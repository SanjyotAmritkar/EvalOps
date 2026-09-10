"use client";

import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import { Drawer } from "@/components/ui/drawer";

interface HelpApi {
  openHelp: () => void;
}

const HelpContext = createContext<HelpApi | null>(null);

interface GlossaryEntry {
  term: string;
  plain: string;
  detail?: string;
}

/** Plain product language first, technical detail second. */
const GLOSSARY: GlossaryEntry[] = [
  {
    term: "Dataset",
    plain:
      "A fixed set of example inputs that defines the behaviour you expect from the system.",
    detail:
      "Each case can carry an expected answer, expected retrieval ids (RAG), or an expected tool trajectory (agent). Datasets are versioned and immutable.",
  },
  {
    term: "System version",
    plain:
      "One configuration of your AI system — a model, prompt, and settings. You compare a baseline against a candidate.",
    detail:
      "Baseline is what's in production today; candidate is the change you want to ship.",
  },
  {
    term: "Experiment",
    plain:
      "Runs the baseline and the candidate over the same dataset so they can be compared fairly.",
    detail:
      "Execution is asynchronous; a durable job in PostgreSQL tracks queued → running → completed / failed.",
  },
  {
    term: "Release policy",
    plain:
      "The rules that turn a comparison into a PASS or BLOCK — how much each metric is allowed to regress.",
    detail:
      "Thresholds are fractional (0.10 = a 10% regression allowed). Attaching a policy to an experiment is optional; without one, a run is a comparison only.",
  },
  {
    term: "Output / RAG / agent evaluation",
    plain:
      "Output evaluators score the final answer. RAG evaluators also score what the system retrieved. Agent evaluators score tool selection, arguments, success, and trajectory.",
    detail:
      "All produce a pass rate and a mean score metric through the same pipeline — there is no separate RAG or agent runner.",
  },
  {
    term: "PASS",
    plain:
      "Every gated metric stayed within the release policy. The candidate is safe to ship on this evidence.",
  },
  {
    term: "BLOCK",
    plain:
      "At least one metric regressed beyond the policy, with statistical evidence strong enough to confirm it. The release is stopped.",
  },
  {
    term: "Inconclusive / weak statistical evidence",
    plain:
      "A threshold was breached at the point estimate, but the paired-bootstrap interval or the sample size is not strong enough to confirm a real regression. The run still PASSes, with the breach surfaced as an advisory.",
    detail:
      "Increase repeats or dataset size for a conclusive result. EvalOps never blocks on a breach it cannot confirm.",
  },
  {
    term: "Production traces",
    plain:
      "Real interactions captured from a running system. You can promote a selection of them into a replay dataset.",
    detail:
      "Promotion copies each trace's input and any recorded reference; it never mutates the traces.",
  },
  {
    term: "Judge calibration",
    plain:
      "Measures how often a configured LLM judge agrees with human labels, so you know how far to trust it.",
    detail:
      "Calibration is measurement only — a low agreement rate never blocks a release or disables the judge.",
  },
];

export function HelpProvider({ children }: { children: ReactNode }) {
  const [open, setOpen] = useState(false);
  const openHelp = useCallback(() => setOpen(true), []);
  const value = useMemo(() => ({ openHelp }), [openHelp]);

  return (
    <HelpContext.Provider value={value}>
      {children}
      <Drawer open={open} onClose={() => setOpen(false)} title="EvalOps help">
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
              <div key={entry.term} className="flex flex-col gap-1 py-3">
                <dt className="text-[15px] font-semibold text-fg">
                  {entry.term}
                </dt>
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
      </Drawer>
    </HelpContext.Provider>
  );
}

/** `{ openHelp }`. No-op outside a provider. */
export function useHelp(): HelpApi {
  return useContext(HelpContext) ?? { openHelp: () => {} };
}
