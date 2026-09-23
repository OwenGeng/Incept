"use client";

/**
 * AppSidebar — unified sidebar component for Linglong platform products (Scout, Studio).
 *
 * Supports two navigation modes out of the box:
 *   - href-based  (Next.js Link + pathname, e.g. Scout)
 *   - state-based (onClick callbacks, e.g. Studio)
 *
 * Usage:
 *   <AppSidebar
 *     productName="Scout"
 *     logo="/logo.png"
 *     storageKey="scout"
 *     items={NAV_ITEMS}
 *     isActive={(key) => ...}
 *     user={{ email, name, image, roleLabel }}
 *     onSignOut={...}
 *   />
 */

import { useState, useEffect, useRef } from "react";
import Link from "next/link";
import type { Route } from "next";
import { ChevronLeft, ChevronRight, ChevronDown, LogOut, User } from "lucide-react";
import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar";
import { cn } from "@/lib/utils";

// ── Public types ───────────────────────────────────────────────────────────────

export type SidebarChildItem = {
  key: string;
  label: string;
  /** href-based navigation */
  href?: string;
  /** state-based navigation */
  onClick?: () => void;
};

export type SidebarNavItem =
  | {
      kind: "simple";
      key: string;
      label: string;
      icon: React.ElementType;
      href?: string;
      onClick?: () => void;
      disabled?: boolean;
    }
  | {
      kind: "group";
      key: string;
      label: string;
      icon: React.ElementType;
      children: SidebarChildItem[];
    }
  | {
      kind: "separator";
      key: string;
    };

export type SidebarUser = {
  email?: string | null;
  name?: string | null;
  image?: string | null;
  /** Optional role label shown beneath email */
  roleLabel?: string | null;
};

export type SidebarPrimaryAction = {
  label: string;
  icon: React.ElementType;
  href?: string;
  onClick?: () => void;
  className?: string;
};

export interface AppSidebarProps {
  /** Product name shown in the header — e.g. "Scout", "Studio" */
  productName: string;
  /** Optional brand title shown next to the logo, defaults to "Linglong" */
  brandTitle?: string;
  /** Optional brand subtitle shown under the brand title */
  brandSubtitle?: string;
  /** Optional logo image path (served from /public). Shown left of product name. */
  logo?: string;
  /** localStorage key prefix to avoid state collision between products */
  storageKey?: string;
  items: SidebarNavItem[];
  /** Return true if the item/child with this key is currently active */
  isActive: (key: string) => boolean;
  user?: SidebarUser;
  onSignOut?: () => void;
  topContent?: React.ReactNode;
  /** Product-owned content rendered in the main sidebar region (for focused tools). */
  content?: React.ReactNode;
  /** Expanded width when `content` needs more room than a conventional navigation rail. */
  expandedWidthClassName?: string;
  /** Product's primary creation action. It remains available as an icon when collapsed. */
  primaryAction?: SidebarPrimaryAction;
  /** Accessible label for the primary navigation region. */
  navigationLabel?: string;
  /** Content above the account block, such as product-specific help. */
  footerContent?: React.ReactNode;
  /** Product accent overrides while retaining the shared sidebar structure. */
  activeItemClassName?: string;
  activeIconClassName?: string;
}

// ── Collapsed-mode group flyout ────────────────────────────────────────────────

function GroupFlyout({
  item,
  isActive,
}: {
  item: Extract<SidebarNavItem, { kind: "group" }>;
  isActive: (key: string) => boolean;
}) {
  return (
    <div className="absolute left-[calc(100%+8px)] top-0 z-50 min-w-[190px] rounded-xl border border-border bg-secondary py-2 shadow-lg">
      <div className="px-3 pb-1.5 pt-0.5 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
        {item.label}
      </div>
      {item.children.map((child) => {
        const active = isActive(child.key);
        const cls = cn(
          "flex w-full items-center px-3 py-2 text-[13px] transition",
          active
            ? "bg-soft-accent font-semibold text-foreground"
            : "text-muted-foreground hover:bg-muted hover:text-foreground",
        );
        if (child.href) {
          return (
            <Link key={child.key} href={child.href as Route} className={cls}>
              {child.label}
            </Link>
          );
        }
        return (
          <button key={child.key} type="button" onClick={child.onClick} className={cn(cls, "text-left")}>
            {child.label}
          </button>
        );
      })}
    </div>
  );
}

// ── Main component ─────────────────────────────────────────────────────────────

