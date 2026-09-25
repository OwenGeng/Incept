/**
 * Authenticated bridge from the AI Video browser client to the unified
 * Linglong Lab API. The browser never receives model credentials.
 */
import http from "node:http";
import { type NextRequest, NextResponse } from "next/server";
import { auth } from "@/auth";
import { isAuthDevSkipped } from "@/lib/auth-mode";

// AI Video is mounted inside Incept API, so it shares the existing service URL
// and internal credential rather than carrying a second backend configuration.
const INCEPT_API_BASE = (
  process.env.INCEPT_API_BASE_URL ??
  process.env.API_BASE_URL ??
  "http://127.0.0.1:8000"
).replace(/\/$/, "");
const INTERNAL_KEY = process.env.INCEPT_INTERNAL_API_KEY ?? "";
const FORWARDED_RESPONSE_HEADERS = ["content-type", "content-disposition", "content-length", "content-range", "cache-control", "accept-ranges"];

type Context = { params: Promise<{ path: string[] }> };

/** Obtains a Cloud Run identity token only when the Next host runs on Cloud Run. */
async function getCloudRunIdentityToken(audience: string): Promise<string | null> {
  if (!process.env.K_SERVICE) return null;
  return new Promise((resolve) => {
    const url = `http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/identity?audience=${encodeURIComponent(audience)}`;
    const request = http.get(url, { headers: { "Metadata-Flavor": "Google" } }, (response) => {
      if (response.statusCode !== 200) return resolve(null);
      let payload = "";
      response.on("data", (chunk: unknown) => { payload += String(chunk); });
      response.on("end", () => resolve(payload.trim() || null));
    });
    request.on("error", () => resolve(null));
    request.setTimeout(2000, () => { request.destroy(); resolve(null); });
  });
}

/** Validates the Linglong session and streams an AI Video request to Incept API. */
async function proxy(request: NextRequest, context: Context): Promise<Response> {
  const { path } = await context.params;
  const joinedPath = path.join("/");
  const isMcpRequest = joinedPath === "api/v1/automation/mcp";
  // AI Video runs inside this Next.js application and uses this same-origin bridge.
  // The mounted API only permits server-to-server CORS. Let the local bridge work
  // without a NextAuth session; deployed environments always require one.
  const isLocalDevelopment = process.env.NODE_ENV === "development";
  const isLocalRequest = request.nextUrl.hostname === "localhost" || request.nextUrl.hostname === "127.0.0.1";
  // MCP is the sole non-cookie entrypoint. It has an independent, scoped,
  // revocable bearer key verified by the API; every other production request
  // still requires the normal Linglong session.
  const skipSessionCheck = isMcpRequest || isAuthDevSkipped() || isLocalDevelopment || isLocalRequest;
  const session = skipSessionCheck ? null : await auth();
  if (!skipSessionCheck && !session?.user) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  const target = `${INCEPT_API_BASE}/ai-video/${joinedPath}${request.nextUrl.search}`;
  const headers: Record<string, string> = {
    "x-internal-api-key": INTERNAL_KEY,
    "x-user-email": session?.user?.email ?? "",
    "x-user-role": session?.user?.role ?? "user",
  };
  const contentType = request.headers.get("content-type");
  const range = request.headers.get("range");
  if (contentType) headers["content-type"] = contentType;
  if (range) headers.range = range;
  if (isMcpRequest) {
    const automationAuthorization = request.headers.get("authorization");
    if (automationAuthorization) {
      // Keep the external automation credential separate from a possible
      // Cloud Run identity token, which also uses Authorization.
      headers["x-incept-mcp-authorization"] = automationAuthorization;
      headers.authorization = automationAuthorization;
    }
    ["mcp-protocol-version", "mcp-method", "mcp-name", "accept"].forEach((name) => {
      const value = request.headers.get(name);
      if (value) headers[name] = value;
    });
  }
  const identityToken = await getCloudRunIdentityToken(INCEPT_API_BASE);
  if (identityToken) headers.authorization = `Bearer ${identityToken}`;

  try {
    const upstream = await fetch(target, {
      method: request.method,
      headers,
      body: request.method === "GET" || request.method === "HEAD" ? null : request.body,
      // @ts-expect-error Node fetch requires duplex when streaming a Request body.
      duplex: "half",
    });
    const responseHeaders = new Headers();
    FORWARDED_RESPONSE_HEADERS.forEach((name) => {
      const value = upstream.headers.get(name);
      if (value) responseHeaders.set(name, value);
    });
    return new Response(upstream.body, { status: upstream.status, headers: responseHeaders });
  } catch (error) {
    console.error("[ai-video proxy] Incept API unreachable", error);
    return NextResponse.json({ error: "Linglong Lab API is unavailable." }, { status: 502 });
  }
}

export const GET = proxy;
export const POST = proxy;
export const PUT = proxy;
export const PATCH = proxy;
export const DELETE = proxy;
export const dynamic = "force-dynamic";
export const runtime = "nodejs";
