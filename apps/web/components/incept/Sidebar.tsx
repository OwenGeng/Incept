"use client";

import { useCallback } from "react";
import { signOut, useSession } from "next-auth/react";
import { BarChart3, Home, Library, Video, WandSparkles } from "lucide-react";
import { AppSidebar, type SidebarNavItem } from "@/components/ui/app-sidebar";

// ── AppView type (exported so AppShell and other components can use it) ────────

export type AppView = "Home" | "Create" | "Analyze" | "Library" | "Settings" | "Workspace";

// ── Nav item definitions ───────────────────────────────────────────────────────

const BASE_ITEMS: Array<Omit<Extract<SidebarNavItem, { kind: "simple" }>, "onClick">> = [
  { kind: "simple", key: "Home",    label: "Home",    icon: Home },
  { kind: "simple", key: "Create",  label: "Image",   icon: WandSparkles },
  { kind: "simple", key: "Analyze", label: "Analyze", icon: BarChart3 },
  { kind: "simple", key: "Library", label: "Library", icon: Library },
];

const DISABLED_ITEMS: Array<Omit<Extract<SidebarNavItem, { kind: "simple" }>, "onClick"> & { disabled: true }> = [
  { kind: "simple", key: "Video", label: "Video", icon: Video, disabled: true },
];

// ── Component ──────────────────────────────────────────────────────────────────

export interface SidebarProps {
  activeView: AppView;
  onViewChange: (view: AppView) => void;
}

export function Sidebar({ activeView, onViewChange }: SidebarProps) {
  const { data: session } = useSession();
  const user = session?.user;

  const items: SidebarNavItem[] = [
    ...BASE_ITEMS.map((item) => ({
      ...item,
      onClick: () => onViewChange(item.key as AppView),
    })),
    ...DISABLED_ITEMS.map((item) => ({ ...item, onClick: () => {} })),
  ];

  const isActive = useCallback((key: string) => activeView === key, [activeView]);

  return (
    <AppSidebar
      productName="Studio"
      logo="/logo.png"
      storageKey="studio"
      items={items}
      isActive={isActive}
      user={{
        email:  user?.email,
        name:   user?.name,
        image:  user?.image,
      }}
      onSignOut={() => signOut({ callbackUrl: "/sign-in" })}
    />
  );
}
