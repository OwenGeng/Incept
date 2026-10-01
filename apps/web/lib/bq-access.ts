import type { UserRole } from "@/types/next-auth";
import { cloudRunAuthorizationHeaders } from "@/lib/cloud-run-auth";

type AccessRecord = {
  role: UserRole | null;
  allowed_projects: string[] | null;
};

export async function getAccessRecord(email: string): Promise<AccessRecord | null> {
  if (!email) return null;

  try {
    const baseUrl = process.env.API_BASE_URL;
    const internalKey = process.env.INCEPT_INTERNAL_API_KEY;
    if (!baseUrl || !internalKey) return null;

    const authorizationHeaders = await cloudRunAuthorizationHeaders(baseUrl);
    const res = await fetch(
      `${baseUrl}/api/internal/check-access?email=${encodeURIComponent(email)}`,
      { headers: { "X-Internal-API-Key": internalKey, ...authorizationHeaders }, cache: "no-store" }
    );

    if (!res.ok) return null;
    const data = (await res.json()) as { role?: string | null; allowed_projects?: string[] | null };

    return {
      role: (data.role ?? null) as UserRole | null,
      allowed_projects: data.allowed_projects ?? null,
    };
  } catch {
    return null;
  }
}
