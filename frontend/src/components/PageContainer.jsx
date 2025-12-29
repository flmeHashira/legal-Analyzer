import { useEffect, useState } from "react"
import PdfPage from "./PdfPage"

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

  return <PdfPage page={page} scale={scale} />
}
