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
  poweredByHeader: false,
  transpilePackages: ["@linglonglab/shared"],
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
  async headers() {
    return [
      {
        source: "/:path*",
        headers: [
          { key: "Strict-Transport-Security", value: "max-age=31536000; includeSubDomains" },
          { key: "X-Content-Type-Options", value: "nosniff" },
          { key: "X-Frame-Options", value: "SAMEORIGIN" },
          { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
          { key: "Permissions-Policy", value: "camera=(), microphone=(), geolocation=()" },
        ],
      },
    ];
  },
};

export default nextConfig;
