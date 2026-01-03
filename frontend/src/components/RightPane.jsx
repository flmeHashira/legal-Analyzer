import FindingCard from "./FindingCard"

export default function RightPane({ findings }) {
  if (!findings || findings.length === 0) {
    return (
      <div className="p-4 text-sm text-muted-foreground">
        No findings available.
      </div>
    )
  }

  return (
    <div className="h-full overflow-y-auto p-4">
      {findings.map(finding => (
        <FindingCard
          key={finding.finding_id}
          finding={finding}
        />
      ))}
    </div>
  )
}
