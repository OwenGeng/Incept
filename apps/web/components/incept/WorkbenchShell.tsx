"use client";

import { Maximize2, Minimize2 } from "lucide-react";
import { forwardRef, useState, type DragEventHandler, type ReactNode } from "react";
import { cn } from "@/lib/utils";

interface WorkbenchShellProps {
  expanded?: boolean;
  onToggleExpanded?: () => void;
  header?: ReactNode;
  body?: ReactNode;
  footer?: ReactNode;
  children?: ReactNode;
  overlay?: ReactNode;
  minimized?: boolean;
  onToggleMinimized?: () => void;
  minimizedContent?: ReactNode;
  viewMode?: "compact" | "standard" | "expanded";
  onViewModeChange?: (mode: "compact" | "standard" | "expanded") => void;
  /** Let the shell grow with its content instead of using the compact/expanded heights. */
  autoHeight?: boolean;
  /** Hide the compact/expanded control when a workspace has no collapsed state. */
  showExpandControl?: boolean;
  className?: string;
  bodyClassName?: string;
  onDragOver?: DragEventHandler<HTMLDivElement>;
  onDragLeave?: DragEventHandler<HTMLDivElement>;
  onDrop?: DragEventHandler<HTMLDivElement>;
}

export const WorkbenchShell = forwardRef<HTMLDivElement, WorkbenchShellProps>(
  function WorkbenchShell(
    {
      expanded = false,
      onToggleExpanded,
      header,
      body,
      footer,
      children,
      overlay,
      minimized = false,
      onToggleMinimized,
      minimizedContent,
      viewMode,
      onViewModeChange,
      autoHeight = false,
      showExpandControl = true,
      className,
      bodyClassName,
      onDragOver,
      onDragLeave,
      onDrop,
    },
    ref,
  ) {
    const [viewMenuOpen, setViewMenuOpen] = useState(false);
    const controlledMode = viewMode ?? (minimized ? "compact" : expanded ? "expanded" : "standard");
    const isControlledView = Boolean(onViewModeChange);
    return (
      <div
        ref={ref}
        className={cn(
          "relative flex flex-col overflow-visible rounded-[28px] border border-border bg-card shadow-[0_8px_32px_rgba(0,0,0,0.08)] transition-all duration-200",
          minimized ? "h-[64px]" : autoHeight ? "h-auto" : expanded ? "h-[520px]" : "h-[300px]",
          className,
        )}
        style={autoHeight ? undefined : { maxHeight: minimized ? "64px" : expanded ? "calc(100svh - 140px)" : "calc(100svh - 260px)" }}
        onDragOver={onDragOver}
        onDragLeave={onDragLeave}
        onDrop={onDrop}
      >
        {minimized ? (
          <div className="flex h-full items-center gap-2 px-3">{minimizedContent}</div>
        ) : (
          <>
            {overlay}

            {isControlledView || onToggleMinimized || showExpandControl ? <div className="absolute right-3 top-3 z-20 flex items-center gap-1.5">
              {isControlledView ? (
                <div className="relative">
                  <button
                    type="button"
                    onClick={() => setViewMenuOpen((open) => !open)}
                    className="inline-flex items-center gap-1.5 rounded-full border border-border bg-background/90 px-2.5 py-1.5 text-[11px] font-medium text-muted-foreground shadow-sm backdrop-blur-sm transition-colors hover:bg-muted hover:text-foreground"
                  >
                    {controlledMode === "expanded" ? <Maximize2 className="size-3.5" /> : <Minimize2 className="size-3.5" />}
                    Composer
                  </button>
                  {viewMenuOpen ? (
                    <div className="absolute right-0 top-[calc(100%+6px)] w-32 overflow-hidden rounded-xl border border-border bg-card p-1 shadow-lg">
                      {(["compact", "standard", "expanded"] as const).map((mode) => (
                        <button
                          key={mode}
                          type="button"
                          onClick={() => {
                            onViewModeChange?.(mode);
                            setViewMenuOpen(false);
                          }}
                          className={cn(
                            "w-full rounded-lg px-2.5 py-2 text-left text-xs capitalize transition-colors hover:bg-muted",
                            controlledMode === mode && "bg-muted font-semibold text-foreground",
                          )}
                        >
                          {mode}
                        </button>
                      ))}
                    </div>
                  ) : null}
                </div>
              ) : onToggleMinimized ? (
                <button
                  type="button"
                  onClick={onToggleMinimized}
                  className="inline-flex items-center gap-1.5 rounded-full border border-border bg-background/90 px-2.5 py-1.5 text-[11px] font-medium text-muted-foreground shadow-sm backdrop-blur-sm transition-colors hover:bg-muted hover:text-foreground"
                >
                  <Minimize2 className="size-3.5" />
                  Minimize
                </button>
              ) : null}
              {!isControlledView && showExpandControl ? <button
                type="button"
                onClick={onToggleExpanded}
                className="inline-flex items-center gap-1.5 rounded-full border border-border bg-background/90 px-2.5 py-1.5 text-[11px] font-medium text-muted-foreground shadow-sm backdrop-blur-sm transition-colors hover:bg-muted hover:text-foreground"
              >
                {expanded ? <Minimize2 className="size-3.5" /> : <Maximize2 className="size-3.5" />}
                {expanded ? "Collapse" : "Expand"}
              </button> : null}
            </div> : null}

            {header ? <div className="shrink-0">{header}</div> : null}

            {children ? (
              children
            ) : (
              <>
                {body ? (
                  <div className={cn("min-h-0 flex-1 overflow-y-auto [scrollbar-width:thin]", bodyClassName)}>
                    {body}
                  </div>
                ) : null}

                {footer ? <div className="shrink-0 border-t border-border">{footer}</div> : null}
              </>
            )}
          </>
        )}
      </div>
    );
  },
);
