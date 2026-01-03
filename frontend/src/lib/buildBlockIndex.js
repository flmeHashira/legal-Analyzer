export function buildBlockIndex(documentJson) {
  const index = {}

  for (const block of documentJson.blocks) {
    if (!block.positions) continue

    index[block.block_id] = {
      page: block.positions.page,
      bboxes: block.positions.line_spans.map(
        ls => ls.bbox_pdf
      ),
    }
  }

  return index
}
