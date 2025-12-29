// src/lib/usePdf.js
import { useEffect, useRef, useState, useCallback } from "react"
import { getDocument, GlobalWorkerOptions } from "pdfjs-dist"

// Ensure worker path works with Vite's ESM resolution
import workerSrc from "pdfjs-dist/build/pdf.worker.mjs?url"
GlobalWorkerOptions.workerSrc = workerSrc


export function usePdf(fileUrl) {
  const pdfRef = useRef(null)            // holds the loaded PDF document object
  const [numPages, setNumPages] = useState(0)
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    if (!fileUrl) return
    let cancelled = false
    setLoading(true)

    const load = async () => {
      try {
        const loadingTask = getDocument(fileUrl)
        const pdf = await loadingTask.promise
        if (cancelled) return
        pdfRef.current = pdf
        setNumPages(pdf.numPages)
        setLoading(false)
      } catch (err) {
        console.error("usePdf load error:", err)
        if (!cancelled) setLoading(false)
      }
    }

    load()
    return () => {
      cancelled = true
      // optional cleanup: free PDF.js internal caches if available
      if (pdfRef.current?.cleanup) pdfRef.current.cleanup()
    }
  }, [fileUrl])

  const getPage = useCallback(
    async (pageNumber) => {
      if (!pdfRef.current) return null
      return pdfRef.current.getPage(pageNumber)
    },
    []
  )

  return { getPage, numPages, loading }
}
