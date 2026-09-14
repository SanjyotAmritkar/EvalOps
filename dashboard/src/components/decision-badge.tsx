"use client";

import { Badge } from "@/components/ui/badge";
import { useExperimentResults } from "@/lib/query/experiments";
import {
  DECISION_STATE_LABEL,
  decisionState,
  decisionStateTone,
} from "@/lib/release-decision";

/**
 * A compact, list-row-sized release-decision indicator for one experiment —
 * the same PASS / BLOCK / PASS · advisory / Not gated states `DecisionHero`
 * shows on the experiment page, derived the same way (see
 * {@link decisionState}), so a list never disagrees with its own detail page.
 *
 * Fetches `GET /experiments/{id}/results` (the same backend-authoritative
 * endpoint and React Query hook the detail page already uses) — nothing is
 * recomputed in the browser. Renders nothing while loading or on error, so a
 * list of many rows never jumps or shows a misleading placeholder; "Not run
 * yet" only appears once the API has confirmed there is no stored result.
 */
export function DecisionBadge({ experimentId }: { experimentId: string }) {
  const results = useExperimentResults(experimentId);
  if (!results.data) return null;

  const latest = results.data[results.data.length - 1];
  if (!latest) {
    return <Badge tone="neutral">Not run yet</Badge>;
  }

  const state = decisionState(latest);
  return (
    <Badge tone={decisionStateTone(state)}>{DECISION_STATE_LABEL[state]}</Badge>
  );
}
