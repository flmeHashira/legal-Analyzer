import { useEffect, useRef, useState, useMemo } from "react"
import { useParams } from "react-router-dom"
import { usePdf } from "@/lib/usePdf"
import PageContainer from "./PageContainer"
import RightPane from "./RightPane"
import { useBlockIndex } from "@/hooks/useBlockIndex"
import { useHighlightsFromFindings } from "@/hooks/useHighlightsFromFindings"
import { Eye, EyeOff } from "lucide-react"

// Helper to replace all placeholders with original text
const unredactFinding = (finding, redactionMap) => {
  if (!redactionMap || Object.keys(redactionMap).length === 0) return finding;

  let summary = finding.summary || "";
  let explanation = finding.explanation || "";
  let triggers = finding.triggers ? [...finding.triggers] : [];

  // Loop through the map and safely replace occurrences
  Object.entries(redactionMap).forEach(([placeholder, data]) => {
    if (!data || !data.original) return;
    summary = summary.split(placeholder).join(data.original);
    explanation = explanation.split(placeholder).join(data.original);
    triggers = triggers.map(t => t.split(placeholder).join(data.original));
  });

  return { ...finding, summary, explanation, triggers };
};

export default function PdfViewer() {
  const { id } = useParams()
  const API_URL = import.meta.env.VITE_API_URL
  const pdfUrl = `${API_URL}/jobs/${id}/pdf`

  const { getPage, numPages } = usePdf(pdfUrl)

  // Start with empty arrays to prevent mapping errors before data loads
  const [documentJson, setDocumentJson] = useState({ blocks: [], findings: [] })
  const [isDataLoading, setIsDataLoading] = useState(true)

  const [pages, setPages] = useState([]) // 0-indexed
  const [scale, setScale] = useState(1.25)
  const [currentPage, setCurrentPage] = useState(0)
  const [activeFindingId, setActiveFindingId] = useState(null)

  const [redactionMap, setRedactionMap] = useState({})
  const [isRedacted, setIsRedacted] = useState(true) // Start fully masked!

  const scrollRef = useRef(null)
  const pageRefs = useRef({})

  useEffect(() => {
    const fetchDocumentData = async () => {
      try {
        // Fetch Document JSON
        const docRes = await fetch(`${API_URL}/jobs/${id}/result`, {
          credentials: "include"
        })
        if (docRes.ok) {
          const data = await docRes.json()
          setDocumentJson(data)
        }

        // Fetch Redaction Map
        const mapRes = await fetch(`${API_URL}/jobs/${id}/redaction-map`, {
          credentials: "include"
        })
        if (mapRes.ok) {
           const mapData = await mapRes.json()
           setRedactionMap(mapData)
        }
      } catch (err) {
        console.error("Failed to load document data:", err)
      } finally {
        setIsDataLoading(false)
      }
    }

    fetchDocumentData()
  }, [id, API_URL])

  const blockIndex = useBlockIndex(documentJson)

  const llmFindings = documentJson.findings || [];

  // Compute the Display Findings based on the toggle
  const displayFindings = useMemo(() => {
    if (isRedacted) return llmFindings; 
    
    // If unlocked, map over findings and unredact them
    return llmFindings.map(finding => unredactFinding(finding, redactionMap));
  }, [llmFindings, isRedacted, redactionMap]);

  // Pass displayFindings to the highlight hook so highlights match what's shown
  const highlightsByPage = useHighlightsFromFindings(blockIndex, displayFindings)

  useEffect(() => {
    if (!numPages) return
    setPages(Array.from({ length: numPages }, (_, i) => i))
  }, [numPages])

  // derive current page from scroll (largest visible area)
  useEffect(() => {
    const el = scrollRef.current
    if (!el) return

    const onScroll = () => {
      const viewportTop = el.scrollTop
      const viewportBottom = viewportTop + el.clientHeight

      let bestPage = currentPage
      let maxVisible = 0

      for (const [page, node] of Object.entries(pageRefs.current)) {
        if (!node) continue

        const top = node.offsetTop
        const bottom = top + node.offsetHeight
        const visible =
          Math.min(bottom, viewportBottom) - Math.max(top, viewportTop)

        if (visible > maxVisible) {
          maxVisible = visible
          bestPage = Number(page)
        }
      }
      setCurrentPage(bestPage)
    }

    el.addEventListener("scroll", onScroll, { passive: true })
    return () => el.removeEventListener("scroll", onScroll)
  }, [currentPage])

  //scroll to page when a finding is selected (page-based)
  useEffect(() => {
    if (!activeFindingId) return

    const finding = displayFindings.find((f) => f.finding_id === activeFindingId)
    if (!finding || !finding.block_ids.length) return

    const firstBlockId = finding.block_ids[0]
    const block = blockIndex[firstBlockId]
    if (!block) return

    const page = block.page
    const pageEl = pageRefs.current[page]
    if (!pageEl) return

    pageEl.scrollIntoView({
      behavior: "smooth",
      block: "start",
    })
  }, [activeFindingId, displayFindings, blockIndex])

  if (isDataLoading) {
    return <div className="h-screen flex items-center justify-center text-muted-foreground">Loading document data...</div>
  }

  return (
    <div className="h-screen flex overflow-hidden">
      <div className="flex flex-col flex-1">
        <div ref={scrollRef} className="flex-1 overflow-y-auto px-6 py-8">
          <div className="mx-auto max-w-[900px]">
            {pages.map((pageNumber) => (
              <div
                key={pageNumber}
                ref={(el) => {
                  if (el) pageRefs.current[pageNumber] = el
                }}
              >
                <PageContainer
                  pageNumber={pageNumber}
                  getPage={getPage}
                  scale={scale}
                  highlights={highlightsByPage[pageNumber] ?? []}
                  activeFindingId={activeFindingId}
                />
              </div>
            ))}
          </div>
        </div>

        <div className="flex items-center gap-4 px-4 py-2 border-t bg-background">
          <span className="text-sm">
            Page {currentPage + 1} / {numPages}
          </span>

          <div className="ml-auto flex items-center gap-6">
            
            {/* PRIVACY TOGGLE */}
            <div className="flex items-center gap-2 border-r pr-6">
              <span className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">
                PII Masking
              </span>
              <button 
                onClick={() => setIsRedacted(!isRedacted)}
                className={`flex items-center gap-2 px-3 py-1.5 rounded-md text-sm font-bold transition-colors ${
                  isRedacted 
                    ? "bg-green-100 text-green-700 hover:bg-green-200" 
                    : "bg-red-100 text-red-700 hover:bg-red-200"
                }`}
              >
                {isRedacted ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                {isRedacted ? "Active" : "Revealed"}
              </button>
            </div>

            <div className="flex items-center gap-2">
              <button onClick={() => setScale((s) => Math.min(3, s + 0.1))}>
                +
              </button>
              <button onClick={() => setScale((s) => Math.max(0.5, s - 0.1))}>
                −
              </button>
              <span className="w-12 text-right">{Math.round(scale * 100)}%</span>
            </div>
          </div>
        </div>
      </div>

      <div className="w-[380px] border-l overflow-y-auto">
        <RightPane
          findings={displayFindings}
          activeFindingId={activeFindingId}
          onSelectFinding={setActiveFindingId}
        />
      </div>
    </div>
  )
}