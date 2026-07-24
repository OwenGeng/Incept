"use client";

import { ArrowUp, Loader2, Plus } from "lucide-react";
import { cn } from "@/lib/utils";

interface WorkbenchFooterActionsProps {
  onUpload: () => void;
  onPrimary: () => void;
  uploadTitle?: string;
  uploadDisabled?: boolean;
  uploadActive?: boolean;
  primaryDisabled?: boolean;
  primaryLoading?: boolean;
  primaryLabel?: string;
}

export function WorkbenchFooterActions({
  onUpload,
  onPrimary,
  uploadTitle,
  uploadDisabled = false,
  uploadActive = false,
  primaryDisabled = false,
  primaryLoading = false,
  primaryLabel,
}: WorkbenchFooterActionsProps) {
  return (
    <div className="flex items-center gap-1.5">
      <button
        type="button"
        title={uploadTitle}
        onClick={onUpload}
        disabled={uploadDisabled}
        className={cn(
          "relative flex size-8 items-center justify-center rounded-full transition-colors",
          uploadDisabled
            ? "cursor-not-allowed text-muted-foreground/40"
            : uploadActive
              ? "bg-soft-accent text-accent"
              : "text-muted-foreground hover:bg-muted hover:text-foreground",
        )}
      >
        <Plus className="size-4" />
      </button>
      <button
        type="button"
        onClick={onPrimary}
        disabled={primaryDisabled}
        className={cn(
          "flex items-center justify-center rounded-full transition-all",
          primaryLabel ? "h-9 px-4 text-xs font-semibold" : "size-9",
          primaryDisabled
            ? "cursor-not-allowed bg-muted text-muted-foreground"
            : "bg-foreground text-background shadow-md hover:opacity-80",
        )}
      >
        {primaryLoading ? <Loader2 className="size-4 animate-spin" /> : primaryLabel || <ArrowUp className="size-4" />}
      </button>
    </div>
  );
}
