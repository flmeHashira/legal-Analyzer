import { useEffect, useState } from "react"
import { usePdf } from "@/lib/usePdf"
import PageContainer from "./PageContainer"

export default function PdfViewer() {
  const { getPage, numPages } = usePdf("/exhibit101.pdf")
  const [pages, setPages] = useState([])
  const [scale, setScale] = useState(1.25)

  useEffect(() => {
    if (!numPages) return
    setPages(Array.from({ length: numPages }, (_, i) => i + 1))
  }, [numPages])

  return (
    <div className="h-screen flex flex-col">
      {/* Zoom controls */}
      <div className="flex gap-2 p-2 border-b">
        <button onClick={() => setScale(s => Math.max(0.5, s - 0.1))}>−</button>
        <span>{Math.round(scale * 100)}%</span>
        <button onClick={() => setScale(s => Math.min(3, s + 0.1))}>+</button>
      </div>

      {/* Scroll container */}
      <div className="flex-1 overflow-y-auto p-6">
        {pages.map(pageNumber => (
          <PageContainer
            key={pageNumber}
            pageNumber={pageNumber}
            getPage={getPage}
            scale={scale}
          />
        ))}
      </div>
    </div>
  )
}
