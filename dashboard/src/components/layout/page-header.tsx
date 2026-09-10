import type { ReactNode } from "react";

/**
 * The one title block per page: a large page title, a plain-language
 * description, and the primary action(s) top-right. Section-level headings on
 * a page use `<h2 className="text-xl ...">` directly.
 */
export function PageHeader({
  eyebrow,
  title,
  description,
  actions,
}: {
  eyebrow?: string;
  title: ReactNode;
  description?: ReactNode;
  actions?: ReactNode;
}) {
  return (
    <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
      <div className="flex min-w-0 flex-col gap-2">
        {eyebrow ? (
          <span className="text-[13px] font-medium tracking-wide text-fg-muted">
            {eyebrow}
          </span>
        ) : null}
        <h1 className="text-[28px] font-semibold leading-tight tracking-tight text-fg sm:text-[32px]">
          {title}
        </h1>
        {description ? (
          <p className="max-w-2xl text-base leading-relaxed text-fg-muted">
            {description}
          </p>
        ) : null}
      </div>
      {actions ? (
        <div className="flex shrink-0 flex-wrap items-center gap-2">{actions}</div>
      ) : null}
    </div>
  );
}
