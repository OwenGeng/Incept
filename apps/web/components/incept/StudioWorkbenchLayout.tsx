"use client";

import { PanelRight } from "lucide-react";
import type { ReactNode } from "react";
import { cn } from "@/lib/utils";

interface StudioWorkbenchLayoutProps {
  title: ReactNode;
  badge?: ReactNode;
  headerActions?: ReactNode;
  threadControls?: ReactNode;
  children: ReactNode;
  bottomBar?: ReactNode;
  rightPanel?: ReactNode;
  rightPanelOpen: boolean;
  onToggleRightPanel?: () => void;
}

export function StudioWorkbenchLayout({
  title,
  badge,
  headerActions,
  threadControls,
  children,
  bottomBar,
  rightPanel,
  rightPanelOpen,
  onToggleRightPanel,
}: StudioWorkbenchLayoutProps) {
  return (
    <div className="flex h-screen min-w-0 flex-1 overflow-hidden bg-background">
      <div className="flex min-w-0 flex-1 flex-col overflow-hidden">
        <div className="shrink-0 border-b px-8 pb-0 pt-6">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2.5">
              <h1 className="font-display text-2xl font-semibold">{title}</h1>
              {badge}
            </div>
            <div className="flex items-center gap-2 pb-1">
              {headerActions}
              {onToggleRightPanel ? (
                <button
                  type="button"
                  onClick={onToggleRightPanel}
                  className={cn(
                    "flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-semibold transition-all",
                    rightPanelOpen
                      ? "bg-foreground text-background hover:opacity-80"
                      : "bg-muted text-foreground hover:bg-muted/80",
                  )}
                >
                  <PanelRight className="size-3.5" />
                  Assets
                </button>
              ) : null}
            </div>
          </div>
          {threadControls ? <div className="mt-5 flex flex-wrap items-center gap-3 pb-4">{threadControls}</div> : null}
        </div>

        <div className="min-h-0 flex-1 overflow-y-auto px-8 py-7">
          {children}
        </div>

        {bottomBar ? (
          <div className="relative min-h-0 shrink-0 overflow-visible bg-background px-6 pb-6 pt-3">
            <div className="pointer-events-none absolute inset-x-0 bottom-full h-16 bg-gradient-to-t from-background to-transparent" />
            {bottomBar}
          </div>
        ) : null}
      </div>

      {rightPanelOpen && rightPanel ? (
        <aside className="flex w-80 shrink-0 flex-col overflow-hidden border-l border-border bg-card">
          {rightPanel}
        </aside>
      ) : null}
    </div>
  );
}
