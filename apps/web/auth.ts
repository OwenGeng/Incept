import NextAuth from "next-auth";
import Google from "next-auth/providers/google";
import { getAccessRecord } from "@/lib/bq-access";
import type { UserRole } from "@/types/next-auth";

/** For agency: pull the first allowed_project as their routing bucket. */
function deriveAllowedRouting(role: UserRole | undefined, allowedProjects: string[] | null | undefined): string | null {
  if (role === "agency" && allowedProjects && allowedProjects.length > 0) {
    return allowedProjects[0];
  }
  return null;
}

export const { handlers, auth, signIn, signOut } = NextAuth({
  trustHost: true,
  pages: {
    signIn: "/sign-in",
  },
  session: {
    strategy: "jwt",
  },
  providers: [
    Google({
      clientId: process.env.GOOGLE_CLIENT_ID,
      clientSecret: process.env.GOOGLE_CLIENT_SECRET,
      checks: ["state"],
    }),
  ],
  callbacks: {
    async signIn({ user }) {
      if (!user.email) return false;

      // Hardcoded admin fallback — works even if the API is down
      if (user.email.toLowerCase() === "owen.geng@moloco.com") {
        user.role = "admin";
        user.allowedProjects = null;
        user.allowedRouting = null;
        return true;
      }

      const record = await getAccessRecord(user.email);
      // record.role is null when email is unknown — deny access
      if (!record || !record.role) return false;

      user.role = record.role as UserRole;
      user.allowedProjects = record.allowed_projects;
      user.allowedRouting = deriveAllowedRouting(user.role, user.allowedProjects);
      return true;
    },

    async jwt({ token, user }) {
      if (user?.email) {
        // Fresh login — copy from user object (already populated in signIn callback)
        token.role = user.role;
        token.allowedProjects = user.allowedProjects;
        token.allowedRouting = user.allowedRouting;
      } else if (token.email && (!token.role || token.allowedProjects === undefined)) {
        // Token refresh — hardcoded admin takes priority, then re-fetch from BQ
        if ((token.email as string).toLowerCase() === "owen.geng@moloco.com") {
          token.role = "admin";
          token.allowedProjects = null;
          token.allowedRouting = null;
        } else {
          const record = await getAccessRecord(token.email as string);
          token.role = record?.role as UserRole | undefined;
          token.allowedProjects = record?.allowed_projects ?? null;
          token.allowedRouting = deriveAllowedRouting(token.role as UserRole | undefined, token.allowedProjects as string[] | null | undefined);
        }
      }
      return token;
    },

    async session({ session, token }) {
      if (session.user) {
        session.user.role = token.role as UserRole | undefined;
        session.user.allowedProjects = (token.allowedProjects as string[] | null | undefined) ?? null;
        session.user.allowedRouting = (token.allowedRouting as string | null | undefined) ?? null;
      }
      return session;
    },
  },
});
