"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { Drawer } from "@/components/ui/drawer";
import { cn } from "@/lib/cn";

interface HelpApi {
  /** Opens the glossary. With `term`, scrolls to and focuses that entry
   * instead of leaving the reader at the top of a 12-entry list. */
  openHelp: (term?: string) => void;
}

const HelpContext = createContext<HelpApi | null>(null);

interface GlossaryEntry {
  /** Stable anchor id — also what {@link InfoHint}'s `term` prop matches. */
  id: string;
  term: string;
  plain: string;
  detail?: string;
}

/** Plain product language first, technical detail second. */
const GLOSSARY: GlossaryEntry[] = [
  {
    id: "dataset",
    term: "Dataset",
    plain:
      "A fixed set of example inputs that defines the behaviour you expect from the system.",
    detail:
      "Each case can carry an expected answer, expected retrieval ids (RAG), or an expected tool trajectory (agent). Datasets are versioned and immutable.",
  },
  {
    id: "system-version",
    term: "System version",
    plain:
      "One configuration of your AI system — a model, prompt, and settings. You compare a baseline against a candidate.",
    detail:
      "Baseline is what's in production today; candidate is the change you want to ship.",
  },
  {
    id: "experiment",
    term: "Experiment",
    plain:
      "Runs the baseline and the candidate over the same dataset so they can be compared fairly.",
    detail:
      "Execution is asynchronous; a durable job in PostgreSQL tracks queued → running → completed / failed.",
  },
  {
    id: "release-policy",
    term: "Release policy",
    plain:
      "The rules that turn a comparison into a PASS or BLOCK — how much each metric is allowed to regress.",
    detail:
      "Thresholds are fractional (0.10 = a 10% regression allowed). Attaching a policy to an experiment is optional; without one, a run is a comparison only.",
  },
  {
    id: "evaluation",
    term: "Output / RAG / agent evaluation",
    plain:
      "Output evaluators score the final answer. RAG evaluators also score what the system retrieved. Agent evaluators score tool selection, arguments, success, and trajectory.",
    detail:
      "All produce a pass rate and a mean score metric through the same pipeline — there is no separate RAG or agent runner.",
  },
  {
    id: "pass",
    term: "PASS",
    plain:
      "Every gated metric stayed within the release policy. The candidate is safe to ship on this evidence.",
  },
  {
    id: "block",
    term: "BLOCK",
    plain:
      "At least one metric regressed beyond the policy, with statistical evidence strong enough to confirm it. The release is stopped.",
  },
  {
    id: "inconclusive",
    term: "Inconclusive / weak statistical evidence",
    plain:
      "A threshold was breached at the point estimate, but the paired-bootstrap interval or the sample size is not strong enough to confirm a real regression. The run still PASSes, with the breach surfaced as an advisory.",
    detail:
      "Increase repeats or dataset size for a conclusive result. EvalOps never blocks on a breach it cannot confirm.",
  },
  {
    id: "statistical-evidence",
    term: "Statistical evidence",
    plain:
      "For each metric, EvalOps pairs every baseline run with the candidate run for the same case and repeat, then computes a 95% confidence interval for the change with a deterministic paired bootstrap.",
    detail:
      "The interval — not the raw average — decides whether a threshold breach is real enough to BLOCK. All of it is backend-computed; the dashboard only formats it.",
  },
  {
    id: "regressing-case",
    term: "Regressing case",
    plain:
      "A single dataset case where the candidate did worse than the baseline: an evaluator went from pass to fail, a graded score dropped, or the candidate hit a provider or tool error the baseline did not.",
    detail:
      "Diagnostics group regressing cases by category to explain a BLOCK. They are descriptive only — they never change the PASS/BLOCK decision.",
  },
  {
    id: "production-traces",
    term: "Production traces",
    plain:
      "Real interactions captured from a running system. You can promote a selection of them into a replay dataset.",
    detail:
      "Promotion copies each trace's input and any recorded reference; it never mutates the traces.",
  },
  {
    id: "judge-calibration",
    term: "Judge calibration",
    plain:
      "Measures how often a configured LLM judge agrees with human labels, so you know how far to trust it.",
    detail:
      "Calibration is measurement only — a low agreement rate never blocks a release or disables the judge.",
  },
];

export function HelpProvider({ children }: { children: ReactNode }) {
  const [open, setOpen] = useState(false);
  const [targetId, setTargetId] = useState<string | undefined>(undefined);
  const openHelp = useCallback((term?: string) => {
    setTargetId(term);
    setOpen(true);
  }, []);
  const value = useMemo(() => ({ openHelp }), [openHelp]);

  return (
    <HelpContext.Provider value={value}>
      {children}
      <Drawer open={open} onClose={() => setOpen(false)} title="EvalOps help">
        <HelpBody targetId={open ? targetId : undefined} />
      </Drawer>
    </HelpContext.Provider>
  );
}

/**
 * Split out so the scroll/focus effect only runs while the drawer is open —
 * `targetId` is `undefined` while closed, so re-opening with no term (the
 * plain Help button) never re-triggers a stale scroll.
 */
function HelpBody({ targetId }: { targetId: string | undefined }) {
  const entryRefs = useRef(new Map<string, HTMLElement>());

  useEffect(() => {
    if (!targetId) return;
    const node = entryRefs.current.get(targetId);
    // Deferred one tick: <Drawer>'s own mount effect focuses its panel after
    // this component's children effects run (effects fire child-first), so
    // focusing synchronously here would just be overwritten by it. A 0ms
    // timeout runs after that settles, without a fixed animation-frame
    // dependency.
    const timer = setTimeout(() => {
      node?.scrollIntoView({ block: "start" });
      node?.focus();
    }, 0);
    return () => clearTimeout(timer);
  }, [targetId]);

  return (
    <div className="flex flex-col gap-5">
      <p className="text-[15px] leading-relaxed text-fg-muted">
        EvalOps compares a candidate AI system against the one in production
        and blocks quality, reliability, latency, and cost regressions before
        release. The core flow is{" "}
        <span className="font-medium text-fg">
          Dataset → System versions → Experiment → Evaluation → Release
          decision
        </span>
        .
      </p>
      <dl className="flex flex-col divide-y divide-border">
        {GLOSSARY.map((entry) => (
          <div
            key={entry.id}
            ref={(node) => {
              if (node) entryRefs.current.set(entry.id, node);
              else entryRefs.current.delete(entry.id);
            }}
            tabIndex={-1}
            className={cn(
              "flex flex-col gap-1 rounded-md py-3 outline-none",
              targetId === entry.id && "-mx-2 bg-accent/5 px-2 ring-1 ring-accent/40",
            )}
          >
            <dt className="text-[15px] font-semibold text-fg">{entry.term}</dt>
            <dd className="text-[14px] leading-relaxed text-fg-muted">
              {entry.plain}
              {entry.detail ? (
                <span className="mt-1 block text-[13px] text-fg-subtle">
                  {entry.detail}
                </span>
              ) : null}
            </dd>
          </div>
        ))}
      </dl>
    </div>
  );
}

/** `{ openHelp }`. No-op outside a provider. */
export function useHelp(): HelpApi {
  return useContext(HelpContext) ?? { openHelp: () => {} };
}
