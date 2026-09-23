"use client";

import { useState } from "react";
import { ArrowUp, Loader2, Plus } from "lucide-react";
import { cn } from "@/lib/utils";

interface WorkbenchFooterActionsProps {
  onUpload: () => void;
  onChooseFromLibrary?: () => void;
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
  onChooseFromLibrary,
  onPrimary,
  uploadTitle,
  uploadDisabled = false,
  uploadActive = false,
  primaryDisabled = false,
  primaryLoading = false,
  primaryLabel,
}: WorkbenchFooterActionsProps) {
  const [sourceMenuOpen, setSourceMenuOpen] = useState(false);

  function chooseLocal() {
    setSourceMenuOpen(false);
    onUpload();
  }

  function chooseLibrary() {
    setSourceMenuOpen(false);
    onChooseFromLibrary?.();
  }

  return (
    <div className="flex items-center gap-1.5">
      <div className="relative">
        <button
          type="button"
          title={uploadTitle}
          onClick={() => onChooseFromLibrary ? setSourceMenuOpen((open) => !open) : onUpload()}
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
        {sourceMenuOpen && !uploadDisabled ? (
          <div className="absolute bottom-10 right-0 z-50 w-48 overflow-hidden rounded-xl border bg-popover p-1 shadow-lg">
            <button type="button" onClick={chooseLocal} className="w-full rounded-lg px-3 py-2 text-left text-xs font-medium hover:bg-muted">Upload from computer</button>
            <button type="button" onClick={chooseLibrary} className="w-full rounded-lg px-3 py-2 text-left text-xs font-medium hover:bg-muted">Choose from Library</button>
          </div>
        ) : null}
      </div>
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
