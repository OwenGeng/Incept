/**
 * Catch-all proxy: /api/incept/[...path] → nbs-api (unified backend)
 *
 * All Incept API calls from the browser go through here instead of hitting
 * the backend directly. This lets us:
 *   - enforce auth with the existing NextAuth session
 *   - keep nbs-api behind --no-allow-unauthenticated on Cloud Run
 *   - pass user identity (email / role) to the backend via trusted headers
 *
 * Static asset paths (/static/generated/...) are also proxied, so
 * resolveAssetUrl() in lib/incept-api.ts works without any special handling.
 *
 * Backend resolution order:
 *   INCEPT_API_BASE_URL (explicit override) → API_BASE_URL → localhost:8000
 */

import http from "node:http";
import { type NextRequest, NextResponse } from "next/server";
import { isAuthDevSkipped } from "@/lib/auth-mode";

const INCEPT_BASE = (
  process.env.INCEPT_API_BASE_URL ??
  process.env.API_BASE_URL ??
  "http://localhost:8000"
).replace(/\/$/, "");

const INTERNAL_KEY = process.env.INCEPT_INTERNAL_API_KEY ?? "";

// Headers we copy from the upstream response to the browser
const FORWARDED_RES_HEADERS = [
  "content-type",
  "content-disposition",
  "content-length",
  "content-range",
  "cache-control",
  "accept-ranges",
];

type Ctx = { params: Promise<{ path: string[] }> };

const delay = (milliseconds: number) => new Promise<void>((resolve) => {
  setTimeout(resolve, milliseconds);
});

async function getCloudRunIdentityToken(audience: string): Promise<string | null> {
  if (!process.env.K_SERVICE) return null;
  return new Promise((resolve) => {
    const metaUrl =
      `http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/identity` +
      `?audience=${encodeURIComponent(audience)}`;
    const request = http.get(metaUrl, { headers: { "Metadata-Flavor": "Google" } }, (response) => {
      if (response.statusCode !== 200) {
        resolve(null);
        return;
      }
      let data = "";
      response.on("data", (chunk: unknown) => {
        data += String(chunk);
      });
      response.on("end", () => resolve(data.trim() || null));
    });
    request.on("error", () => resolve(null));
    request.setTimeout(2000, () => {
      request.destroy();
      resolve(null);
    });
  });
}

async function proxy(req: NextRequest, ctx: Ctx): Promise<Response> {
  const { path } = await ctx.params;
  // ── 1. Auth ──────────────────────────────────────────────────────────────
  const isPublicVideoStudio = path[0] === "video-studio";
  const session = isAuthDevSkipped()
    ? null
    : await import("@/auth").then((mod) => mod.auth());
  if (!isAuthDevSkipped() && !isPublicVideoStudio && !session?.user) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  // ── 2. Target URL ─────────────────────────────────────────────────────────
  const target = `${INCEPT_BASE}/${path.join("/")}${req.nextUrl.search}`;
  const identityToken = await getCloudRunIdentityToken(INCEPT_BASE);

  // ── 3. Request headers ────────────────────────────────────────────────────
  const fwd: Record<string, string> = {
    "x-internal-api-key": INTERNAL_KEY,
    "x-user-email":       session?.user?.email ?? (isPublicVideoStudio ? "local@linglonglab.internal" : ""),
    "x-user-role":        session?.user?.role  ?? "user",
  };
  if (identityToken) {
    fwd.authorization = `Bearer ${identityToken}`;
  }
  // Preserve Content-Type so multipart uploads and JSON reach the backend intact
  const ct = req.headers.get("content-type");
  if (ct) fwd["content-type"] = ct;
  // Video elements use Range requests to load MP4 metadata and seek. Preserve
  // this hop-by-hop request header so the backend can return 206 responses.
  const range = req.headers.get("range");
  if (range) fwd.range = range;

  // ── 4. Forward to incept-api ──────────────────────────────────────────────
  let upstream: Response;
  try {
    upstream = await fetch(target, {
      method: req.method,
      headers: fwd,
      // stream the body through without buffering (needed for file uploads)
      body: req.method === "GET" || req.method === "HEAD" ? null : req.body,
      // @ts-expect-error duplex not in TS types yet, required for streaming bodies in Node 18+
      duplex: "half",
    });
  } catch (err) {
    // `uvicorn --reload` briefly drops existing sockets while replacing the
    // worker. A read request is safe to retry and should not surface a random
    // 502 in the UI. Never retry mutations here: a POST can create a second
    // generation job and must remain explicitly user-driven.
    if (req.method === "GET" || req.method === "HEAD") {
      try {
        await delay(250);
        upstream = await fetch(target, {
          method: req.method,
          headers: fwd,
        });
      } catch (retryErr) {
        console.error("[incept proxy] upstream unreachable after retry:", retryErr);
        return NextResponse.json(
          { error: "nbs-api unreachable" },
          { status: 502 },
        );
      }
    } else {
    console.error("[incept proxy] upstream unreachable:", err);
    return NextResponse.json(
      { error: "nbs-api unreachable" },
      { status: 502 },
    );
    }
  }

  // ── 5. Stream response back ───────────────────────────────────────────────
  const resHeaders = new Headers();
  for (const h of FORWARDED_RES_HEADERS) {
    const v = upstream.headers.get(h);
    if (v) resHeaders.set(h, v);
  }

  return new Response(upstream.body, {
    status: upstream.status,
    headers: resHeaders,
  });
}

export const GET    = proxy;
export const POST   = proxy;
export const PUT    = proxy;
export const PATCH  = proxy;
export const DELETE = proxy;

// Never cache — every request carries live session data
export const dynamic = "force-dynamic";
export const runtime = "nodejs";
