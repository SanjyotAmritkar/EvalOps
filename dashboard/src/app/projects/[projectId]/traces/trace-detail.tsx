"use client";

import { Badge } from "@/components/ui/badge";
import { CodeBlock } from "@/components/ui/code-block";
import { CopyButton } from "@/components/ui/copy-button";
import {
  DefinitionItem,
  DefinitionList,
} from "@/components/ui/definition-list";
import { formatDateTime } from "@/lib/format";
import type { ProductionTrace } from "@/lib/api/types";

function formatLatency(ms: number | null): string {
  return ms === null ? "—" : `${Math.round(ms)} ms`;
}

function formatCost(usd: number | null): string {
  return usd === null ? "—" : `$${usd.toFixed(4)}`;
}

export function TraceDetail({
  trace,
  systemVersionLabel,
  systemVersionHref,
  onClose,
}: {
  trace: ProductionTrace;
  systemVersionLabel: string;
  systemVersionHref: string | null;
  onClose: () => void;
}) {
  const hasReference =
    trace.reference_output !== null && trace.reference_output.trim() !== "";
  const metadataText = JSON.stringify(trace.metadata ?? {}, null, 2);
  const hasMetadata = Object.keys(trace.metadata ?? {}).length > 0;

  return (
    <section
      aria-label="Trace detail"
      className="flex flex-col gap-5 rounded-lg border border-border bg-surface p-5"
    >
      <div className="flex items-start justify-between gap-3">
        <div className="flex flex-col gap-1">
          <span className="text-[11px] font-semibold uppercase tracking-[0.08em] text-fg-subtle">
            Production trace
          </span>
          <span className="text-sm text-fg-muted">
            Captured {formatDateTime(trace.created_at)}
          </span>
        </div>
        <button
          type="button"
          onClick={onClose}
          className="text-sm text-accent transition-colors hover:underline"
        >
          Close
        </button>
      </div>

      <div className="flex flex-col gap-2">
        <span className="text-[13px] font-medium text-fg-subtle">Input</span>
        <CodeBlock>{trace.input}</CodeBlock>
      </div>

      <div className="flex flex-col gap-2">
        <span className="text-[13px] font-medium text-fg-subtle">
          Production output
        </span>
        <p className="rounded-md border border-warn/30 bg-warn/5 px-3 py-2 text-xs text-fg-muted">
          This is the{" "}
          <span className="font-medium text-fg">
            historical output from the live system
          </span>{" "}
          at the time of this interaction. It is{" "}
          <span className="font-medium text-fg">not</span> evaluation ground
          truth and is never used as the expected answer when this trace is
          replayed.
        </p>
        {trace.error !== null ? (
          <CodeBlock label="error" className="border-block/40">
            {trace.error}
          </CodeBlock>
        ) : trace.output === "" ? (
          <p className="text-sm text-fg-subtle">
            No output was recorded for this interaction.
          </p>
        ) : (
          <CodeBlock>{trace.output}</CodeBlock>
        )}
      </div>

      <div className="flex flex-col gap-2">
        <div className="flex items-center gap-2">
          <span className="text-[13px] font-medium text-fg-subtle">
            Reference output
          </span>
          <Badge tone={hasReference ? "neutral" : "warn"}>
            {hasReference ? "recorded" : "none"}
          </Badge>
        </div>
        {hasReference ? (
          <>
            <p className="text-xs text-fg-muted">
              The known-good answer recorded for this interaction.
              Reference-based evaluators compare a replayed candidate against{" "}
              <span className="font-medium text-fg">this</span> — never against
              the production output above.
            </p>
            <CodeBlock>{trace.reference_output}</CodeBlock>
          </>
        ) : (
          <p className="text-xs text-fg-muted">
            No reference was recorded. This trace can still be promoted and
            replayed, but reference-based evaluators (exact match, contains) will
            have nothing to compare against for this case. EvalOps never
            substitutes the production output as a reference.
          </p>
        )}
      </div>

      <DefinitionList>
        <DefinitionItem term="System version">
          {systemVersionHref ? (
            <a
              href={systemVersionHref}
              className="text-fg transition-colors hover:text-accent"
            >
              {systemVersionLabel}
            </a>
          ) : (
            systemVersionLabel
          )}
        </DefinitionItem>
        <DefinitionItem term="Latency">
          <span className="tabular-nums">{formatLatency(trace.latency_ms)}</span>
        </DefinitionItem>
        <DefinitionItem term="Cost">
          <span className="tabular-nums">{formatCost(trace.cost_usd)}</span>
        </DefinitionItem>
        <DefinitionItem term="Status">
          {trace.error !== null ? (
            <Badge tone="block">error</Badge>
          ) : (
            <Badge tone="pass">completed</Badge>
          )}
        </DefinitionItem>
        <DefinitionItem term="Origin">
          <Badge tone="neutral">{trace.origin}</Badge>
        </DefinitionItem>
        <DefinitionItem term="Trace ID">
          <span className="inline-flex items-center gap-2">
            <code className="font-mono text-xs text-fg-muted">{trace.id}</code>
            <CopyButton value={trace.id} />
          </span>
        </DefinitionItem>
      </DefinitionList>

      <div className="flex flex-col gap-2">
        <span className="text-[13px] font-medium text-fg-subtle">Metadata</span>
        {hasMetadata ? (
          <CodeBlock>{metadataText}</CodeBlock>
        ) : (
          <p className="text-sm text-fg-subtle">
            No metadata was attached to this trace.
          </p>
        )}
      </div>
    </section>
  );
}
