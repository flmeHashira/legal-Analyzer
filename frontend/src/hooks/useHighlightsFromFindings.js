// import { useMemo } from "react"
// import { highlightsFromBlockIds } from "@/lib/highlightsFromBlockIds"

// export function useHighlightsFromFindings(blockIndex, llmResult) {
//   return useMemo(() => {
//     if (!llmResult || !blockIndex) return {}
//     return highlightsFromBlockIds(
//       llmResult.block_ids,
//       blockIndex
//     )
//   }, [blockIndex, llmResult])
// }

import { useMemo } from "react"
import { highlightsFromFindings } from "@/lib/highlightsFromFindings"

/**
 * React hook that converts LLM findings into
 * page-wise flattened highlights for rendering.
 */
export function useHighlightsFromFindings(blockIndex, llmFindings) {
  return useMemo(() => {
    if (!blockIndex || !llmFindings) return {}
    return highlightsFromFindings(llmFindings, blockIndex)
  }, [blockIndex, llmFindings])
}

