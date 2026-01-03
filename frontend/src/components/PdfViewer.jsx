import { useEffect, useState } from "react"
import { usePdf } from "@/lib/usePdf"
import PageContainer from "./PageContainer"
import RightPane from "./RightPane"
import documentJson from "@/data/document.runtime.json"
import { useBlockIndex } from "@/hooks/useBlockIndex"

// findings -> page-wise flattened highlights
import { useHighlightsFromFindings } from "@/hooks/useHighlightsFromFindings"

export default function PdfViewer() {
  const { getPage, numPages } = usePdf("/exhibit101.pdf")
  const [pages, setPages] = useState([])    // 0-indexed page numbers
  const [scale, setScale] = useState(1.25)
  const [activeFindingId, setActiveFindingId] = useState(null)

  const blockIndex = useBlockIndex(documentJson)    // blockIndex[block_id] -> { page, bboxes }

  const [llmFindings] = useState([
    {
      finding_id: "f001",
      block_ids: ["b000001", "b000003", "b000004"],
      risk: "high",
      summary: "Restrictive employment obligations",
      explanation:
        "These sections collectively require the executive to devote full business efforts to the company and restrict outside engagements without approval.",
      triggers: [
        "exclusive service requirement",
        "prior written approval",
      ],
    },
    {
      finding_id: "f002",
      block_ids: ["b000095", "b000096", "b000112"],
      risk: "medium",
      summary: "Representations regarding conflicting obligations",
      explanation:
        "The executive warrants that no prior obligations conflict with this agreement, which could create exposure if inaccurate.",
      triggers: [
        "representations and warranties",
        "prior obligations",
      ],
    },
  ])

  // highlightsByPage[page] -> flat list of rects
  const highlightsByPage = useHighlightsFromFindings(
    blockIndex,
    llmFindings
  )

  // Build page list once PDF is loaded (0-indexed)
  useEffect(() => {
    if (!numPages) return
    setPages(Array.from({ length: numPages }, (_, i) => i))
  }, [numPages])

  return (
    <div className="h-screen flex flex-col">
        {/* Top bar */}
        <div className="flex gap-2 p-2 border-b">
        <button onClick={() => setScale(s => Math.max(0.5, s - 0.1))}>
            −
        </button>
        <span>{Math.round(scale * 100)}%</span>
        <button onClick={() => setScale(s => Math.min(3, s + 0.1))}>
            +
        </button>
        </div>

        {/* Main content */}
        <div className="flex flex-1 overflow-hidden">
        {/* PDF (left) */}
        <div className="flex-1 overflow-y-auto p-6">
            {pages.map(pageNumber => (
            <PageContainer
                key={pageNumber}
                pageNumber={pageNumber}
                getPage={getPage}
                scale={scale}
                highlights={highlightsByPage[pageNumber] ?? []}
                activeFindingId={activeFindingId} 
            />
            ))}
        </div>

        {/* Right pane (findings) */}
        <div className="w-[380px] border-l">
            <RightPane
                findings={llmFindings}
                activeFindingId={activeFindingId}
                onSelectFinding={setActiveFindingId}/>
        </div>
        </div>
    </div>
    )
}
