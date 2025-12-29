import { useEffect, useState } from "react"
import PdfPage from "./PdfPage"

const testHighlights = [
  {
    id: "test",
    bbox: [100, 600, 200, 20], // x, y, width, height
  },
]

export default function PageContainer({ pageNumber, getPage, scale }) {
  const [page, setPage] = useState(null)

  useEffect(() => {
    let cancelled = false
    getPage(pageNumber).then(p => {
      if (!cancelled) setPage(p)
    })
    return () => {
      cancelled = true
    }
  }, [pageNumber, getPage])

  if (!page) {
    return <div style={{ height: 400 }} />
  }

  return <PdfPage page={page} scale={scale} highlights={testHighlights} />
}
