"use client";

import { useParams } from "next/navigation";
import type { ReactNode } from "react";
import { ErrorState } from "@/components/feedback/error-state";
import { LoadingState } from "@/components/feedback/loading-state";
import { BackLink } from "@/components/layout/back-link";
import { PageHeader } from "@/components/layout/page-header";
import { Badge } from "@/components/ui/badge";
import { CodeBlock } from "@/components/ui/code-block";
import { CopyButton } from "@/components/ui/copy-button";
import {
  DefinitionItem,
  DefinitionList,
} from "@/components/ui/definition-list";
import { apiErrorMessage, isNotFound } from "@/lib/api/errors";
import { formatDateTime } from "@/lib/format";
import { formatJson } from "@/lib/json";
import { useSystemVersion } from "@/lib/query/system-versions";

function ConfigSection({
  title,
  value,
}: {
  title: string;
  value: Record<string, unknown> | null;
}) {
  let body: ReactNode;
  if (value === null) {
    body = <p className="text-sm text-fg-subtle">Not set.</p>;
  } else if (Object.keys(value).length === 0) {
    body = <p className="text-sm text-fg-subtle">Empty object.</p>;
  } else {
    const json = formatJson(value);
    body = (
      <CodeBlock label={title} copyValue={json}>
        {json}
      </CodeBlock>
    );
  }
  return (
    <section className="flex flex-col gap-2">
      <h2 className="font-mono text-sm font-semibold text-fg">{title}</h2>
      {body}
    </section>
  );
}

export default function SystemVersionDetailPage() {
  const params = useParams<{
    projectId: string;
    systemVersionId: string;
  }>();
  const projectId = String(params.projectId ?? "");
  const versionId = String(params.systemVersionId ?? "");
  const version = useSystemVersion(versionId);

  const backHref = `/projects/${projectId}/system-versions`;

  if (version.isPending) {
    return (
      <div className="flex flex-col gap-6">
        <BackLink href={backHref} label="System Versions" />
        <LoadingState rows={4} />
      </div>
    );
  }

  if (version.isError || !version.data) {
    const notFound = isNotFound(version.error);
    return (
      <div className="flex flex-col gap-4">
        <BackLink href={backHref} label="System Versions" />
        <ErrorState
          title={
            notFound
              ? "System version not found"
              : "Could not load system version"
          }
          message={
            notFound
              ? "This system version does not exist."
              : apiErrorMessage(version.error, "The API did not respond.")
          }
          onRetry={notFound ? undefined : () => void version.refetch()}
        />
      </div>
    );
  }

  const v = version.data;

  return (
    <div className="flex flex-col gap-6">
      <BackLink href={backHref} label="System Versions" />
      <PageHeader
        title={
          <span className="flex flex-wrap items-center gap-2">
            {v.name}
            <span className="font-mono text-sm font-normal text-fg-muted">
              {v.version}
            </span>
          </span>
        }
      />

      <DefinitionList>
        <DefinitionItem term="Name">{v.name}</DefinitionItem>
        <DefinitionItem term="Version">
          <code className="font-mono text-[13px]">{v.version}</code>
        </DefinitionItem>
        <DefinitionItem term="Provider">
          <Badge tone="neutral">{v.provider}</Badge>
        </DefinitionItem>
        <DefinitionItem term="Model">
          <code className="font-mono text-[13px]">{v.model}</code>
        </DefinitionItem>
        <DefinitionItem term="Created">
          {formatDateTime(v.created_at)}
        </DefinitionItem>
        <DefinitionItem term="ID">
          <span className="inline-flex items-center gap-2">
            <code className="font-mono text-xs text-fg-muted">{v.id}</code>
            <CopyButton value={v.id} />
          </span>
        </DefinitionItem>
      </DefinitionList>

      <section className="flex flex-col gap-2">
        <h2 className="font-mono text-sm font-semibold text-fg">
          prompt_template
        </h2>
        <CodeBlock label="prompt_template" copyValue={v.prompt_template}>
          {v.prompt_template}
        </CodeBlock>
      </section>

      <ConfigSection title="parameters" value={v.parameters} />
      <ConfigSection title="rag_config" value={v.rag_config} />
      <ConfigSection title="tool_policy" value={v.tool_policy} />
    </div>
  );
}
