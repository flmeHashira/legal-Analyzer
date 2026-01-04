import { useEffect, useRef, useState } from "react";
import { usePdf } from "@/lib/usePdf";
import PageContainer from "./PageContainer";
import RightPane from "./RightPane";
import documentJson from "@/data/document.runtime.json";
import { useBlockIndex } from "@/hooks/useBlockIndex";
import { useHighlightsFromFindings } from "@/hooks/useHighlightsFromFindings";

export default function PdfViewer() {
  const { getPage, numPages } = usePdf("/exhibit101.pdf");

  const [pages, setPages] = useState([]); // 0-indexed
  const [scale, setScale] = useState(1.25);
  const [currentPage, setCurrentPage] = useState(0);
  const [activeFindingId, setActiveFindingId] = useState(null);

  const scrollRef = useRef(null);
  const pageRefs = useRef({});

  const blockIndex = useBlockIndex(documentJson);

  const [llmFindings] = useState([
    {
      finding_id: "f001",
      block_ids: ["b000001", "b000003", "b000004"],
      risk: "high",
      summary: "Restrictive employment obligations",
      explanation:
        "These sections collectively require the executive to devote full business efforts to the company and restrict outside engagements without approval.",
      triggers: ["exclusive service requirement", "prior written approval"],
    },
    {
      finding_id: "f002",
      block_ids: ["b000095", "b000096", "b000112"],
      risk: "medium",
      summary: "Representations regarding conflicting obligations",
      explanation:
        "The executive warrants that no prior obligations conflict with this agreement, which could create exposure if inaccurate.",
      triggers: ["representations and warranties", "prior obligations"],
    },
  ]);

  const highlightsByPage = useHighlightsFromFindings(blockIndex, llmFindings);

  useEffect(() => {
    if (!numPages) return;
    setPages(Array.from({ length: numPages }, (_, i) => i));
  }, [numPages]);

  // derive current page from scroll (largest visible area)
  useEffect(() => {
    const el = scrollRef.current;
    if (!el) return;

    const onScroll = () => {
      const viewportTop = el.scrollTop;
      const viewportBottom = viewportTop + el.clientHeight;

      let bestPage = currentPage;
      let maxVisible = 0;

      for (const [page, node] of Object.entries(pageRefs.current)) {
        if (!node) continue;

        const top = node.offsetTop;
        const bottom = top + node.offsetHeight;
        const visible =
          Math.min(bottom, viewportBottom) - Math.max(top, viewportTop);

        if (visible > maxVisible) {
          maxVisible = visible;
          bestPage = Number(page);
        }
      }
      setCurrentPage(bestPage);
    };

    el.addEventListener("scroll", onScroll, { passive: true });
    return () => el.removeEventListener("scroll", onScroll);
  }, [currentPage]);

  //scroll to page when a finding is selected (page-based)
  useEffect(() => {
    if (!activeFindingId) return;

    const finding = llmFindings.find((f) => f.finding_id === activeFindingId);
    if (!finding || !finding.block_ids.length) return;

    const firstBlockId = finding.block_ids[0];
    const block = blockIndex[firstBlockId];
    if (!block) return;

    const page = block.page;
    const pageEl = pageRefs.current[page];
    if (!pageEl) return;

    pageEl.scrollIntoView({
      behavior: "smooth",
      block: "start",
    });
  }, [activeFindingId, llmFindings, blockIndex]);

  return (
    <div className="h-screen flex overflow-hidden">
      <div className="flex flex-col flex-1">
        <div ref={scrollRef} className="flex-1 overflow-y-auto px-6 py-8">
          <div className="mx-auto max-w-[900px]">
            {pages.map((pageNumber) => (
              <div
                key={pageNumber}
                ref={(el) => {
                  if (el) pageRefs.current[pageNumber] = el;
                }}
              >
                <PageContainer
                  pageNumber={pageNumber}
                  getPage={getPage}
                  scale={scale}
                  highlights={highlightsByPage[pageNumber] ?? []}
                  activeFindingId={activeFindingId}
                />
              </div>
            ))}
          </div>
        </div>

        <div className="flex items-center gap-4 px-4 py-2 border-t bg-background">
          <span className="text-sm">
            Page {currentPage + 1} / {numPages}
          </span>

          <div className="ml-auto flex items-center gap-2">
            <button onClick={() => setScale((s) => Math.min(3, s + 0.1))}>
              +
            </button>
            <button onClick={() => setScale((s) => Math.max(0.5, s - 0.1))}>
              −
            </button>
            <span>{Math.round(scale * 100)}%</span>
          </div>
        </div>
      </div>

      <div className="w-[380px] border-l overflow-y-auto">
        <RightPane
          findings={llmFindings}
          activeFindingId={activeFindingId}
          onSelectFinding={setActiveFindingId}
        />
      </div>
    </div>
  );
}
