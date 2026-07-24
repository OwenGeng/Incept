"use client";

import { useCallback } from "react";
import { usePathname } from "next/navigation";
import { signOut } from "next-auth/react";
import { LayoutPanelTop, Sparkles, MessageSquare } from "lucide-react";
import { AppSidebar, type SidebarNavItem } from "@/components/ui/app-sidebar";
import type { UserRole } from "@/types/next-auth";

// ── Role label map ─────────────────────────────────────────────────────────────

const ROLE_DISPLAY: Record<string, string> = {
  admin:         "Admin",
  moloco_nbs:    "Moloco NBS",
  moloco_ctv:    "Moloco CTV",
  moloco_growth: "Moloco Growth",
  moloco_gtm:    "Moloco GTM",
  moloco_supply: "Moloco Supply",
  agency:        "Agency",
  user:          "Moloco NBS",
};

// ── Nav items (all roles — filtered before passing to sidebar) ─────────────────

const ALL_MOLOCO: UserRole[] = [
  "admin", "moloco_nbs", "moloco_ctv", "moloco_growth",
  "moloco_gtm", "moloco_supply", "user",
];

type RoledNavItem = (SidebarNavItem & { roles: UserRole[] }) | { kind: "separator"; key: string; roles: UserRole[] };

const ALL_NAV_ITEMS: RoledNavItem[] = [
  {
    kind: "group",
    key: "supply-smb",
    label: "Supply SMB",
    icon: LayoutPanelTop,
    roles: [...ALL_MOLOCO, "agency"],
    children: [
      { key: "no-sdk-no-ua", label: "No SDK + No UA", href: "/supply-smb/no-sdk-no-ua/weekly-brief" },
      { key: "sdk-no-ua",    label: "SDK + No UA",    href: "/supply-smb/sdk-no-ua/list-1/top-lists" },
    ],
  },
  {
    kind: "simple",
    key: "ai-insights",
    label: "AI Insights",
    href: "/ai-insights",
    icon: Sparkles,
    roles: ALL_MOLOCO,
  },
  {
    kind: "separator",
    key: "sep-ask-ai",
    roles: ALL_MOLOCO,
  },
  {
    kind: "simple",
    key: "ask-ai",
    label: "Ask AI",
    href: "/ask-ai",
    icon: MessageSquare,
    roles: ALL_MOLOCO,
  },
  // Settings moved to portal page header (admin only)
  // Brand is intentionally excluded from nav — access via /brand directly
];

// ── Active state logic (pathname-based) ────────────────────────────────────────

function useIsActive(pathname: string) {
  return useCallback((key: string) => {
    switch (key) {
      case "no-sdk-no-ua": return pathname.startsWith("/supply-smb/no-sdk-no-ua");
      case "sdk-no-ua":    return pathname.startsWith("/supply-smb/sdk-no-ua");
      case "supply-smb":   return pathname.startsWith("/supply-smb");
      case "ai-insights":  return pathname.startsWith("/ai-insights");
      case "ask-ai":        return pathname.startsWith("/ask-ai");
      default:             return false;
    }
  }, [pathname]);
}

// ── Component ──────────────────────────────────────────────────────────────────

export function Sidebar({
  email,
  name,
  image,
  role,
}: {
  email?: string | null;
  name?:  string | null;
  image?: string | null;
  role?:  UserRole | null;
}) {
  const pathname = usePathname();
  const isActive = useIsActive(pathname);

  const items = ALL_NAV_ITEMS.filter((item) =>
    !role || item.roles.includes(role)
  );

  return (
    <AppSidebar
      productName=""
      brandTitle="Linglong"
      brandSubtitle="Lab"
      logo="/logo.png"
      storageKey="supply"
      items={items}
      isActive={isActive}
      user={{
        email,
        name,
        image,
        roleLabel: role ? (ROLE_DISPLAY[role] ?? role) : null,
      }}
      onSignOut={() => signOut({ callbackUrl: "/sign-in" })}
    />
  );
}
