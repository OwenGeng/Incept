import http from "node:http";
import type {
  DetailedAnalysisPayload,
  GenericTopListsPayload,
  LeadCreate,
  LeadListPayload,
  LeadRecord,
  RefreshSnapshotResponse,
  TopListsPayload,
  WeeklyBriefPayload,
  WeeklyBriefSummaryPayload,
} from "@/types/supply";
import type { AiInsightsPayload } from "@/types/ai-insights";

type SessionUser = {
  email?: string | null;
  role?: string | null;
  allowedProjects?: string[] | null;
  allowedRouting?: string | null;
};

export type TopListsQuery = {
  priority?: string;
  routing?: string;
  supplyVisibility?: string;
  search?: string;
  companySortBy?: string;
  companySortDir?: string;
  appSortBy?: string;
  appSortDir?: string;
  companyPage?: string;
  appPage?: string;
};

export type GenericDatasetTopListsQuery = {
  search?: string;
  routing?: string;
  hqCountry?: string;
  monetization?: string;
  companySortBy?: string;
  companySortDir?: string;
  appSortBy?: string;
  appSortDir?: string;
  companyPage?: string;
  appPage?: string;
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

/**
 * Fetch a Cloud Run identity token from the GCP metadata server.
 * Only works when running inside Cloud Run / GCE. Returns null in local dev.
 *
 * The token allows the web service (incept-web) to call incept-api even when
 * the API Cloud Run service is NOT set to allUsers — the IAM layer verifies
 * the identity token before forwarding the request to the application.
 */
/**
 * Fetch a Cloud Run identity token from the GCP metadata server.
 * Only works when running inside Cloud Run / GCE. Returns null in local dev.
 *
 * Uses Node.js native http (not global fetch) to bypass Next.js App Router's
 * fetch wrapper, which intercepts http:// requests and breaks the metadata call.
 */
async function getCloudRunIdentityToken(audience: string): Promise<string | null> {
  // K_SERVICE is only set inside Cloud Run
  if (!process.env.K_SERVICE) return null;
  return new Promise((resolve) => {
    const metaUrl =
      `http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/identity` +
      `?audience=${encodeURIComponent(audience)}`;
    const req = http.get(metaUrl, { headers: { "Metadata-Flavor": "Google" } }, (res) => {
      if (res.statusCode !== 200) { resolve(null); return; }
      let data = "";
      res.on("data", (chunk: unknown) => { data += String(chunk); });
      res.on("end", () => resolve(data.trim() || null));
    });
    req.on("error", () => resolve(null));
    // 2-second timeout — metadata server is local, should respond instantly
    req.setTimeout(2000, () => { req.destroy(); resolve(null); });
  });
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
  const identityToken = await getCloudRunIdentityToken(baseUrl);

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
      ...(identityToken ? { "Authorization": `Bearer ${identityToken}` } : {}),
      ...(options?.body ? { "Content-Type": "application/json" } : {}),
    },
    ...(options?.body ? { body: JSON.stringify(options.body) } : {}),
  });

  if (!response.ok) {
    throw new Error(`API request failed for ${path}: ${response.status}`);
  }

  return normalizeKeys((await response.json()) as T);
}

function buildQueryString(query?: Record<string, string | undefined>) {
  if (!query) return "";
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(query)) {
    if (value) {
      params.set(key, value);
    }
  }
  const serialized = params.toString();
  return serialized ? `?${serialized}` : "";
}

export function getWeeklyBrief(user?: SessionUser) {
  return fetchFromApi<WeeklyBriefPayload>("/api/v1/supply-smb/weekly-brief", user);
}

export function getWeeklyBriefSummary(user?: SessionUser) {
  return fetchFromApi<WeeklyBriefSummaryPayload>("/api/v1/supply-smb/weekly-brief/summary", user);
}

export function getTopLists(user?: SessionUser, query?: TopListsQuery) {
  return fetchFromApi<TopListsPayload>(
    `/api/v1/supply-smb/top-lists${buildQueryString({
      priority: query?.priority,
      routing: query?.routing,
      supply_visibility: query?.supplyVisibility,
      search: query?.search,
      company_sort_by: query?.companySortBy,
      company_sort_dir: query?.companySortDir,
      app_sort_by: query?.appSortBy,
      app_sort_dir: query?.appSortDir,
      company_page: query?.companyPage,
      app_page: query?.appPage
    })}`,
    user
  );
}

