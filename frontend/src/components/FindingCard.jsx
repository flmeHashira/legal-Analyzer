import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import {
  Accordion,
  AccordionItem,
  AccordionTrigger,
  AccordionContent,
} from "@/components/ui/accordion"

export default function FindingCard({
  finding,
  isActive,
  onClick,
}) {

  const { risk, summary, explanation, triggers } = finding

  return (
    <Card
  onClick={onClick}
  className={`mb-4 cursor-pointer transition
    ${isActive ? "ring-2 ring-gray-500" : "hover:bg-muted/40"}
  `}
>
      <CardHeader className="space-y-2">
        <Badge variant={riskVariant(risk)}>{risk.toUpperCase()} RISK</Badge>

        <CardTitle className="text-base leading-snug">{summary}</CardTitle>
      </CardHeader>

      <CardContent className="space-y-4 text-sm">
        <p className="leading-relaxed">{explanation}</p>

        {triggers?.length > 0 && (
          <Accordion type="single" collapsible>
            <AccordionItem value="triggers">
              <AccordionTrigger>Why was this flagged?</AccordionTrigger>

              <AccordionContent>
                <ul className="list-disc pl-5 space-y-1">
                  {triggers.map((t, i) => (
                    <li key={i}>{t}</li>
                  ))}
                </ul>
              </AccordionContent>
            </AccordionItem>
          </Accordion>
        )}
      </CardContent>
    </Card>
  )
}

function riskVariant(risk) {
  switch (risk) {
    case "high":
      return "destructive"
    case "medium":
      return "secondary"
    case "low":
      return "outline"
    default:
      return "secondary"
  }
}
