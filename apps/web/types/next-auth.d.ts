import NextAuth from "next-auth";

// Canonical role set for InterSight
// - admin:           full access to everything (owen.geng@moloco.com, hardcoded)
// - moloco_nbs:      Supply SMB + AI Insights + Leads
// - moloco_ctv:      CTV + AI Insights
// - moloco_growth:   Supply SMB + AI Insights
// - moloco_gtm:      Supply SMB + AI Insights
// - moloco_supply:   Supply SMB + AI Insights
// - agency:          Supply SMB (routing-scoped) + own Leads only
// - user:            legacy alias for moloco_nbs (backward-compatible)
export type UserRole =
  | "admin"
  | "moloco_nbs"
  | "moloco_ctv"
  | "moloco_growth"
  | "moloco_gtm"
  | "moloco_supply"
  | "agency"
  | "user";

declare module "next-auth" {
  interface Session {
    user: {
      name?: string | null;
      email?: string | null;
      image?: string | null;
      role?: UserRole;
      allowedProjects?: string[] | null;
      // For agency users: the single routing bucket they own (e.g. "Qipeng")
      // Derived from allowedProjects[0] at login time.
      allowedRouting?: string | null;
    };
  }

  interface User {
    role?: UserRole;
    allowedProjects?: string[] | null;
    allowedRouting?: string | null;
  }
}

declare module "next-auth/jwt" {
  interface JWT {
    role?: UserRole;
    allowedProjects?: string[] | null;
    allowedRouting?: string | null;
  }
}
