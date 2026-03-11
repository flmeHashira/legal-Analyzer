import { useState, useEffect, useRef } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../AuthContext";

import { 
  FileText, Settings, Bell, LogOut, UploadCloud, Lock, 
  Search, File, ShieldCheck, Trash2, ChevronLeft, ChevronRight, Loader2
} from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";

export default function Home() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  
  // Use Vite Environment Variable
  const API_URL = import.meta.env.VITE_API_URL;
  
  // State
  const [jobs, setJobs] = useState([]);
  const [isUploading, setIsUploading] = useState(false);
  const [isLoading, setIsLoading] = useState(true);
  const [searchQuery, setSearchQuery] = useState("");
  
  // Ref for the hidden file input
  const fileInputRef = useRef(null);

  // 1. Fetch Jobs from DB
  const fetchJobs = async () => {
    try {
      const response = await fetch(`${API_URL}/jobs`, {
        credentials: "include"
      });
      if (response.ok) {
        const data = await response.json();
        setJobs(data);
      }
    } catch (error) {
      console.error("Failed to fetch jobs:", error);
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    fetchJobs();
  }, []);

  // AUTO-POLLING
  useEffect(() => {
    // 1. Check if any job is currently in progress
    const hasActiveJobs = jobs.some(
      job => job.status === "QUEUED" || job.status === "PROCESSING"
    );

    // 2. If nothing is processing, don't waste network requests
    if (!hasActiveJobs) return;

    // 3. If something IS processing, check the DB every 3 seconds
    const interval = setInterval(() => {
      fetchJobs();
    }, 3000);

    // 4. Cleanup: Stop the timer when the component unmounts or jobs update
    return () => clearInterval(interval);
    
  }, [jobs]);

  // 2. Handle File Upload
  const handleUpload = async (event) => {
    const file = event.target.files[0];
    if (!file) return;

    setIsUploading(true);
    const formData = new FormData();
    formData.append("pdf", file); // Must match multer.single('pdf')

    try {
      const response = await fetch(`${API_URL}/upload`, {
        method: "POST",
        body: formData,
        credentials: "include"
      });

      if (response.ok) {
        // Refresh the list immediately to show the QUEUED job
        await fetchJobs();
      } else {
        alert("Upload failed. Please try again.");
      }
    } catch (error) {
      console.error("Upload error:", error);
    } finally {
      setIsUploading(false);
      event.target.value = null; // Reset input so you can upload the same file again if needed
    }
  };

  const handleLogout = async () => {
    await logout();
    navigate("/login");
  };

  // Helper: Format Postgres Date
  const formatDate = (dateString) => {
    return new Date(dateString).toLocaleString('en-US', {
      month: 'short', day: 'numeric', year: 'numeric', 
      hour: '2-digit', minute:'2-digit'
    });
  };

  // Helper: Status Badges
  const StatusBadge = ({ status }) => {
    switch (status) {
      case "COMPLETED":
        return <Badge variant="outline" className="bg-green-50 text-green-700 border-green-200 dark:bg-green-900/20 dark:text-green-400 dark:border-green-800/30">Completed</Badge>;
      case "QUEUED":
      case "PROCESSING":
        return (
          <Badge variant="outline" className="bg-primary/5 text-primary border-primary/20 flex gap-1.5 items-center">
            <Loader2 className="h-3 w-3 animate-spin" /> {status === "QUEUED" ? "Queued" : "Processing"}
          </Badge>
        );
      case "FAILED":
        return <Badge variant="outline" className="bg-red-50 text-red-700 border-red-200 dark:bg-red-900/20 dark:text-red-400 dark:border-red-800/30">Failed</Badge>;
      case "PURGED":
        return <Badge variant="outline" className="bg-gray-100 text-gray-500 border-gray-300 dark:bg-gray-800 dark:text-gray-400">Purged</Badge>;
      default:
        return <Badge variant="outline">{status}</Badge>;
    }
  };

  // Filter jobs based on search (Updated to use original_filename)
  const filteredJobs = jobs.filter(job => {
    const searchTarget = job.original_filename || job.input_file || "";
    return searchTarget.toLowerCase().includes(searchQuery.toLowerCase());
  });

  return (
    <div className="bg-slate-50 dark:bg-background min-h-screen font-sans text-foreground">
      {/* Top Nav (Unchanged) */}
      <header className="sticky top-0 z-50 w-full border-b bg-background/80 backdrop-blur-md">
        <div className="mx-auto flex max-w-[1200px] items-center justify-between px-6 py-3">
          <div className="flex items-center gap-3">
            <div className="flex size-8 items-center justify-center rounded bg-primary text-primary-foreground">
              <FileText className="h-5 w-5" />
            </div>
            <h1 className="text-lg font-bold tracking-tight">LegalDoc Analysis</h1>
          </div>
          <div className="flex items-center gap-4">
            <div className="flex items-center gap-3">
              <span className="hidden md:block text-sm font-medium">{user?.email || "User"}</span>
              <Button variant="ghost" size="icon" onClick={handleLogout} className="text-muted-foreground hover:text-red-500" title="Log Out">
                <LogOut className="h-5 w-5" />
              </Button>
            </div>
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-[1200px] px-6 py-8">
        <div className="mb-8 flex flex-col gap-1">
          <h2 className="text-3xl font-black tracking-tight">Document Jobs</h2>
          <p className="text-muted-foreground text-base">Manage and monitor your legal document analysis tasks with privacy in mind.</p>
        </div>

        {/* Upload Zone */}
        <div className="mb-8">
          <div className="flex flex-col items-center gap-5 rounded-xl border-2 border-dashed border-border bg-card px-6 py-10 transition-all hover:border-primary/50">
            <div className="flex h-14 w-14 items-center justify-center rounded-full bg-primary/10 text-primary">
              {isUploading ? <Loader2 className="h-8 w-8 animate-spin" /> : <UploadCloud className="h-8 w-8" />}
            </div>
            <div className="flex max-w-[480px] flex-col items-center gap-1 text-center">
              <p className="text-lg font-bold">Upload PDF Document</p>
              <p className="text-sm font-normal text-muted-foreground">
                Drag and drop your PDF here or click to browse. Files are processed privately and deleted after 24 hours.
              </p>
            </div>
            
            {/* Hidden File Input & Trigger Button */}
            <input 
              type="file" 
              accept="application/pdf" 
              ref={fileInputRef} 
              onChange={handleUpload} 
              className="hidden" 
            />
            <Button 
              onClick={() => fileInputRef.current.click()} 
              disabled={isUploading}
              className="min-w-[140px] font-bold tracking-wide"
            >
              {isUploading ? "Uploading..." : "Browse Files"}
            </Button>
            
            <div className="flex items-center gap-2 text-[10px] uppercase tracking-widest text-muted-foreground">
              <Lock className="h-3 w-3" />
              <span>Private processing</span>
            </div>
          </div>
        </div>

        <div className="mb-6 flex flex-col items-center justify-between gap-4 md:flex-row">
          <div className="flex w-full border-b md:w-auto">
             <button className="border-b-2 border-primary px-4 py-3 text-sm font-bold text-primary">All Jobs</button>
          </div>
          <div className="relative w-full md:max-w-xs">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
            <Input 
              className="pl-9" 
              placeholder="Search by file name..." 
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
            />
          </div>
        </div>

        {/* Data Table */}
        <div className="overflow-hidden rounded-xl border bg-card shadow-sm">
          <Table>
            <TableHeader className="bg-muted/50">
              <TableRow>
                <TableHead>File Name</TableHead>
                <TableHead>Status</TableHead>
                <TableHead className="text-center">Pages</TableHead>
                <TableHead>Date Created</TableHead>
                <TableHead className="text-right">Action</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {isLoading ? (
                <TableRow><TableCell colSpan={5} className="text-center py-10 text-muted-foreground">Loading documents...</TableCell></TableRow>
              ) : filteredJobs.length === 0 ? (
                <TableRow><TableCell colSpan={5} className="text-center py-10 text-muted-foreground">No documents found. Upload one above.</TableCell></TableRow>
              ) : (
                filteredJobs.map((job) => (
                  <TableRow key={job.id} className="hover:bg-muted/50 transition-colors">
                    <TableCell className="font-medium">
                      <div className="flex items-center gap-3">
                        <File className="h-4 w-4 text-muted-foreground" />
                        <span className="truncate max-w-[200px] block" title={job.original_filename}>
                            {job.original_filename || job.input_file}
                        </span>
                      </div>
                    </TableCell>
                    <TableCell><StatusBadge status={job.status} /></TableCell>
                    <TableCell className="text-center text-muted-foreground">{job.page_count || "--"}</TableCell>
                    <TableCell className="text-muted-foreground">{formatDate(job.created_at)}</TableCell>
                    <TableCell className="text-right">
                      <Button 
                        variant="secondary" 
                        size="sm" 
                        className="h-8 text-xs font-bold text-primary bg-primary/10 hover:bg-primary/20 disabled:opacity-50"
                        disabled={job.status !== "COMPLETED"}
                        onClick={() => navigate(`/document/${job.id}`)}
                      >
                        {job.status === "PURGED" ? "Expired" : "Open"}
                      </Button>
                    </TableCell>
                  </TableRow>
                ))
              )}
            </TableBody>
          </Table>
        </div>
      </main>
    </div>
  );
}