"use client";

import { useCallback } from "react";
import { signOut, useSession } from "next-auth/react";
import { Activity, Home, ImageIcon, Library } from "lucide-react";
import type { LinglongLabUser } from "@linglonglab/shared";
import { AppSidebar, type SidebarNavItem } from "@/components/ui/app-sidebar";
import type { ContentScope } from "@/lib/incept-api";

// ── AppView type (exported so AppShell and other components can use it) ────────

export type AppView = "Home" | "Image" | "Analyze" | "Library" | "Settings" | "Workspace" | "Usage";

// ── Nav item definitions ───────────────────────────────────────────────────────

const BASE_ITEMS: Array<Omit<Extract<SidebarNavItem, { kind: "simple" }>, "onClick">> = [
  { kind: "simple", key: "Home",    label: "Home",    icon: Home },
  { kind: "simple", key: "Image",   label: "Image",   icon: ImageIcon },
  { kind: "simple", key: "Library", label: "Library", icon: Library },
  { kind: "simple", key: "Usage",   label: "Usage",   icon: Activity },
];

// ── Component ──────────────────────────────────────────────────────────────────

export interface SidebarProps {
  activeView: AppView;
  onViewChange: (view: AppView) => void;
  currentUser: LinglongLabUser;
  contentScope: ContentScope;
  onContentScopeChange: (scope: ContentScope) => void;
}

export function Sidebar({
  activeView,
  onViewChange,
  currentUser,
  contentScope,
  onContentScopeChange,
}: SidebarProps) {
  const { data: session } = useSession();
  const user = session?.user;
  // Workspace content is shared by signed-in members. The scope control only
  // changes what is displayed; it does not grant edit or delete permission.
  const canViewAllContent = Boolean(currentUser.id && currentUser.id !== "anon");

  const items: SidebarNavItem[] = [
    ...BASE_ITEMS.map((item) => ({
      ...item,
      onClick: () => onViewChange(item.key as AppView),
    })),
  ];

  const isActive = useCallback((key: string) => activeView === key, [activeView]);

  return (
    <AppSidebar
      productName=""
      brandTitle="Linglong"
      brandSubtitle="Lab"
      logo="/logo.png"
      storageKey="studio"
      expandedWidthClassName="w-60"
      items={items}
      isActive={isActive}
      user={{
        email:  user?.email,
        name:   user?.name,
        image:  user?.image,
      }}
      onSignOut={() => signOut({ callbackUrl: "/sign-in" })}
      topContent={
        canViewAllContent ? (
          <div className="flex items-center justify-between gap-3">
            <div className="min-w-0">
              <p className="text-[10px] font-semibold uppercase tracking-[0.14em] text-muted-foreground">
                Content Scope
              </p>
              <p className="mt-1 text-[11px] font-medium text-foreground/80">
                {contentScope === "all" ? "All users" : "Mine only"}
              </p>
            </div>
            <button
              type="button"
              aria-pressed={contentScope === "all"}
              onClick={() => onContentScopeChange(contentScope === "all" ? "mine" : "all")}
              className={
                contentScope === "all"
                  ? "relative inline-flex h-6 w-11 shrink-0 items-center rounded-full bg-black ring-1 ring-black/20 transition-colors"
                  : "relative inline-flex h-6 w-11 shrink-0 items-center rounded-full bg-black/35 ring-1 ring-black/15 transition-colors"
              }
              title={contentScope === "all" ? "Showing all users" : "Showing only my content"}
            >
              <span
                className={
                  contentScope === "all"
                    ? "inline-block size-5 translate-x-5 rounded-full bg-background shadow-md ring-1 ring-black/5 transition-transform"
                    : "inline-block size-5 translate-x-0.5 rounded-full bg-background shadow-md ring-1 ring-black/5 transition-transform"
                }
              />
            </button>
          </div>
        ) : null
      }
    />
  );
}
