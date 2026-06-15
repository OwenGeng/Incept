import { type NextRequest, NextResponse } from "next/server";
import { auth } from "@/auth";
import { isAuthDevSkipped } from "@/lib/auth-mode";

const API_BASE = (
  process.env.API_BASE_URL ?? "http://localhost:8000"
).replace(/\/$/, "");

const INTERNAL_KEY = process.env.INCEPT_INTERNAL_API_KEY ?? "";

export async function POST(req: NextRequest): Promise<Response> {
  const session = isAuthDevSkipped() ? null : await auth();
  if (!isAuthDevSkipped() && !session?.user) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  const { content } = await req.json() as { content: string };
  if (!content?.trim()) {
    return NextResponse.json({ error: "content required" }, { status: 400 });
  }

  let upstream: Response;
  try {
    upstream = await fetch(`${API_BASE}/api/v1/feedback`, {
      method: "POST",
      headers: { "content-type": "application/json", "x-internal-api-key": INTERNAL_KEY },
      body: JSON.stringify({ content: content.trim(), user_email: session?.user?.email ?? "" }),
    });
  } catch (err) {
    console.error("[feedback proxy] upstream unreachable:", err);
    return NextResponse.json({ error: "incept-api unreachable" }, { status: 502 });
  }

  const data = await upstream.json() as unknown;
  return NextResponse.json(data, { status: upstream.status });
}

export const dynamic = "force-dynamic";
