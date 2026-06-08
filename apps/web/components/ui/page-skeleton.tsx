/**
 * Reusable loading skeleton for supply-smb pages.
 * Used by each route's loading.tsx so the user sees instant visual feedback
 * while the server-side render + API fetch completes.
 */
export function PageSkeleton({ variant = "brief" }: { variant?: "brief" | "table" | "analysis" | "leads" }) {
  return (
    <div className="animate-pulse space-y-6">
      {/* ── Topbar skeleton ──────────────────────────────────────── */}
      <div className="mb-8 border-b border-border pb-5">
        <div className="h-8 w-56 rounded-xl bg-muted" />
        <div className="mt-2 h-4 w-80 rounded-lg bg-muted" />
        <div className="mt-5 flex gap-5">
          {[0, 1, 2, 3].map((i) => (
            <div key={i} className="h-5 w-24 rounded-md bg-muted" />
          ))}
        </div>
      </div>

      {variant === "brief" && (
        <>
          {/* Hero card */}
          <div className="h-56 rounded-[28px] bg-muted" />
          {/* 4-col selection steps */}
          <div className="grid grid-cols-4 gap-4">
            {[0, 1, 2, 3].map((i) => (
              <div key={i} className="h-32 rounded-[24px] bg-muted" />
            ))}
          </div>
          {/* Funnel card */}
          <div className="h-72 rounded-[24px] bg-muted" />
          {/* Priority + highlights */}
          <div className="grid grid-cols-4 gap-4">
            {[0, 1, 2, 3].map((i) => (
              <div key={i} className="h-40 rounded-[24px] bg-muted" />
            ))}
          </div>
          <div className="grid grid-cols-3 gap-4">
            {[0, 1, 2].map((i) => (
              <div key={i} className="h-44 rounded-[24px] bg-muted" />
            ))}
          </div>
        </>
      )}

      {variant === "table" && (
        <>
          {/* Filter chips */}
          <div className="flex gap-3">
            {[0, 1, 2, 3].map((i) => (
              <div key={i} className="h-8 w-24 rounded-xl bg-muted" />
            ))}
          </div>
          {/* Table card */}
          <div className="rounded-[24px] bg-muted p-6 space-y-3">
            <div className="h-5 w-40 rounded-lg bg-border" />
            {[0, 1, 2, 3, 4, 5, 6].map((i) => (
              <div key={i} className="h-10 rounded-xl bg-border" style={{ opacity: 1 - i * 0.08 }} />
            ))}
          </div>
        </>
      )}

      {variant === "analysis" && (
        <div className="grid gap-4 xl:grid-cols-2">
          {[0, 1, 2, 3].map((i) => (
            <div key={i} className="h-56 rounded-[24px] bg-muted" />
          ))}
        </div>
      )}

      {variant === "leads" && (
        <>
          <div className="grid grid-cols-4 gap-4">
            {[0, 1, 2, 3].map((i) => (
              <div key={i} className="h-28 rounded-[24px] bg-muted" />
            ))}
          </div>
          <div className="h-16 rounded-[20px] bg-soft-accent" />
          <div className="h-64 rounded-[24px] bg-muted" />
        </>
      )}
    </div>
  );
}
