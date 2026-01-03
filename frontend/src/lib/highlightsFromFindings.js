export function highlightsFromFindings(llmFindings, blockIndex) {
  const byPage = {}

  for (const finding of llmFindings) {
    const { finding_id, block_ids, risk } = finding

    for (const blockId of block_ids) {
      const entry = blockIndex[blockId]
      if (!entry) continue

      const { page, bboxes } = entry

      if (!byPage[page]) byPage[page] = []

      byPage[page].push({
        finding_id,
        block_id: blockId,
        risk,
        bboxes,
      })
    }
  }

  return byPage
}
