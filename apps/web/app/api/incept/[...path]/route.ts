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

import { type NextRequest, NextResponse } from "next/server";
import { auth } from "@/auth";
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
  "cache-control",
  "accept-ranges",
];

type Ctx = { params: Promise<{ path: string[] }> };

async function proxy(req: NextRequest, ctx: Ctx): Promise<Response> {
  // ── 1. Auth ──────────────────────────────────────────────────────────────
  const session = isAuthDevSkipped() ? null : await auth();
  if (!isAuthDevSkipped() && !session?.user) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  // ── 2. Target URL ─────────────────────────────────────────────────────────
  const { path } = await ctx.params;
  const target = `${INCEPT_BASE}/${path.join("/")}${req.nextUrl.search}`;

  // ── 3. Request headers ────────────────────────────────────────────────────
  const fwd: Record<string, string> = {
    "x-internal-api-key": INTERNAL_KEY,
    "x-user-email":       session?.user?.email ?? "",
    "x-user-role":        session?.user?.role  ?? "user",
  };
  // Preserve Content-Type so multipart uploads and JSON reach the backend intact
  const ct = req.headers.get("content-type");
  if (ct) fwd["content-type"] = ct;

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
    console.error("[incept proxy] upstream unreachable:", err);
    return NextResponse.json(
      { error: "nbs-api unreachable" },
      { status: 502 },
    );
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