export function AppSidebar({
  productName,
  brandTitle = "Linglong",
  brandSubtitle,
  logo,
  storageKey = "app",
  items,
  isActive,
  user,
  onSignOut,
  topContent,
  content,
  expandedWidthClassName,
  primaryAction,
  navigationLabel = "Primary navigation",
  footerContent,
  activeItemClassName = "bg-soft-accent font-semibold text-foreground",
  activeIconClassName = "text-accent",
}: AppSidebarProps) {
  const [collapsed, setCollapsed] = useState(false);
  const [mounted, setMounted] = useState(false);
  const [groupOpen, setGroupOpen] = useState<Record<string, boolean>>({});
  const [hoveredGroup, setHoveredGroup] = useState<string | null>(null);
  const hoverTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Hydration-safe: restore persisted state after mount
  useEffect(() => {
    setMounted(true);
    const savedCollapsed = localStorage.getItem(`${storageKey}-sidebar-collapsed`);
    if (savedCollapsed === "true") setCollapsed(true);

    const initialGroupOpen: Record<string, boolean> = {};
    for (const item of items) {
      if (item.kind === "group") {
        const saved = localStorage.getItem(`${storageKey}-sidebar-group-${item.key}`);
        initialGroupOpen[item.key] = saved !== "false"; // default: open
      }
    }
    setGroupOpen(initialGroupOpen);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [storageKey]);

  function toggleCollapsed() {
    const next = !collapsed;
    setCollapsed(next);
    localStorage.setItem(`${storageKey}-sidebar-collapsed`, String(next));
    if (next) setHoveredGroup(null);
  }

  function toggleGroup(key: string) {
    setGroupOpen((prev) => {
      const next = { ...prev, [key]: !prev[key] };
      localStorage.setItem(`${storageKey}-sidebar-group-${key}`, String(next[key]));
      return next;
    });
  }

  const isCollapsed = mounted && collapsed;
  const userLabel = user?.email ?? user?.name ?? "Workspace";
  const PrimaryActionIcon = primaryAction?.icon;

  return (
    <aside
      className={cn(
        "relative z-10 flex h-screen shrink-0 sticky top-0 flex-col border-r border-border bg-white transition-[width] duration-200 ease-in-out",
        isCollapsed ? "w-[64px]" : (expandedWidthClassName ?? "w-[220px]"),
      )}
    >
      {/* ── Collapse / expand toggle ────────────────────────────────────────── */}
      <button
        onClick={toggleCollapsed}
        aria-label={isCollapsed ? "Expand sidebar" : "Collapse sidebar"}
        className="absolute -right-3.5 top-[68px] z-20 flex size-7 items-center justify-center rounded-full border border-border bg-secondary text-muted-foreground shadow-sm transition hover:border-[var(--border-strong)] hover:text-foreground"
      >
        {isCollapsed
          ? <ChevronRight className="size-3.5" />
          : <ChevronLeft className="size-3.5" />
        }
      </button>

      {/* ── Platform + Product header ────────────────────────────────────────── */}
      {isCollapsed ? (
        /* Collapsed: just the logo, links back to portal */
        <Link
          href="/"
          title={brandTitle}
          className="flex shrink-0 items-center justify-center border-b border-border py-[18px] transition hover:bg-muted"
        >
          {logo ? (
            // eslint-disable-next-line @next/next/no-img-element
            <img src={logo} alt={brandTitle} className="size-9 shrink-0 rounded-lg object-contain" />
          ) : (
            <div className="flex size-9 shrink-0 select-none items-center justify-center rounded-xl bg-foreground text-[11px] font-bold tracking-tight text-background">
              LL
            </div>
          )}
        </Link>
      ) : (
        /* Expanded: brand block + optional product sub-label */
        <div className="shrink-0 border-b border-border px-4 py-3">
          <Link
            href="/"
            className="group -mx-1 flex items-center gap-3 rounded-lg px-1 py-1 transition hover:bg-muted"
          >
            {logo ? (
              // eslint-disable-next-line @next/next/no-img-element
              <img src={logo} alt={brandTitle} className="size-8 shrink-0 rounded-lg object-contain" />
            ) : (
              <div className="flex size-8 shrink-0 select-none items-center justify-center rounded-lg bg-foreground text-[10px] font-bold text-background">
                LL
              </div>
            )}
            <span className="min-w-0 truncate text-[15px] font-semibold tracking-tight text-foreground">{brandTitle}{brandSubtitle ? <><span className="text-muted-foreground transition group-hover:text-foreground/80"> </span><span className="text-muted-foreground transition group-hover:text-foreground/80">{brandSubtitle}</span></> : null}</span>
          </Link>
          {productName ? (
            <div className="mt-1.5 px-1">
              <span className="text-[13px] font-semibold tracking-tight text-muted-foreground">
                {productName}
              </span>
            </div>
          ) : null}
        </div>
      )}

      {!isCollapsed && topContent ? (
        <div className="shrink-0 border-b border-border px-4 py-3">
          {topContent}
        </div>
      ) : null}

      {primaryAction && PrimaryActionIcon ? (
        <div className={cn("shrink-0", isCollapsed ? "px-2 py-3" : "px-3 pt-4")}>
          {primaryAction.href ? (
            <Link href={primaryAction.href as Route} title={isCollapsed ? primaryAction.label : undefined} className={cn("flex h-11 items-center rounded-xl text-sm font-semibold text-white shadow-sm transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-offset-2", isCollapsed ? "justify-center px-0" : "justify-center gap-2 px-3", primaryAction.className)}><PrimaryActionIcon className="size-4" />{!isCollapsed && primaryAction.label}</Link>
          ) : (
            <button type="button" onClick={primaryAction.onClick} title={isCollapsed ? primaryAction.label : undefined} className={cn("flex h-11 w-full items-center rounded-xl text-sm font-semibold text-white shadow-sm transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-offset-2", isCollapsed ? "justify-center px-0" : "justify-center gap-2 px-3", primaryAction.className)}><PrimaryActionIcon className="size-4" />{!isCollapsed && primaryAction.label}</button>
          )}
        </div>
      ) : null}

      {/* ── Product content / navigation ───────────────────────────────────── */}
      {content && !isCollapsed ? (
        <div className="flex-1 overflow-y-auto">{content}</div>
      ) : (
      <div className="flex-1 overflow-y-auto py-3">
        <nav className="flex flex-col gap-0.5 px-2" aria-label={navigationLabel}>
          {items.map((item) => {
            /* ── Separator ──────────────────────────────────────────────── */
            if (item.kind === "separator") {
              return (
                <div key={item.key} className={cn("my-1", isCollapsed ? "mx-2" : "mx-1")}>
                  <div className="h-px bg-border" />
                </div>
              );
            }

            const Icon = item.icon;

            /* ── Group item ─────────────────────────────────────────────── */
            if (item.kind === "group") {
              const anyChildActive = item.children.some((c) => isActive(c.key));
              const isOpen = !!groupOpen[item.key] && !isCollapsed;

              return (
                <div
                  key={item.key}
                  className="relative"
                  onMouseEnter={() => {
                    if (!isCollapsed) return;
                    if (hoverTimerRef.current) clearTimeout(hoverTimerRef.current);
                    setHoveredGroup(item.key);
                  }}
                  onMouseLeave={() => {
                    if (!isCollapsed) return;
                    hoverTimerRef.current = setTimeout(() => setHoveredGroup(null), 120);
                  }}
                >
                  <button
                    type="button"
                    onClick={() => toggleGroup(item.key)}
                    className={cn(
                      "flex w-full cursor-pointer select-none items-center gap-2.5 rounded-xl px-3 py-2.5 text-sm transition",
                      isCollapsed && "mx-1 w-auto justify-center px-0 py-3",
                      anyChildActive ? "text-foreground" : "text-muted-foreground",
                      "hover:bg-muted hover:text-foreground",
                    )}
                  >
                    <Icon
                      className={cn(
                        "size-4 shrink-0",
                        anyChildActive ? activeIconClassName : "text-muted-foreground",
                      )}
                    />
                    {!isCollapsed && (
                      <>
                        <span className={cn("flex-1 truncate text-left", anyChildActive ? "font-semibold" : "font-medium")}>
                          {item.label}
                        </span>
                        <ChevronDown
                          className={cn(
                            "size-3.5 shrink-0 text-muted-foreground transition-transform duration-200",
                            isOpen && "rotate-180",
                          )}
                        />
                      </>
                    )}
                  </button>

                  {/* Sub-items */}
                  {isOpen && (
                    <div className="mt-0.5 flex flex-col gap-0.5 pl-3">
                      {item.children.map((child) => {
                        const active = isActive(child.key);
                        const childCls = cn(
                          "flex items-center rounded-xl px-3 py-2 text-[13px] transition",
                          active
                            ? activeItemClassName
                            : "text-muted-foreground hover:bg-muted hover:text-foreground",
                        );
                        if (child.href) {
                          return <Link key={child.key} href={child.href as Route} className={childCls}>{child.label}</Link>;
                        }
                        return (
                          <button key={child.key} type="button" onClick={child.onClick} className={cn(childCls, "w-full text-left")}>
                            {child.label}
                          </button>
                        );
                      })}
                    </div>
                  )}

                  {/* Collapsed flyout */}
                  {isCollapsed && hoveredGroup === item.key && (
                    <GroupFlyout item={item} isActive={isActive} />
                  )}
                </div>
              );
            }

            /* ── Simple item ────────────────────────────────────────────── */
            const active = isActive(item.key);
            const disabled = item.disabled ?? false;
            const simpleCls = cn(
              "group flex w-full items-center gap-2.5 rounded-xl px-3 py-2.5 text-sm transition",
              isCollapsed && "mx-1 w-auto justify-center px-0 py-3",
              disabled
                ? "cursor-default opacity-40"
                : active
                ? activeItemClassName
                : "text-muted-foreground hover:bg-muted hover:text-foreground",
            );
            const iconCls = cn(
              "size-4 shrink-0",
              disabled
                ? "text-muted-foreground"
                : active
                ? activeIconClassName
                : "text-muted-foreground group-hover:text-foreground",
            );

            if (item.href && !disabled) {
              return (
                <Link key={item.key} href={item.href as Route} title={isCollapsed ? item.label : undefined} className={simpleCls}>
                  <Icon className={iconCls} />
                  {!isCollapsed && <span className="truncate">{item.label}</span>}
                </Link>
              );
            }
            return (
              <button
                key={item.key}
                type="button"
                title={isCollapsed ? item.label : undefined}
                onClick={disabled ? undefined : item.onClick}
                disabled={disabled}
                className={simpleCls}
              >
                <Icon className={iconCls} />
                {!isCollapsed && (
                  <>
                    <span className="truncate">{item.label}</span>
                    {disabled && (
                      <span className="ml-auto shrink-0 rounded-full bg-muted px-1.5 py-0.5 text-[9px] font-semibold uppercase tracking-wide text-muted-foreground">
                        Soon
                      </span>
                    )}
                  </>
                )}
              </button>
            );
          })}
        </nav>
      </div>
      )}

      {/* ── User account ────────────────────────────────────────────────────── */}
      <div className="shrink-0 border-t border-border px-2 py-3">
        {!isCollapsed && footerContent ? <div className="mb-2">{footerContent}</div> : null}
        {isCollapsed ? (
          <div className="flex justify-center">
            {onSignOut ? <button onClick={onSignOut} title={`${userLabel} — Sign out`} className="flex size-9 items-center justify-center rounded-xl bg-muted text-muted-foreground transition hover:bg-muted hover:text-foreground">
              <User className="size-4" />
            </button> : <span title={userLabel} className="flex size-9 items-center justify-center rounded-xl bg-muted text-xs font-semibold text-muted-foreground">{userLabel.slice(0, 1).toUpperCase()}</span>}
          </div>
        ) : (
          <div className="group flex items-center gap-2.5 rounded-xl border border-border bg-card px-3 py-2.5 shadow-[0_1px_2px_rgba(16,19,24,0.04)]">
            <Avatar className="size-7 shrink-0">
              {user?.image && (
                <AvatarImage src={user.image} alt={user.name ?? "User"} referrerPolicy="no-referrer" />
              )}
              <AvatarFallback className="bg-foreground text-[11px] font-semibold text-background">
                {userLabel.slice(0, 1).toUpperCase()}
              </AvatarFallback>
            </Avatar>
            <div className="min-w-0 flex-1">
              <div className="truncate text-[11.5px] font-semibold text-foreground" title={userLabel}>
                {userLabel}
              </div>
              {user?.roleLabel && (
                <div className="text-[10px] text-muted-foreground">{user.roleLabel}</div>
              )}
            </div>
            {onSignOut ? <button onClick={onSignOut} title="Sign out" className="shrink-0 rounded-lg p-1 text-muted-foreground transition hover:text-foreground"><LogOut className="size-3.5" /></button> : null}
          </div>
        )}
      </div>
    </aside>
  );
}
