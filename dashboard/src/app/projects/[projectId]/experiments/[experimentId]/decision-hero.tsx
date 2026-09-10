import Link from "next/link";
import { InfoHint } from "@/components/ui/info-hint";
import { cn } from "@/lib/cn";
import type { MetricLine } from "@/lib/api/types";
import { blockingSentence, metricStatus } from "@/lib/release-decision";

type HeroState = "pass" | "block" | "advisory" | "not-gated";

const FRAME: Record<HeroState, string> = {
  pass: "border-pass/40 bg-pass/5",
  block: "border-block/40 bg-block/5",
  advisory: "border-warn/40 bg-warn/5",
  "not-gated": "border-border bg-surface-raised",
};

const TOKEN: Record<HeroState, string> = {
  pass: "border-pass/50 bg-pass/10 text-pass",
  block: "border-block/50 bg-block/10 text-block",
  advisory: "border-warn/50 bg-warn/10 text-warn",
  "not-gated": "border-border bg-surface text-fg-muted",
};

const HEADLINE: Record<HeroState, string> = {
  pass: "Ready to release",
  block: "Release blocked",
  advisory: "Passed with unverified concerns",
  "not-gated": "Comparison only",
};

const TOKEN_TEXT: Record<HeroState, string> = {
  pass: "PASS",
  block: "BLOCK",
  advisory: "PASS",
  "not-gated": "Not gated",
};

/**
 * The dominant result of a completed experiment. Every word and number here is
 * the backend's — `decision`, `gated`, `reasons` and `advisories` come straight
 * from the recomputed EvaluationResult. No gate logic runs in the browser.
 */
export function DecisionHero({
  decision,
  gated,
  reasons,
  advisories,
  metrics,
  policyHref,
}: {
  decision: string;
  gated: boolean;
  reasons: string[];
  advisories: string[];
  metrics: MetricLine[];
  policyHref?: string;
}) {
  const state: HeroState = !gated
    ? "not-gated"
    : decision === "block"
      ? "block"
      : advisories.length > 0
        ? "advisory"
        : "pass";

  const blocking = metrics.filter((m) => m.regression);
  const improved = metrics.filter((m) => metricStatus(m) === "improved");

  return (
    <section
      aria-label="Release decision"
      className={cn("flex flex-col gap-3 rounded-xl border p-5", FRAME[state])}
    >
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
        <span
          className={cn(
            "inline-flex items-center rounded-md border px-2.5 py-1 text-[15px] font-bold tracking-tight",
            TOKEN[state],
          )}
        >
          {TOKEN_TEXT[state]}
          {state === "advisory" ? (
            <span className="ml-1.5 font-medium">· advisory</span>
          ) : null}
        </span>
        <h2 className="text-[22px] font-semibold leading-tight tracking-tight text-fg">
          {HEADLINE[state]}
        </h2>
        <InfoHint label="What does the release decision mean?" />
      </div>

      {state === "not-gated" ? (
        <p className="text-[15px] leading-relaxed text-fg-muted">
          No release policy is attached, so the two versions were measured but no
          PASS or BLOCK decision was made.{" "}
          {policyHref ? (
            <>
              <Link
                href={policyHref}
                className="font-medium text-accent underline-offset-2 hover:underline"
              >
                Attach a release policy
              </Link>{" "}
              to gate this comparison.
            </>
          ) : (
            "Attach a release policy to gate this comparison."
          )}
        </p>
      ) : state === "block" ? (
        <div className="flex flex-col gap-2">
          <p className="text-[15px] font-medium text-block">
            {blocking.length} policy metric{blocking.length === 1 ? "" : "s"}{" "}
            regressed beyond tolerance, with statistical evidence strong enough to
            confirm it.
          </p>
          <ul className="flex flex-col gap-1 text-[14px] leading-relaxed text-fg-muted">
            {(blocking.length > 0
              ? blocking.map((m) => blockingSentence(m))
              : reasons
            ).map((sentence, index) => (
              <li key={index} className="flex gap-2">
                <span aria-hidden className="text-block">
                  •
                </span>
                <span>{sentence}</span>
              </li>
            ))}
          </ul>
        </div>
      ) : state === "advisory" ? (
        <div className="flex flex-col gap-2">
          <p className="text-[15px] font-medium text-warn">
            {advisories.length} threshold breach
            {advisories.length === 1 ? "" : "es"} could not be confirmed
            statistically. Do not read this as an unconditional pass.
          </p>
          <ul className="flex flex-col gap-1 text-[14px] leading-relaxed text-fg-muted">
            {advisories.map((advisory, index) => (
              <li key={index} className="flex gap-2">
                <span aria-hidden className="text-warn">
                  •
                </span>
                <span>{advisory}</span>
              </li>
            ))}
          </ul>
          <p className="text-[13px] text-fg-subtle">
            Re-run with more repeats or a larger dataset for a conclusive result.
          </p>
        </div>
      ) : (
        <p className="text-[15px] leading-relaxed text-fg-muted">
          All gated metrics stayed within the release policy
          {improved.length > 0
            ? `; ${improved.length} metric${improved.length === 1 ? "" : "s"} improved.`
            : ". No statistically confirmed regression exceeded the configured policy."}
        </p>
      )}
    </section>
  );
}
