import { type NextRequest, NextResponse } from "next/server";
import { isAuthDevSkipped } from "@/lib/auth-mode";
import { getCloudRunIdentityToken } from "@/lib/cloud-run-auth";

const API_BASE = (
  process.env.INCEPT_API_BASE_URL ??
  process.env.API_BASE_URL ??
  "http://localhost:8000"
).replace(/\/$/, "");

const INTERNAL_KEY = process.env.INCEPT_INTERNAL_API_KEY ?? "";
const ALLOWED_ROOTS = new Set([
  "agent",
  "ai",
  "assets",
  "nodes",
  "settings",
  "tools",
  "workspaces",
]);

type Context = { params: Promise<{ path: string[] }> };

async function proxy(request: NextRequest, context: Context): Promise<Response> {
  const { path } = await context.params;
  if (!path.length || !ALLOWED_ROOTS.has(path[0]!)) {
    return NextResponse.json({ code: 404, message: "Video API route not found" }, { status: 404 });
  }

  const devAuthSkipped = isAuthDevSkipped();
  const session = devAuthSkipped
    ? null
    : await import("@/auth").then((module) => module.auth());
  if (!devAuthSkipped && !session?.user?.email) {
    return NextResponse.json({ code: 401, message: "Unauthorized" }, { status: 401 });
  }

  const target = `${API_BASE}/video-legacy/api/${path.map(encodeURIComponent).join("/")}${request.nextUrl.search}`;
  const identityToken = await getCloudRunIdentityToken(API_BASE);
  const headers = new Headers({
    "x-internal-api-key": INTERNAL_KEY,
    "x-user-email": session?.user?.email ?? "local@linglonglab.internal",
    "x-user-role": session?.user?.role ?? "user",
  });
  const contentType = request.headers.get("content-type");
  const range = request.headers.get("range");
  if (contentType) headers.set("content-type", contentType);
  if (range) headers.set("range", range);
  if (identityToken) headers.set("authorization", `Bearer ${identityToken}`);

  try {
    const upstream = await fetch(target, {
      method: request.method,
      headers,
      body: request.method === "GET" || request.method === "HEAD" ? null : request.body,
      // @ts-expect-error Node fetch requires duplex when forwarding a stream.
      duplex: "half",
      cache: "no-store",
    });
    const responseHeaders = new Headers();
    for (const name of ["content-type", "content-disposition", "content-length", "content-range", "accept-ranges", "cache-control"]) {
      const value = upstream.headers.get(name);
      if (value) responseHeaders.set(name, value);
    }
    return new Response(upstream.body, { status: upstream.status, headers: responseHeaders });
  } catch (error) {
    console.error("[video proxy] upstream unavailable", error);
    return NextResponse.json({ code: 502, message: "Video API unavailable" }, { status: 502 });
  }
}

export const GET = proxy;
export const POST = proxy;
export const PUT = proxy;
export const PATCH = proxy;
export const DELETE = proxy;
export const dynamic = "force-dynamic";
export const runtime = "nodejs";
