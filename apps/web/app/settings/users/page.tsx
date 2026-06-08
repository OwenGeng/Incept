import { Suspense } from "react";
import { auth } from "@/auth";
import { getAdminUsers } from "@/lib/api";
import { UsersView } from "@/components/settings/users-view";
import { Topbar } from "@/components/layout/topbar";

// ── Data layer (runs inside Suspense) ─────────────────────────────────────────

async function UsersContent() {
  const session = await auth();
  const user = session!.user; // layout already guards admin access
  const data = await getAdminUsers(user);
  return <UsersView initialData={data} currentUserEmail={user.email ?? ""} />;
}

// ── Skeleton ──────────────────────────────────────────────────────────────────

function UsersSkeleton() {
  return (
    <div className="space-y-4">
      {/* Toolbar row */}
      <div className="flex gap-3">
        <div className="h-10 w-64 animate-pulse rounded-xl bg-muted" />
        <div className="ml-auto h-10 w-32 animate-pulse rounded-xl bg-muted" />
        <div className="h-10 w-28 animate-pulse rounded-xl bg-muted" />
      </div>
      {/* Table */}
      <div className="overflow-hidden rounded-2xl border border-border">
        {/* Header */}
        <div className="flex gap-8 border-b border-border bg-muted px-6 py-4">
          {[120, 200, 100, 80, 60].map((w, i) => (
            <div key={i} className="h-3 animate-pulse rounded bg-muted-foreground/20" style={{ width: w }} />
          ))}
        </div>
        {/* Rows */}
        {Array.from({ length: 8 }).map((_, r) => (
          <div key={r} className="flex gap-8 border-b border-border px-6 py-5">
            {[120, 200, 100, 80, 60].map((w, c) => (
              <div
                key={c}
                className="h-4 animate-pulse rounded bg-muted"
                style={{ width: w + (r + c) * 6 }}
              />
            ))}
          </div>
        ))}
      </div>
    </div>
  );
}

// ── Page ──────────────────────────────────────────────────────────────────────

export default function SettingsUsersPage() {
  return (
    <div className="min-w-0">
      {/* Topbar renders immediately */}
      <Topbar
        title="User Management"
        subtitle="Manage access for Moloco team members and external agencies. Users not in this list cannot sign in."
      />
      <Suspense fallback={<UsersSkeleton />}>
        <UsersContent />
      </Suspense>
    </div>
  );
}
