import { Suspense } from "react";
import { auth } from "@/auth";
import { Topbar } from "@/components/layout/topbar";
import type { TopListsQuery } from "@/components/supply-smb/prospect-filter-bar";
import { TableToolbar } from "@/components/supply-smb/table-toolbar";
import { TopListsTablesContent } from "@/components/supply-smb/top-lists-view";
import { getTopLists } from "@/lib/api";
import { defaultPageTabs } from "@/lib/supply-navigation";
import type { Session } from "next-auth";

// ── Filter field config ────────────────────────────────────────────────────────

const FILTER_FIELDS = [
  {
    type: "search" as const,
    key:  "search",
    label: "Search",
    placeholder: "company, app, genre…",
  },
  {
    type: "select" as const,
    key:  "priority",
    label: "Priority",
    options: [
      { label: "All",        value: "all" },
      { label: "P1",         value: "P1" },
      { label: "P2",         value: "P2" },
      { label: "P3",         value: "P3" },
      { label: "P4",         value: "P4" },
    ],
  },
  {
    type: "select" as const,
    key:  "routing",
    label: "Team Routing",
    options: [
      { label: "All",         value: "all" },
      { label: "Non-Gaming",  value: "Non-Gaming" },
      { label: "Gaming",      value: "Gaming" },
    ],
  },
  {
    type: "select" as const,
    key:  "supplyVisibility",
    label: "Supply Visible",
    options: [
      { label: "All",     value: "all" },
      { label: "Visible", value: "visible" },
      { label: "Hidden",  value: "hidden" },
    ],
  },
];

const PRESERVE_KEYS = ["companySortBy", "companySortDir", "appSortBy", "appSortDir"];
const RESET_HREF    = "/supply-smb/no-sdk-no-ua/top-lists";

// ── Async table content — inside Suspense ──────────────────────────────────────

async function TopListsTablesAsync({
  user,
  query,
}: {
  user: Session["user"] | undefined;
  query: TopListsQuery;
}) {
  const data = await getTopLists(user, query);
  return <TopListsTablesContent data={data} query={query} />;
}

// ── Skeleton ───────────────────────────────────────────────────────────────────

function TopListsTablesSkeleton() {
  const colWidths = [72, 160, 64, 88, 110, 60, 72, 88];
  return (
    <div className="space-y-5">
      {[colWidths, [72, 160, 140, 64, 88, 100, 72, 88, 96, 80]].map((cols, ti) => (
        <div key={ti} className="overflow-hidden rounded-2xl border border-border bg-card">
          <div className="flex items-start justify-between px-6 pt-5 pb-4">
            <div>
              <div className="h-5 w-36 animate-pulse rounded-lg bg-muted" />
              <div className="mt-1.5 h-3.5 w-52 animate-pulse rounded bg-muted" />
            </div>
            <div className="h-8 w-8 animate-pulse rounded-lg bg-muted" />
          </div>
          <div className="overflow-x-auto">
            <div className="flex gap-6 border-b border-border px-6 py-4">
              {cols.map((w, i) => (
                <div key={i} className="h-3 animate-pulse rounded bg-muted" style={{ width: w }} />
              ))}
            </div>
            {Array.from({ length: 8 }).map((_, r) => (
              <div key={r} className="flex gap-6 border-b border-border px-6 py-[18px]">
                {cols.map((w, c) => (
                  <div
                    key={c}
                    className="h-4 animate-pulse rounded bg-muted"
                    style={{ width: w + ((r + c) % 3) * 12 }}
                  />
                ))}
              </div>
            ))}
          </div>
          <div className="flex items-center justify-between border-t border-border px-6 py-4">
            <div className="h-4 w-40 animate-pulse rounded bg-muted" />
            <div className="flex gap-2">
              <div className="h-9 w-16 animate-pulse rounded-xl bg-muted" />
              <div className="h-9 w-16 animate-pulse rounded-xl bg-muted" />
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}

// ── Page ──────────────────────────────────────────────────────────────────────

type SearchParams = Promise<{
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
}>;

export default async function NoSdkNoUaTopListsPage({
  searchParams,
}: {
  searchParams?: SearchParams;
}) {
  const session = await auth();
  const query: TopListsQuery = (await searchParams) ?? {};

  return (
    <div className="min-w-0">
      <Topbar
        activeHref="/supply-smb/no-sdk-no-ua/top-lists"
        title="Supply SMB — No SDK + No UA"
        subtitle="Priority-ranked companies and apps for cold SDK outreach."
        pageTabs={defaultPageTabs}
      />

      <div className="space-y-5">
        {/*
          TableToolbar renders immediately — client component, no data dependency.
          No export buttons here (table data not yet available outside Suspense).
          Per-table CSV download buttons are inside TopListsTablesContent.
        */}
        <TableToolbar
          fields={FILTER_FIELDS}
          query={query as Record<string, string | undefined>}
          resetHref={RESET_HREF}
          preserveKeys={PRESERVE_KEYS}
        />

        {/* Tables stream in behind Suspense */}
        <Suspense fallback={<TopListsTablesSkeleton />}>
          <TopListsTablesAsync user={session?.user} query={query} />
        </Suspense>
      </div>
    </div>
  );
}
