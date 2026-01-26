export default function PdfNavBar({
  currentPage,
  totalPages,
  zoom,
  onZoomIn,
  onZoomOut,
  onPrevPage,
  onNextPage,
}) {
  return (
    <div className="flex items-center gap-4 px-4 py-2 border-b bg-background">
      {/* Page controls */}
      <button onClick={onPrevPage} disabled={currentPage <= 0}>
        ←
      </button>

      <span className="text-sm">
        Page {currentPage + 1} / {totalPages}
      </span>

      <button onClick={onNextPage} disabled={currentPage >= totalPages - 1}>
        →
      </button>

      <div className="ml-auto flex items-center gap-2">
        <button onClick={onZoomOut}>−</button>
        <span className="text-sm">{Math.round(zoom * 100)}%</span>
        <button onClick={onZoomIn}>+</button>
      </div>
    </div>
  )
}
