import { useEffect, useState } from "react"
import { usePdf } from "@/lib/usePdf"
import PdfPage from "@/components/PdfPage"

export default function App() {
  const { getPage, numPages, loading } = usePdf("/exhibit101.pdf")
  const [page, setPage] = useState(null)

  useEffect(() => {
    let cancelled = false

    async function loadPage() {
      if (!getPage || numPages === 0) return
      const p = await getPage(1)
      if (!cancelled) setPage(p)
    }

    loadPage()

    return () => {
      cancelled = true
    }
  }, [getPage, numPages])

  if (loading || !page) {
    return <div style={{ padding: 24 }}>Loading…</div>
  }

  return (
    <div style={{ padding: 24 }}>
      <PdfPage page={page} />
    </div>
  )
}
