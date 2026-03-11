export function buildBlockIndex(documentJson) {
  const index = {}

  if (!documentJson || !documentJson.blocks) return index;

  for (const block of documentJson.blocks) {
    // Check if the block has the required positions data
    if (!block.positions) continue;

    // Use the block-level bbox_pdf since the parser consolidated it there
    index[block.block_id] = {
      page: block.positions.page,
      // Wrap in an array because the UI expects a list of bboxes per block
      bboxes: [block.positions.bbox_pdf]
    }
  }

  return index
}