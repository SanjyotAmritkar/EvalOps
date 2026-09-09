import { Badge } from "./badge";

/**
 * PASS / BLOCK / NEEDS REVIEW badge for a release-gate decision. Only render
 * this when the decision actually comes from API data (a run response).
 */
export function DecisionBadge({
  decision,
  gated,
}: {
  decision: string;
  gated: boolean;
}) {
  if (!gated) {
    return <Badge tone="neutral">Ungated</Badge>;
  }
  if (decision === "pass") {
    return <Badge tone="pass">PASS</Badge>;
  }
  if (decision === "block") {
    return <Badge tone="block">BLOCK</Badge>;
  }
  if (decision === "needs_review") {
    return <Badge tone="warn">NEEDS REVIEW</Badge>;
  }
  return <Badge tone="neutral">{decision}</Badge>;
}
