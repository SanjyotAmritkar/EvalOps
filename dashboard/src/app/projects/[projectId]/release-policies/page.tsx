"use client";

import { useState } from "react";
import { EmptyState } from "@/components/feedback/empty-state";
import { ErrorState } from "@/components/feedback/error-state";
import { LoadingState } from "@/components/feedback/loading-state";
import { PageHeader } from "@/components/layout/page-header";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { TBody, TD, TH, THead, TR, Table } from "@/components/ui/table";
import { apiErrorMessage } from "@/lib/api/errors";
import type { ReleasePolicy } from "@/lib/api/types";
import { describeThreshold, metricLabel } from "@/lib/metric-labels";
import { useReleasePolicies } from "@/lib/query/release-policies";
import { ReleasePolicyForm } from "./release-policy-form";

function PolicyCard({ policy }: { policy: ReleasePolicy }) {
  const thresholds = Object.entries(policy.thresholds);
  return (
    <Card className="flex flex-col gap-3 p-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h3 className="font-medium text-fg">{policy.name}</h3>
        <code className="font-mono text-xs text-fg-subtle">{policy.id}</code>
      </div>

      {thresholds.length === 0 ? (
        <p className="text-sm text-fg-subtle">
          No metric thresholds — this policy blocks nothing on its own.
        </p>
      ) : (
        <Table>
          <THead>
            <TR>
              <TH>Metric</TH>
              <TH>Allowed regression</TH>
            </TR>
          </THead>
          <TBody>
            {thresholds.map(([metric, value]) => (
              <TR key={metric}>
                <TD>
                  <span className="flex flex-col">
                    <span className="font-medium text-fg">
                      {metricLabel(metric)}
                    </span>
                    <span className="font-mono text-[11px] text-fg-subtle">
                      {metric}
                    </span>
                  </span>
                </TD>
                <TD className="text-fg-muted">{describeThreshold(value)}</TD>
              </TR>
            ))}
          </TBody>
        </Table>
      )}

      <p className="text-xs text-fg-subtle">
        Safety-violation limit:{" "}
        <span className="font-mono tabular-nums">
          {policy.max_safety_violations}
        </span>
        . Safety metrics are not evaluated yet, so this limit currently has no
        effect.
      </p>
    </Card>
  );
}

export default function ReleasePoliciesPage() {
  const policies = useReleasePolicies();
  const [showForm, setShowForm] = useState(false);

  const list = policies.data ?? [];

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title="Release Policies"
        description="Thresholds that turn a baseline-vs-candidate comparison into a PASS or BLOCK decision."
        actions={
          <Button
            variant={showForm ? "ghost" : "primary"}
            onClick={() => setShowForm((value) => !value)}
          >
            {showForm ? "Close" : "New policy"}
          </Button>
        }
      />

      <p className="rounded-md border border-border bg-surface-raised px-3 py-2 text-xs text-fg-muted">
        Release policies are defined globally and can be attached to experiments
        in any project. Threshold values are fractions:{" "}
        <span className="font-mono">0.10</span> means a 10% adverse change is
        tolerated.
      </p>

      {showForm ? (
        <ReleasePolicyForm onCreated={() => setShowForm(false)} />
      ) : null}

      {policies.isPending ? (
        <LoadingState />
      ) : policies.isError ? (
        <ErrorState
          title="Could not load release policies"
          message={apiErrorMessage(policies.error, "The API did not respond.")}
          onRetry={() => void policies.refetch()}
        />
      ) : list.length === 0 ? (
        <EmptyState
          title="No release policies yet"
          description="Create a policy to gate experiments on regression tolerances."
          action={
            !showForm ? (
              <Button onClick={() => setShowForm(true)}>New policy</Button>
            ) : undefined
          }
        />
      ) : (
        <div className="flex flex-col gap-3">
          {list.map((policy) => (
            <PolicyCard key={policy.id} policy={policy} />
          ))}
        </div>
      )}
    </div>
  );
}