export function getDetailedAnalysis(user?: SessionUser) {
  return fetchFromApi<DetailedAnalysisPayload>("/api/v1/supply-smb/detailed-analysis", user);
}

export function getDatasetTopLists(
  datasetKey: string,
  user?: SessionUser,
  query?: GenericDatasetTopListsQuery,
) {
  return fetchFromApi<GenericTopListsPayload>(
    `/api/v1/supply-smb/datasets/${datasetKey}/top-lists${buildQueryString({
      search: query?.search,
      routing: query?.routing,
      hq_country: query?.hqCountry,
      monetization: query?.monetization,
      company_sort_by: query?.companySortBy,
      company_sort_dir: query?.companySortDir,
      app_sort_by: query?.appSortBy,
      app_sort_dir: query?.appSortDir,
      company_page: query?.companyPage,
      app_page: query?.appPage,
    })}`,
    user,
  );
}

export function getDatasetDetailedAnalysis(datasetKey: string, user?: SessionUser) {
  return fetchFromApi<DetailedAnalysisPayload>(`/api/v1/supply-smb/datasets/${datasetKey}/detailed-analysis`, user);
}

export function refreshSnapshot(user?: SessionUser) {
  return fetchFromApi<RefreshSnapshotResponse>("/api/v1/supply-smb/refresh-snapshot", user, { method: "POST" });
}


// ── Lead Tracking ──────────────────────────────────────────────────────────────

export function getLeads(user?: SessionUser, withAttribution = false) {
  const qs = withAttribution ? "?attribution=true" : "";
  return fetchFromApi<LeadListPayload>(`/api/v1/leads${qs}`, user);
}

export function createLead(payload: LeadCreate, user?: SessionUser) {
  // Convert camelCase payload back to snake_case for the API
  const body = {
    company_name: payload.companyName,
    list_source: payload.listSource,
    team_routing: payload.teamRouting,
    sent_to_team: payload.sentToTeam,
    notes: payload.notes ?? "",
    activated_by: payload.activatedBy,
  };
  return fetchFromApi<LeadRecord>("/api/v1/leads", user, { method: "POST", body });
}

export function updateLeadStatus(
  leadId: string,
  status: "sent" | "opened" | "spending",
  notes = "",
  user?: SessionUser,
) {
  return fetchFromApi<Record<string, string>>(`/api/v1/leads/${leadId}`, user, {
    method: "PATCH",
    body: { status, notes },
  });
}

// ── AI Insights ───────────────────────────────────────────────────────────────

export function getAiInsights(user?: SessionUser, scope = "no-sdk-no-ua") {
  return fetchFromApi<AiInsightsPayload>(`/api/v1/ai-insights?scope=${scope}`, user);
}

// ── Cold Prospects ─────────────────────────────────────────────────────────────

export type ColdProspectOverview = {
  totalApps: number;
  totalCompanies: number;
  p1Count: number;
  p2Count: number;
  p3Count: number;
  dataAsOf: string;
  wowNew: number;
  wowDropped: number;
  avgPaidFracP1: number;
  avgPaidFracP2: number;
  topUaNetworks: { network: string; appCount: number }[];
};

export type ColdProspectApp = {
  appMarketBundle: string;
  appName: string;
  companyName: string;
  os: string;
  priority: string;
  paidFrac: number | null;
  stLastMonthDownloads: number | null;
  mauWw: number | null;
  activeUaNetworks: string | null;
  monetizationType: string | null;
  genre: string | null;
  hqCountry: string | null;
};

export type ColdProspectAppsPayload = {
  total: number;
  page: number;
  pageSize: number;
  apps: ColdProspectApp[];
};

export function getColdProspectOverview(user?: SessionUser) {
  return fetchFromApi<ColdProspectOverview>("/api/v1/cold-prospects/overview", user);
}

export function getColdProspectApps(
  user?: SessionUser,
  query?: { priority?: string; os?: string; search?: string; page?: string },
) {
  return fetchFromApi<ColdProspectAppsPayload>(
    `/api/v1/cold-prospects/apps${buildQueryString(query)}`,
    user,
  );
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
