import { Badge } from "@/components/ui/badge";
import { CopyButton } from "@/components/ui/copy-button";
import { TBody, TD, TH, THead, TR, Table } from "@/components/ui/table";
import type { JudgeCalibration, JudgeCalibrationCase } from "@/lib/api/types";
import { cn } from "@/lib/cn";
import { formatDateTime } from "@/lib/format";

/** Backend fraction (0..1) as a percentage, or "N/A" for an undefined metric.
 * This only *formats* a backend value -- it never recomputes a metric. */
function rateOrNA(value: number | null): string {
  return value === null ? "N/A" : `${(value * 100).toFixed(1)}%`;
}

function truncate(text: string, max = 140): string {
  return text.length > max ? `${text.slice(0, max)}…` : text;
}

function VerdictBadge({ pass }: { pass: boolean }) {
  return (
    <Badge tone={pass ? "pass" : "block"}>{pass ? "Pass" : "Fail"}</Badge>
  );
}

function MetricStat({
  label,
  value,
  hint,
}: {
  label: string;
  value: string;
  hint?: string;
}) {
  return (
    <div className="flex flex-col gap-0.5 rounded-md border border-border bg-surface px-3 py-2">
      <span className="text-[11px] font-medium uppercase tracking-wide text-fg-subtle">
        {label}
      </span>
      <span className="text-lg font-semibold tabular-nums text-fg">{value}</span>
      {hint ? <span className="text-[11px] text-fg-subtle">{hint}</span> : null}
    </div>
  );
}

function CaseRow({ index, case: c }: { index: number; case: JudgeCalibrationCase }) {
  const failed = c.judge_pass === null;
  return (
    <TR
      className={cn(failed && "border-l-2 border-l-warn bg-warn/5")}
      data-testid={failed ? "calibration-case-failed" : "calibration-case"}
    >
      <TD className="text-right tabular-nums text-fg-subtle">{index + 1}</TD>
      <TD className="max-w-[16rem] align-top text-fg-muted">
        <p className="whitespace-pre-wrap break-words">{truncate(c.input)}</p>
      </TD>
      <TD className="max-w-[16rem] align-top text-fg-muted">
        <p className="whitespace-pre-wrap break-words">{truncate(c.output)}</p>
      </TD>
      <TD className="align-top">
        <VerdictBadge pass={c.human_pass} />
      </TD>
      <TD className="align-top">
        {failed ? (
          <Badge tone="warn">Judge failed</Badge>
        ) : (
          <VerdictBadge pass={c.judge_pass as boolean} />
        )}
      </TD>
      <TD className="align-top tabular-nums text-fg-muted">
        {c.judge_score === null ? "N/A" : c.judge_score.toFixed(2)}
      </TD>
      <TD className="max-w-[18rem] align-top text-[13px] text-fg-muted">
        {failed ? (
          <span className="text-warn">{c.error}</span>
        ) : (
          (c.judge_reasoning ?? "—")
        )}
      </TD>
    </TR>
  );
}

