import { useState } from "react"
import { useAuth } from '../AuthContext'
import { useNavigate } from "react-router-dom"

import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Checkbox } from "@/components/ui/checkbox"
import {
  Card,
  CardContent,
  CardFooter,
  CardHeader,
} from "@/components/ui/card"
import { Label } from "@/components/ui/label"
import { Lock } from "lucide-react"



export default function Login() {
  const { login } = useAuth()
  const navigate = useNavigate()
  const [email, setEmail] = useState("")
  const [password, setPassword] = useState("")
  const [error, setError] = useState("")

  // Create this function to handle the button click
  const handleSubmit = async (e) => {
    e.preventDefault() // Prevents the page from reloading
    setError("") 
    
    try {
      await login(email, password)
      navigate("/")
    } catch (err) {
      setError("Invalid email or password")
    }
  }

  return (
    <div className="min-h-screen flex flex-col bg-background">
      
      {/* Top Bar */}
      <header className="flex items-center justify-between border-b px-6 py-3 bg-background">
        <div className="flex items-center gap-3">
          <div className="h-6 w-6 text-primary">
            {/* Simple logo placeholder */}
            <div className="h-6 w-6 rounded-full bg-primary" />
          </div>
          <span className="text-lg font-bold tracking-tight">
            LegalDoc AI
          </span>
        </div>
      </header>

      {/* Main */}
      <main className="flex flex-1 items-center justify-center px-6">
        <Card className="w-full max-w-[440px] rounded-xl shadow-lg">
          
          <CardHeader className="space-y-2 text-center">
            <h1 className="text-2xl font-bold tracking-tight">
              Sign in to your account
            </h1>
            <p className="text-sm text-muted-foreground">
              Access your secure legal workspace
            </p>
          </CardHeader>

          <CardContent>
            {/* 1. Add onSubmit here */}
            <form onSubmit={handleSubmit} className="space-y-5">
              
              {/* Email */}
              <div className="space-y-2">
                <Label htmlFor="email">Email</Label>
                <Input
                  id="email"
                  type="email"
                  placeholder="name@company.com"
                  autoComplete="email"
                  // 2. Wire up Email
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  required 
                />
              </div>

              {/* Password */}
              <div className="space-y-2">
                <div className="flex justify-between items-center">
                  <Label htmlFor="password">Password</Label>
                  <button type="button" className="text-xs text-primary hover:underline">
                    Forgot password?
                  </button>
                </div>
                <Input
                  id="password"
                  type="password"
                  placeholder="Enter your password"
                  autoComplete="current-password"
                  // 3. Wire up Password
                  value={password} 
                  onChange={(e) => setPassword(e.target.value)}
                  required
                />
              </div>

              {/* Error Message (Optional but recommended) */}
              {error && <p className="text-sm text-red-500">{error}</p>}

              {/* ... Checkbox code ... */}

              <Button type="submit" className="w-full h-12 text-base font-semibold">
                Sign In
              </Button>
            </form>
          </CardContent>

          <CardFooter className="flex flex-col gap-2 border-t pt-6">
            <div className="flex items-center gap-2 text-xs text-muted-foreground">
              <Lock className="h-4 w-4" />
              <span className="font-medium">
                Privacy-first. Documents processed securely.
              </span>
            </div>
          </CardFooter>

        </Card>
      </main>

      {/* Footer */}
      <footer className="py-8 px-6 text-center text-xs text-muted-foreground">
        <p className="mt-4 text-[10px] uppercase tracking-widest">
          2026 LegalDoc AI. Made with ❤️ by Gourav.
        </p>
      </footer>

    </div>
  )
}