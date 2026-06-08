import path from "path";
import type { NextConfig } from "next";

const extraDevOrigins = (
  process.env.NEXT_ALLOWED_DEV_ORIGINS ??
  "localhost,127.0.0.1,198.18.196.101"
)
  .split(",")
  .map((value) => value.trim())
  .filter(Boolean);

const nextConfig: NextConfig = {
  transpilePackages: ["@incept/shared"],
  // typedRoutes enforces RouteImpl<string> everywhere — incompatible with plain-string
  // helpers like buildUrl(). Disabled to unblock Cloud Run builds; re-enable once all
  // router.push / Link href calls are migrated to typed routes.
  // typedRoutes: true,
  allowedDevOrigins: extraDevOrigins,
  // Standalone output bundles only what's needed — optimal for Docker / Cloud Run
  output: "standalone",
  // CRITICAL for pnpm monorepo: tell Next.js to trace deps from the monorepo root
  // so the .pnpm virtual store is included in the standalone output.
  // Without this, server.js can't resolve modules at runtime in Cloud Run.
  // This also causes the standalone output to use the nested layout:
  //   .next/standalone/apps/web/server.js  (not .next/standalone/server.js)
  // which is why Dockerfile.web uses CMD ["node", "apps/web/server.js"].
  outputFileTracingRoot: path.join(__dirname, "../../"),
  // Skip TS type-checking during `next build` — tsc runs separately in CI.
  // Suppresses build-time errors from next-auth v5 `unknown` token fields
  // and typedRoutes strictness until a full migration is done.
  typescript: {
    ignoreBuildErrors: true,
  },
};

export default nextConfig;
