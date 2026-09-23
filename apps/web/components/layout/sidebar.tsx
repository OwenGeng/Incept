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
  moloco_supply: "Moloco Supply",
  agency:        "Agency",
  user:          "Moloco NBS",
};

// Supply's nav items (Supply SMB / AI Insights / Ask AI) were removed with the
// rest of Supply. Nothing currently needs a populated sidebar — this component's
// only remaining caller is app/brand/layout.tsx, which uses AppShell purely for
// page chrome — so it renders brand/user info with an empty nav rather than
// being deleted outright.
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
      storageKey="supply"
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
