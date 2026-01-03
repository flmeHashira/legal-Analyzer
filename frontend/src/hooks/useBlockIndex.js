import { useMemo } from "react"
import { buildBlockIndex } from "@/lib/buildBlockIndex"

export function useBlockIndex(documentJson) {
  return useMemo(
    () => buildBlockIndex(documentJson),
    [documentJson]
  )
}