"use client";

/**
 * AppSidebar — unified sidebar component for Incept platform products (Scout, Studio).
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
    }
  | {
      kind: "group";
      key: string;
      label: string;
      icon: React.ElementType;
      children: SidebarChildItem[];
    };

export type SidebarUser = {
  email?: string | null;
  name?: string | null;
  image?: string | null;
  /** Optional role label shown beneath email */
  roleLabel?: string | null;
};

export interface AppSidebarProps {
  /** Product name shown in the header — e.g. "Scout", "Studio" */
  productName: string;
  /** Optional logo image path (served from /public). Shown left of product name. */
  logo?: string;
  /** localStorage key prefix to avoid state collision between products */
  storageKey?: string;
  items: SidebarNavItem[];
  /** Return true if the item/child with this key is currently active */
  isActive: (key: string) => boolean;
  user?: SidebarUser;
  onSignOut: () => void;
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
  logo,
  storageKey = "app",
  items,
  isActive,
  user,
  onSignOut,
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

  return (
    <aside
      className={cn(
        "relative z-10 flex h-screen shrink-0 sticky top-0 flex-col bg-secondary border-r border-border transition-[width] duration-200 ease-in-out",
        isCollapsed ? "w-[64px]" : "w-[220px]",
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
          title="Incept"
          className="flex shrink-0 items-center justify-center border-b border-border py-[18px] transition hover:bg-muted"
        >
          {logo ? (
            // eslint-disable-next-line @next/next/no-img-element
            <img src={logo} alt="Incept" className="size-9 shrink-0 rounded-lg object-contain" />
          ) : (
            <div className="flex size-9 shrink-0 select-none items-center justify-center rounded-xl bg-foreground text-[11px] font-bold tracking-tight text-background">
              IN
            </div>
          )}
        </Link>
      ) : (
        /* Expanded: Incept (platform, clickable) + Scout (product sub-label) */
        <div className="shrink-0 border-b border-border px-4 py-3">
          <Link
            href="/"
            className="group -mx-1 flex items-center gap-2 rounded-lg px-1 py-1 transition hover:bg-muted"
          >
            {logo ? (
              // eslint-disable-next-line @next/next/no-img-element
              <img src={logo} alt="Incept" className="size-6 shrink-0 rounded-md object-contain" />
            ) : (
              <div className="flex size-6 shrink-0 select-none items-center justify-center rounded-md bg-foreground text-[9px] font-bold text-background">
                IN
              </div>
            )}
            <span className="text-[13px] font-medium text-muted-foreground transition group-hover:text-foreground">
              Incept
            </span>
          </Link>
          <div className="mt-1.5 px-1">
            <span className="text-[17px] font-semibold tracking-tight text-foreground">
              {productName}
            </span>
          </div>
        </div>
      )}

      {/* ── Navigation ──────────────────────────────────────────────────────── */}
      <div className="flex-1 overflow-y-auto py-3">
        <nav className="flex flex-col gap-0.5 px-2" aria-label="Primary navigation">
          {items.map((item) => {
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
                        anyChildActive ? "text-accent" : "text-muted-foreground",
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
                            ? "bg-soft-accent font-semibold text-foreground"
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
            const simpleCls = cn(
              "group flex w-full items-center gap-2.5 rounded-xl px-3 py-2.5 text-sm transition",
              isCollapsed && "mx-1 w-auto justify-center px-0 py-3",
              active
                ? "bg-soft-accent font-semibold text-foreground"
                : "text-muted-foreground hover:bg-muted hover:text-foreground",
            );
            const iconCls = cn(
              "size-4 shrink-0",
              active ? "text-accent" : "text-muted-foreground group-hover:text-foreground",
            );

            if (item.href) {
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
                onClick={item.onClick}
                className={simpleCls}
              >
                <Icon className={iconCls} />
                {!isCollapsed && <span className="truncate">{item.label}</span>}
              </button>
            );
          })}
        </nav>
      </div>

      {/* ── User account ────────────────────────────────────────────────────── */}
      <div className="shrink-0 border-t border-border px-2 py-3">
        {isCollapsed ? (
          <div className="flex justify-center">
            <button
              onClick={onSignOut}
              title={user?.email ? `${user.email} — Sign out` : "Sign out"}
              className="flex size-9 items-center justify-center rounded-xl bg-muted text-muted-foreground transition hover:bg-muted hover:text-foreground"
            >
              <User className="size-4" />
            </button>
          </div>
        ) : (
          <div className="group flex items-center gap-2.5 rounded-xl border border-border bg-card px-3 py-2.5 shadow-[0_1px_2px_rgba(16,19,24,0.04)]">
            <Avatar className="size-7 shrink-0">
              {user?.image && (
                <AvatarImage src={user.image} alt={user.name ?? "User"} referrerPolicy="no-referrer" />
              )}
              <AvatarFallback className="bg-foreground text-[11px] font-semibold text-background">
                {(user?.email ?? user?.name ?? "U").slice(0, 1).toUpperCase()}
              </AvatarFallback>
            </Avatar>
            <div className="min-w-0 flex-1">
              <div className="truncate text-[11.5px] font-semibold text-foreground" title={user?.email ?? ""}>
                {user?.email ?? "—"}
              </div>
              {user?.roleLabel && (
                <div className="text-[10px] text-muted-foreground">{user.roleLabel}</div>
              )}
            </div>
            <button
              onClick={onSignOut}
              title="Sign out"
              className="shrink-0 rounded-lg p-1 text-muted-foreground transition hover:text-foreground"
            >
              <LogOut className="size-3.5" />
            </button>
          </div>
        )}
      </div>
    </aside>
  );
}
