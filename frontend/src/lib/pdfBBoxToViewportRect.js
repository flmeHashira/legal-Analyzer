/**
 * Convert a PDF-space bbox into viewport-space rectangle
 *
 * @param {number[]} bbox - [x, y, w, h] in PDF units (origin bottom-left)
 * @param {number} pageHeightPdf - page height in PDF units
 * @param {number} scale - viewport scale
 */
export function pdfBBoxToViewportRect(bbox, pageHeightPdf, scale) {
  const [x, y, w, h] = bbox

  // PDF → viewport conversion
  const left = x * scale

  // Flip Y-axis: PDF bottom-left → DOM top-left
  const top = (pageHeightPdf - (y + h)) * scale

  const width = w * scale
  const height = h * scale

  return {
    left,
    top,
    width,
    height,
  }
}
