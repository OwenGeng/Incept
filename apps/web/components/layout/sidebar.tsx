"use client";

import { signOut } from "next-auth/react";
import { AppSidebar } from "@/components/ui/app-sidebar";
import type { UserRole } from "@/types/next-auth";

// ── Role label map ─────────────────────────────────────────────────────────────

const ROLE_DISPLAY: Record<string, string> = {
  admin:         "Admin",
  moloco_nbs:    "Moloco NBS",
  moloco_ctv:    "Moloco CTV",
  moloco_growth: "Moloco Growth",
  moloco_gtm:    "Moloco GTM",
  agency:        "Agency",
  user:          "Moloco NBS",
};

// Nothing currently needs a populated sidebar. The remaining caller is
// app/brand/layout.tsx, which uses AppShell for page chrome, so this component
// renders brand/user info with an empty navigation list.
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
  return (
    <AppSidebar
      productName=""
      brandTitle="Linglong"
      brandSubtitle="Lab"
      logo="/logo.png"
      storageKey="brand"
      items={[]}
      isActive={() => false}
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
