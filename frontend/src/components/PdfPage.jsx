import { useEffect, useRef } from "react"

export default function PdfPage({ page, scale = 1.25 }) {
  const canvasRef = useRef(null)
  const renderTaskRef = useRef(null)

  useEffect(() => {
    if (!page) return

    const canvas = canvasRef.current
    const ctx = canvas.getContext("2d")

    const viewport = page.getViewport({ scale })
    const dpr = window.devicePixelRatio || 1

    // Set real pixel size
    canvas.width = Math.floor(viewport.width * dpr)
    canvas.height = Math.floor(viewport.height * dpr)

    // Set CSS size
    canvas.style.width = `${viewport.width}px`
    canvas.style.height = `${viewport.height}px`

    ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
    ctx.clearRect(0, 0, canvas.width, canvas.height)

    // IMPORTANT: cancel any in-flight render
    if (renderTaskRef.current) {
      renderTaskRef.current.cancel()
    }

    const renderTask = page.render({
        canvasContext: ctx,
        viewport,
    })

    renderTask.promise.catch((err) => {
        // Ignore expected cancellation
        if (err?.name !== "RenderingCancelledException") {
            console.error(err)
        }
    })

    renderTaskRef.current = renderTask


    return () => {
      // cleanup on unmount / rerender
      if (renderTaskRef.current) {
        renderTaskRef.current.cancel()
        renderTaskRef.current = null
      }
    }
  }, [page, scale])

  return <canvas ref={canvasRef} />
}
