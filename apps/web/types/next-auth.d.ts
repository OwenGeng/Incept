import NextAuth from "next-auth";

// Canonical application role set
// - admin:           full access; default for authenticated @moloco.com users
// - moloco_nbs:      explicitly assigned NBS-scoped role
// - moloco_ctv:      CTV + AI Insights
// - moloco_growth:   Growth-scoped access
// - moloco_gtm:      GTM-scoped access
// - agency:          routing-scoped agency access
// - user:            legacy alias for moloco_nbs (backward-compatible)
export type UserRole =
  | "admin"
  | "moloco_nbs"
  | "moloco_ctv"
  | "moloco_growth"
  | "moloco_gtm"
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
