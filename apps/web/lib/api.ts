import { cloudRunAuthorizationHeaders } from "@/lib/cloud-run-auth";

type SessionUser = {
  email?: string | null;
  role?: string | null;
  allowedProjects?: string[] | null;
  allowedRouting?: string | null;
};

function toCamelCase(value: string) {
  // Handle _letter → uppercase letter, and _digit → just remove underscore
  return value.replace(/_([a-z0-9])/g, (_, char: string) =>
    char >= "a" && char <= "z" ? char.toUpperCase() : char
  );
}

function normalizeKeys<T>(value: T): T {
  if (Array.isArray(value)) {
    return value.map((item) => normalizeKeys(item)) as T;
  }

  if (value && typeof value === "object") {
    return Object.fromEntries(
      Object.entries(value as Record<string, unknown>).map(([key, nested]) => [
        toCamelCase(key),
        normalizeKeys(nested)
      ])
    ) as T;
  }

  return value;
}

async function fetchFromApi<T>(
  path: string,
  user?: SessionUser,
  options?: { method?: string; body?: unknown },
): Promise<T> {
  const baseUrl = process.env.API_BASE_URL;
  const internalKey = process.env.INCEPT_INTERNAL_API_KEY;

  if (!baseUrl || !internalKey) {
    throw new Error(`Missing API configuration for ${path}`);
  }

  // Fetch Cloud Run identity token so incept-api can stay private (no allUsers invoker).
  // Falls back to null in local dev — the API allows unauthenticated calls there.
  const authorizationHeaders = await cloudRunAuthorizationHeaders(baseUrl);

  const method = options?.method ?? "GET";
  const response = await fetch(`${baseUrl}${path}`, {
    method,
    cache: "no-store",
    headers: {
      "X-Internal-API-Key": internalKey,
      "X-User-Email": user?.email ?? "",
      "X-User-Role": user?.role ?? "",
      "X-Allowed-Projects": user?.allowedProjects?.join(",") ?? "",
      "X-Allowed-Routing": user?.allowedRouting ?? "",
      ...authorizationHeaders,
      ...(options?.body ? { "Content-Type": "application/json" } : {}),
    },
    ...(options?.body ? { body: JSON.stringify(options.body) } : {}),
  });

  if (!response.ok) {
    throw new Error(`API request failed for ${path}: ${response.status}`);
  }

  return normalizeKeys((await response.json()) as T);
}

// ── Admin: User Management ─────────────────────────────────────────────────────

export type AdminUser = {
  email: string;
  role: string;
  routingBucket?: string | null;
  agencyCompany?: string | null;
};

export type AdminUserListPayload = {
  users: AdminUser[];
  total: number;
};

export function getAdminUsers(user?: SessionUser) {
  return fetchFromApi<AdminUserListPayload>("/api/v1/admin/users", user);
}

export function addAdminUser(
  payload: { email: string; role: string; routingBucket?: string; agencyCompany?: string },
  user?: SessionUser,
) {
  return fetchFromApi<AdminUser>("/api/v1/admin/users", user, {
    method: "POST",
    body: {
      email: payload.email,
      role: payload.role,
      routing_bucket: payload.routingBucket ?? null,
      agency_company: payload.agencyCompany ?? null,
    },
  });
}

export function bulkAddAdminUsers(
  payload: { emails: string[]; role: string; routingBucket?: string; agencyCompany?: string },
  user?: SessionUser,
) {
  return fetchFromApi<{ added: number; emails: string[] }>("/api/v1/admin/users/bulk", user, {
    method: "POST",
    body: {
      emails: payload.emails,
      role: payload.role,
      routing_bucket: payload.routingBucket ?? null,
      agency_company: payload.agencyCompany ?? null,
    },
  });
}

export function updateAdminUser(
  email: string,
  payload: { role: string; routingBucket?: string | null; agencyCompany?: string | null },
  user?: SessionUser,
) {
  return fetchFromApi<AdminUser>(`/api/v1/admin/users/${encodeURIComponent(email)}`, user, {
    method: "PATCH",
    body: {
      role: payload.role,
      routing_bucket: payload.routingBucket ?? null,
      agency_company: payload.agencyCompany ?? null,
    },
  });
}

export function deleteAdminUser(email: string, user?: SessionUser) {
  return fetchFromApi<void>(`/api/v1/admin/users/${encodeURIComponent(email)}`, user, {
    method: "DELETE",
  });
}
