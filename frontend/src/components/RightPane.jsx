import FindingCard from "./FindingCard"
import { ShieldCheck } from "lucide-react"

export default function RightPane({
  findings,
  activeFindingId,
  onSelectFinding,
}) {
  
  if (!findings || findings.length === 0) {
    return (
      <div className="flex h-full flex-col items-center justify-center p-8 text-center bg-slate-50/50 dark:bg-background/50">
        <div className="mb-5 flex h-20 w-20 items-center justify-center rounded-full bg-green-100 text-green-600 dark:bg-green-900/20 dark:text-green-400">
          <ShieldCheck className="h-10 w-10" />
        </div>
        <h3 className="text-xl font-black tracking-tight text-foreground">Document is Clean</h3>
        <p className="mt-2 text-sm text-muted-foreground">
          The AI analysis did not detect any high-risk restrictive covenants, hidden liabilities, or unusual obligations in this text.
        </p>
      </div>
    )
  }

  return (
    <div className="flex h-full flex-col bg-slate-50/30 dark:bg-background">
      {/* Sticky Header to show total count */}
      <div className="border-b bg-background px-4 py-3 sticky top-0 z-10">
        <h2 className="text-sm font-bold uppercase tracking-wider text-muted-foreground">
          Identified Risks ({findings.length})
        </h2>
      </div>

      <div className="flex-1 overflow-y-auto p-4 space-y-4">
        {findings.map((finding) => (
          <FindingCard
            key={finding.finding_id}
            finding={finding}
            isActive={finding.finding_id === activeFindingId}
            onClick={() => onSelectFinding(finding.finding_id)}
          />
        ))}
      </div>
    </div>
  )
}