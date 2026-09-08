import type { ReactNode } from "react";
import { AlertIcon } from "@/components/icons";
import { Button } from "@/components/ui/button";

export function ErrorState({
  title = "Something went wrong",
  message,
  onRetry,
}: {
  title?: string;
  message?: ReactNode;
  onRetry?: () => void;
}) {
  return (
    <div className="flex flex-col items-start gap-3 rounded-lg border border-block/30 bg-surface px-6 py-8">
      <div className="flex items-center gap-2 text-block">
        <AlertIcon />
        <p className="text-sm font-medium">{title}</p>
      </div>
      {message ? <p className="text-sm text-fg-muted">{message}</p> : null}
      {onRetry ? (
        <Button variant="secondary" onClick={onRetry}>
          Try again
        </Button>
      ) : null}
    </div>
  );
}
