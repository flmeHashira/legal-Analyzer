import { useEffect, useRef } from "react";
import { pdfBBoxToViewportRect } from "@/lib/pdfBBoxToViewportRect";

function riskBaseColor(risk) {
  switch (risk) {
    case "high":
      return "rgba(239, 68, 68, 0.28)";
    case "medium":
      return "rgba(245, 158, 11, 0.28)";
    case "low":
      return "rgba(59, 130, 246, 0.22)";
    default:
      return "rgba(100, 116, 139, 0.22)";
  }
}

function activeOverlayStyle(isActive) {
  if (!isActive) return {};

  return {
    outline: "2px solid rgba(239, 68, 68, 0.9)",
    boxShadow: "0 0 0 2px rgba(239, 68, 68, 0.35)",
    zIndex: 10,
  };
}

export default function PdfPage({
  page,
  scale = 1.25,
  highlights,
  activeFindingId,
}) {
  const canvasRef = useRef(null);
  const renderTaskRef = useRef(null);

  useEffect(() => {
    if (!page) return;

    const canvas = canvasRef.current;
    const ctx = canvas.getContext("2d");

    const viewport = page.getViewport({ scale });
    const dpr = window.devicePixelRatio || 1;

    canvas.width = Math.floor(viewport.width * dpr);
    canvas.height = Math.floor(viewport.height * dpr);
    canvas.style.width = `${viewport.width}px`;
    canvas.style.height = `${viewport.height}px`;

    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);

    if (renderTaskRef.current) {
      renderTaskRef.current.cancel();
    }

    const task = page.render({
      canvasContext: ctx,
      viewport,
    });

    renderTaskRef.current = task;
    task.promise.catch((err) => {
      if (err?.name !== "RenderingCancelledException") {
        console.error("Render error:", err);
      }
    });

    return () => {
      task.cancel();
    };
  }, [page, scale]);

  if (!page) return null;
  return (
    <div
      style={{
        position: "relative",
        marginBottom: 24,
      }}>
      <canvas ref={canvasRef} />

      {highlights.map((h) => {
        const pageHeightPdf = page.view[3] - page.view[1];
        const bboxes = h.bboxes ?? (h.bbox ? [h.bbox] : []);
        const isActive = h.finding_id === activeFindingId;

        return bboxes.map((bbox, idx) => {
          const { left, top, width, height } = pdfBBoxToViewportRect(bbox, pageHeightPdf, scale);

          return (
            <div
              key={`${h.finding_id}-${idx}`}
              style={{
                position: "absolute",
                left,
                top,
                width,
                height,
                background: riskBaseColor(h.risk),  //base risk color (always visible)
                ...activeOverlayStyle(isActive),    //additional styles if active

                pointerEvents: "none",
              }}
            />
          );
        });
      })}
    </div>
  );
}
