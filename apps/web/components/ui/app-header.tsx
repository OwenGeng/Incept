"use client";

/**
 * AppHeader — unified page/section header for all Incept products.
 *
 * variant="header"  — sticky bar at the top of a flex-col section (Studio style)
 *                     left: mobile-menu button + title
 *                     right: Feedback + Docs buttons
 *
 * variant="page"    — embedded at the top of scrollable page content (Scout style)
 *                     title + subtitle + optional tab rows (scope / dataset / page)
 *                     right: Feedback + Docs buttons
 */

import Link from "next/link";
import type { Route } from "next";
import { Menu } from "lucide-react";
import { cn } from "@/lib/utils";
import { FeedbackButton, DocsButton } from "@/components/ui/feedback-button";

type NavTab = { label: string; href: string };

export interface AppHeaderProps {
  title: string;
  subtitle?: string;

  /**
   * "header" — renders as a <header> bar with border-b (Incept sticky header)
   * "page"   — renders as a <div> embedded in scrollable content (Scout Topbar)
   * @default "header"
   */
  variant?: "header" | "page";

  /** Show Feedback + Docs action buttons on the right @default true */
  showActions?: boolean;

  /** Mobile hamburger menu callback — only relevant in "header" variant */
  onMobileMenuOpen?: () => void;

  // ── Tab rows (for "page" variant, i.e. Scout) ────────────────────────────────
  activeHref?: string;
  pageTabs?: NavTab[];
  scopeTabs?: NavTab[];
  activeScopeHref?: string;
  datasetTabs?: NavTab[];
  activeDatasetHref?: string;
}

export function AppHeader({
  title,
  subtitle,
  variant = "header",
  showActions = true,
  onMobileMenuOpen,
  activeHref,
  pageTabs,
  scopeTabs,
  activeScopeHref,
  datasetTabs,
  activeDatasetHref,
}: AppHeaderProps) {
  if (variant === "header") {
    // ── Incept-style: single horizontal row ───────────────────────────────────
    return (
      <header className="flex shrink-0 items-center justify-between gap-4 border-b border-border bg-background px-7 py-4 max-[860px]:px-4">
        <div className="flex items-center gap-3">
          {onMobileMenuOpen && (
            <button
              type="button"
              onClick={onMobileMenuOpen}
              className="hidden max-[980px]:flex items-center justify-center size-9 rounded-xl border border-border bg-card text-muted-foreground transition hover:text-foreground"
            >
              <Menu className="size-4" />
            </button>
          )}
          <h1 className="text-2xl font-semibold tracking-tight text-foreground">{title}</h1>
        </div>
        {showActions && (
          <div className="flex items-center gap-2">
            <FeedbackButton />
            <DocsButton />
          </div>
        )}
      </header>
    );
  }

  // ── Scout-style: title + subtitle + optional tab rows ────────────────────────
  return (
    <div className="mb-8 border-b border-border pb-5">
      <div className="flex items-start justify-between gap-4 pt-1">
        <div>
          <div className="text-[28px] font-semibold tracking-tight text-foreground">{title}</div>
          {subtitle && (
            <div className="mt-1 text-sm text-muted-foreground">{subtitle}</div>
          )}
        </div>
        {showActions && (
          <div className="flex items-center gap-2 pt-1.5 shrink-0">
            <FeedbackButton />
            <DocsButton />
          </div>
        )}
      </div>

      {scopeTabs?.length ? (
        <div className="mt-6 flex flex-wrap gap-2">
          {scopeTabs.map((tab) => (
            <Link
              key={tab.href}
              href={tab.href as Route}
              className={cn(
                "rounded-xl border px-3.5 py-2 text-sm font-medium transition",
                activeScopeHref === tab.href
                  ? "border-accent bg-accent text-accent-foreground shadow-[0_3px_10px_rgba(53,111,236,0.25)]"
                  : "border-border bg-card text-muted-foreground hover:border-accent hover:text-foreground",
              )}
            >
              {tab.label}
            </Link>
          ))}
        </div>
      ) : null}

      {datasetTabs?.length ? (
        <div className="mt-4 flex flex-wrap gap-2">
          {datasetTabs.map((tab) => (
            <Link
              key={tab.href}
              href={tab.href as Route}
              className={cn(
                "rounded-xl border px-3.5 py-2 text-sm font-medium transition",
                activeDatasetHref === tab.href
                  ? "border-accent bg-accent text-accent-foreground shadow-[0_3px_10px_rgba(53,111,236,0.25)]"
                  : "border-border bg-card text-muted-foreground hover:border-accent hover:text-foreground",
              )}
            >
              {tab.label}
            </Link>
          ))}
        </div>
      ) : null}

      {activeHref && pageTabs?.length ? (
        <div className="mt-5 flex items-center gap-5">
          {pageTabs.map((tab) => (
            <Link
              key={tab.href}
              href={tab.href as Route}
              className={cn(
                "border-b-2 border-transparent px-0 py-2.5 text-sm font-medium transition",
                activeHref === tab.href
                  ? "border-accent text-foreground font-semibold"
                  : "text-muted-foreground hover:text-foreground",
              )}
            >
              {tab.label}
            </Link>
          ))}
        </div>
      ) : null}
    </div>
  );
}
