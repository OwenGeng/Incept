import { auth } from "@/auth";
import { isDeferredProductSurfaceEnabled } from "@/lib/release-surfaces";
import { NextResponse } from "next/server";
import type { UserRole } from "@/types/next-auth";

// ── Route → allowed roles ──────────────────────────────────────────────────────
// Any role not in the list gets redirected to /unauthorized.
// "user" is the legacy alias for moloco_nbs.

// All internal Moloco roles (every team except agency)
const ALL_MOLOCO: UserRole[] = ["admin", "moloco_nbs", "moloco_ctv", "moloco_growth", "moloco_gtm", "user"];
const ROUTE_ACCESS: Array<{ prefix: string; roles: UserRole[] }> = [
  // CTV is available to internal Moloco roles, but not external agency roles.
  { prefix: "/ctv",         roles: ALL_MOLOCO },
  { prefix: "/ai-insights", roles: ALL_MOLOCO },
  { prefix: "/settings",    roles: ["admin"] },
];

function getAllowedRoles(pathname: string): UserRole[] | null {
  for (const rule of ROUTE_ACCESS) {
    if (pathname.startsWith(rule.prefix)) return rule.roles;
  }
  return null; // no restriction
}

export default auth((req) => {
  const { pathname } = req.nextUrl;

  if (
    !isDeferredProductSurfaceEnabled("gamingPlayable") &&
    (pathname === "/gaming-playable" || pathname.startsWith("/gaming-playable/"))
  ) {
    return new NextResponse(null, { status: 404 });
  }

  // Dev mode: skip all auth checks
  if (process.env.AUTH_DEV_SKIP_SIGN_IN === "true") {
    return NextResponse.next();
  }

  const session = req.auth;

  // Not logged in → sign-in
  if (!session) {
    const signInUrl = new URL("/sign-in", req.url);
    signInUrl.searchParams.set("callbackUrl", pathname);
    return NextResponse.redirect(signInUrl);
  }

  const role = session.user?.role;
  const allowedRoles = getAllowedRoles(pathname);

  if (allowedRoles && role && !allowedRoles.includes(role)) {
    return NextResponse.redirect(new URL("/unauthorized", req.url));
  }

  // Forward role context to API via request headers (picked up by API calls in server components)
  const response = NextResponse.next();
  response.headers.set("x-user-role", role ?? "");
  response.headers.set("x-user-email", session.user?.email ?? "");
  response.headers.set("x-allowed-routing", session.user?.allowedRouting ?? "");
  return response;
});

export const config = {
  matcher: [
    /*
     * Match all routes except:
     *  - /api/* (API routes)
     *  - /_next/* (Next.js internals)
     *  - /sign-in, /unauthorized (public pages)
     *  - Any path with a file extension (.png, .svg, .ico, .css, .js …)
     *    This ensures public-folder static assets are never intercepted by auth,
     *    which was causing /logo.png to redirect to /sign-in when not logged in.
     */
    "/((?!api|_next/static|_next/image|sign-in|unauthorized|.*\\.).*)",
  ],
};
