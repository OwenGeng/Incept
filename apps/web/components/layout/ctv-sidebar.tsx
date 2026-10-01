"use client";

import { useCallback } from "react";
import { usePathname } from "next/navigation";
import { signOut } from "next-auth/react";
import { Globe, Smartphone, Sparkles, MessageSquare } from "lucide-react";
import { AppSidebar, type SidebarNavItem } from "@/components/ui/app-sidebar";
import type { UserRole } from "@/types/next-auth";

const ALL_MOLOCO: UserRole[] = [
  "admin", "moloco_nbs", "moloco_ctv", "moloco_growth",
  "moloco_gtm", "user",
];

const ROLE_DISPLAY: Record<string, string> = {
  admin:         "Admin",
  moloco_nbs:    "Moloco NBS",
  moloco_ctv:    "Moloco CTV",
  moloco_growth: "Moloco Growth",
  moloco_gtm:    "Moloco GTM",
  user:          "Moloco NBS",
};

const NAV_ITEMS: SidebarNavItem[] = [
  {
    kind: "simple",
    key: "ctv-to-web",
    label: "CTV to Web",
    href: "/ctv/ctv-to-web",
    icon: Globe,
    disabled: true,
  },
  {
    kind: "simple",
    key: "ctv-to-app",
    label: "CTV to App",
    href: "/ctv/ctv-to-app",
    icon: Smartphone,
    disabled: true,
  },
  {
    kind: "simple",
    key: "ctv-ai-insights",
    label: "AI Insights",
    href: "/ctv/ai-insights",
    icon: Sparkles,
    disabled: true,
  },
  {
    kind: "separator",
    key: "sep-ask-ai",
  },
  {
    kind: "simple",
    key: "ctv-ask-ai",
    label: "Ask AI",
    href: "/ctv/ask-ai",
    icon: MessageSquare,
    disabled: true,
  },
];

function useIsActive(pathname: string) {
  return useCallback((key: string) => {
    switch (key) {
      case "ctv-to-web":     return pathname.startsWith("/ctv/ctv-to-web");
      case "ctv-to-app":     return pathname.startsWith("/ctv/ctv-to-app");
      case "ctv-ai-insights": return pathname.startsWith("/ctv/ai-insights");
      case "ctv-ask-ai":     return pathname.startsWith("/ctv/ask-ai");
      default:               return false;
    }
  }, [pathname]);
}

export function CtvSidebar({
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

  return (
    <AppSidebar
      productName=""
      logo="/logo.png"
      storageKey="ctv"
      items={NAV_ITEMS}
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
