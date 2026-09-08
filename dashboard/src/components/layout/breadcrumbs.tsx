import Link from "next/link";
import { Fragment } from "react";
import { ChevronRightIcon } from "@/components/icons";

export interface Crumb {
  label: string;
  href?: string;
}

export function Breadcrumbs({ items }: { items: Crumb[] }) {
  return (
    <nav aria-label="Breadcrumb">
      <ol className="flex flex-wrap items-center gap-1.5 text-sm text-fg-muted">
        {items.map((item, index) => {
          const isLast = index === items.length - 1;
          return (
            <Fragment key={index}>
              {index > 0 ? (
                <li aria-hidden>
                  <ChevronRightIcon
                    width={14}
                    height={14}
                    className="text-fg-subtle"
                  />
                </li>
              ) : null}
              <li>
                {item.href && !isLast ? (
                  <Link
                    href={item.href}
                    className="transition-colors hover:text-fg"
                  >
                    {item.label}
                  </Link>
                ) : (
                  <span
                    className={isLast ? "text-fg" : undefined}
                    aria-current={isLast ? "page" : undefined}
                  >
                    {item.label}
                  </span>
                )}
              </li>
            </Fragment>
          );
        })}
      </ol>
    </nav>
  );
}
