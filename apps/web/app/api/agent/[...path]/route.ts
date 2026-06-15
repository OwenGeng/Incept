import { type NextRequest, NextResponse } from "next/server";
import { auth } from "@/auth";
import { isAuthDevSkipped } from "@/lib/auth-mode";

const API_BASE = (
  process.env.API_BASE_URL ?? "http://localhost:8000"
).replace(/\/$/, "");

const INTERNAL_KEY = process.env.INCEPT_INTERNAL_API_KEY ?? "";

type Ctx = { params: Promise<{ path: string[] }> };

async function proxy(req: NextRequest, ctx: Ctx): Promise<Response> {
  const session = isAuthDevSkipped() ? null : await auth();
  if (!isAuthDevSkipped() && !session?.user) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  const { path } = await ctx.params;
  const target = `${API_BASE}/api/v1/agent/${path.join("/")}${req.nextUrl.search}`;

  const fwd: Record<string, string> = {
    "x-internal-api-key": INTERNAL_KEY,
    "x-user-email": session?.user?.email ?? "",
    "x-user-role": session?.user?.role ?? "user",
    "content-type": "application/json",
  };

  let upstream: Response;
  try {
    upstream = await fetch(target, {
      method: req.method,
      headers: fwd,
      body: req.method === "GET" || req.method === "HEAD" ? null : req.body,
      // @ts-expect-error duplex not in TS types yet
      duplex: "half",
    });
  } catch (err) {
    console.error("[agent proxy] upstream unreachable:", err);
    return NextResponse.json({ error: "incept-api unreachable" }, { status: 502 });
  }

  const resHeaders = new Headers();
  const ct = upstream.headers.get("content-type");
  if (ct) resHeaders.set("content-type", ct);

  return new Response(upstream.body, { status: upstream.status, headers: resHeaders });
}

export const GET    = proxy;
export const POST   = proxy;
export const dynamic = "force-dynamic";