export function CalibrationResult({
  calibration,
}: {
  calibration: JudgeCalibration;
}) {
  const m = calibration.metrics;

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-col gap-1">
        <span className="text-[11px] font-semibold uppercase tracking-[0.08em] text-fg-subtle">
          Calibration result
        </span>
        <div className="flex flex-wrap items-center gap-x-2 gap-y-1 text-sm text-fg">
          <span className="font-medium">{calibration.judge_name}</span>
          <span className="text-fg-subtle">·</span>
          <span className="font-mono text-[13px]">
            {calibration.judge_provider}/{calibration.judge_model}
          </span>
          <span className="text-fg-subtle">·</span>
          <span className="text-fg-muted">
            temperature {calibration.judge_temperature}
          </span>
          <span className="text-fg-subtle">·</span>
          <span className="text-fg-muted">rubric {calibration.rubric_id}</span>
        </div>
        <div className="flex flex-wrap items-center gap-x-2 gap-y-1 text-[13px] text-fg-subtle">
          <span>Run {formatDateTime(calibration.created_at)}</span>
          <span aria-hidden>·</span>
          <code className="font-mono">{calibration.id}</code>
          <CopyButton value={calibration.id} label="Copy ID" />
        </div>
      </div>

      <p className="rounded-md border border-border bg-surface-raised px-3 py-2 text-xs text-fg-muted">
        This measures how often the LLM judge agrees with the human labels. It{" "}
        <span className="font-medium text-fg">
          does not affect release gating
        </span>{" "}
        — a low agreement rate never blocks a release or disables the judge. The{" "}
        <span className="font-mono">{m.failures}</span> failed judge call
        {m.failures === 1 ? "" : "s"} {m.failures === 1 ? "is" : "are"} excluded
        from every metric below; undefined metrics show as{" "}
        <span className="font-medium text-fg">N/A</span>.
      </p>

      <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
        <MetricStat
          label="Agreement"
          value={rateOrNA(m.agreement_rate)}
          hint={`${m.agreements} of ${m.scored} scored`}
        />
        <MetricStat
          label="Scored / Failed / Total"
          value={`${m.scored} / ${m.failures} / ${m.total}`}
        />
        <MetricStat label="Precision" value={rateOrNA(m.precision)} />
        <MetricStat label="Recall" value={rateOrNA(m.recall)} />
        <MetricStat label="F1" value={rateOrNA(m.f1)} />
        <MetricStat
          label="True pos / True neg"
          value={`${m.true_positives} / ${m.true_negatives}`}
        />
        <MetricStat
          label="False pos / False neg"
          value={`${m.false_positives} / ${m.false_negatives}`}
        />
      </div>

      <div className="flex flex-col gap-2">
        <span className="text-[11px] font-semibold uppercase tracking-[0.08em] text-fg-subtle">
          Per-example: human verdict vs judge verdict
        </span>
        <Table>
          <THead>
            <TR>
              <TH className="text-right">#</TH>
              <TH>Input</TH>
              <TH>System output</TH>
              <TH>Human</TH>
              <TH>Judge</TH>
              <TH>Score</TH>
              <TH>Reasoning / error</TH>
            </TR>
          </THead>
          <TBody>
            {calibration.cases.map((c, index) => (
              <CaseRow key={index} index={index} case={c} />
            ))}
          </TBody>
        </Table>
      </div>
    </div>
  );
}

export function CalibrationSummaryRow({
  calibration,
  selected,
  onSelect,
}: {
  calibration: JudgeCalibration;
  selected: boolean;
  onSelect: () => void;
}) {
  const m = calibration.metrics;
  return (
    <button
      type="button"
      onClick={onSelect}
      aria-pressed={selected}
      className={cn(
        "flex w-full flex-wrap items-center justify-between gap-x-4 gap-y-1 rounded-lg border bg-surface p-3 text-left transition-colors hover:bg-surface-raised focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
        selected ? "border-accent" : "border-border",
      )}
    >
      <span className="flex min-w-0 flex-col">
        <span className="truncate text-sm font-medium text-fg">
          {calibration.judge_name}{" "}
          <span className="font-mono text-[12px] font-normal text-fg-subtle">
            {calibration.judge_provider}/{calibration.judge_model}
          </span>
        </span>
        <span className="text-[12px] text-fg-subtle">
          {formatDateTime(calibration.created_at)}
        </span>
      </span>
      <span className="flex shrink-0 items-center gap-3 text-[13px] tabular-nums text-fg-muted">
        <span>
          Agreement{" "}
          <span className="font-semibold text-fg">
            {rateOrNA(m.agreement_rate)}
          </span>
        </span>
        <span>
          {m.scored}/{m.total} scored
        </span>
        {m.failures > 0 ? <Badge tone="warn">{m.failures} failed</Badge> : null}
      </span>
    </button>
  );
}
