"use client";

import { AlertTriangle, RefreshCw } from "lucide-react";

interface PageErrorProps {
  error: Error & { digest?: string };
  reset: () => void;
}

export function PageError({ error, reset }: PageErrorProps) {
  return (
    <div className="flex min-h-[40vh] flex-col items-center justify-center gap-6 text-center">
      <div className="flex size-14 items-center justify-center rounded-full bg-danger-soft">
        <AlertTriangle className="size-6 text-destructive" />
      </div>
      <div>
        <div className="text-lg font-semibold text-foreground">Something went wrong</div>
        <p className="mt-2 max-w-sm text-sm leading-7 text-muted-foreground">
          {error.message?.includes("API request failed")
            ? "Failed to load data from the backend. The service may be starting up — try again in a moment."
            : "An unexpected error occurred. Try refreshing, or contact Owen if the issue persists."}
        </p>
        {error.digest && (
          <p className="mt-1 font-mono text-[10px] text-muted-foreground">ref: {error.digest}</p>
        )}
      </div>
      <button
        onClick={reset}
        className="inline-flex items-center gap-2 rounded-xl bg-accent px-5 py-2.5 text-sm font-semibold text-white shadow-[0_4px_14px_rgba(58,134,255,0.30)] transition hover:bg-accent/90"
      >
        <RefreshCw className="size-4" />
        Try again
      </button>
    </div>
  );
}
