import { redirect } from "next/navigation";
import { auth } from "@/auth";
import { isAuthDevSkipped } from "@/lib/auth-mode";
import Link from "next/link";
import { ArrowRight, WandSparkles, Settings, BarChart2 } from "lucide-react";

export default async function PortalPage() {
  const session = await auth();

  if (isAuthDevSkipped()) {
    redirect("/supply-smb/no-sdk-no-ua/weekly-brief");
  }

  if (!session) {
    redirect("/sign-in");
  }

  const user  = session.user;
  const role  = user?.role;
  // Agency accounts are Scout-only — redirect them directly
  if (role === "agency") {
    redirect("/supply-smb/no-sdk-no-ua/weekly-brief");
  }

  return (
    <div className="min-h-screen bg-muted">

      {/* Header */}
      <header className="border-b border-border bg-card">
        <div className="mx-auto flex max-w-4xl items-center justify-between px-6 py-4">
          <div className="flex items-center gap-2.5">
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img src="/logo.png" alt="Linglong" className="h-7 w-7 rounded-lg object-contain" />
            <div className="flex flex-col leading-none">
              <span className="text-[15px] font-semibold tracking-tight text-foreground">Linglong</span>
              <span className="mt-1 text-[11px] font-medium tracking-[0.08em] text-muted-foreground">Lab</span>
            </div>
          </div>
          <div className="flex items-center gap-3">
            {role === "admin" && (
              <Link
                href="/settings/users"
                className="flex size-8 items-center justify-center rounded-lg text-muted-foreground transition hover:bg-muted hover:text-foreground"
                title="Settings"
              >
                <Settings className="size-4" />
              </Link>
            )}
            {user?.image && (
              // eslint-disable-next-line @next/next/no-img-element
              <img src={user.image} alt={user.name ?? "User"} referrerPolicy="no-referrer" className="h-8 w-8 rounded-full object-cover" />
            )}
            <span className="text-sm text-muted-foreground">{user?.name ?? user?.email}</span>
          </div>
        </div>
      </header>

      {/* Hero */}
      <div className="mx-auto max-w-4xl px-6 pt-12 pb-8">
        <h1 className="mt-3 text-[32px] font-semibold tracking-tight text-foreground">
          Choose your tool
        </h1>
      </div>

      {/* Product cards */}
      <div className="mx-auto max-w-4xl px-6 pb-16">
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          <Link
            href="/incept"
            className="group flex flex-col overflow-hidden rounded-2xl border border-border bg-card shadow-sm transition-all hover:-translate-y-0.5 hover:shadow-md sm:col-span-2 lg:col-span-1"
          >
            <div className="flex h-28 items-center justify-center bg-gradient-to-br from-[#F3EEFB] to-[#EDE4FF]">
              <div className="flex size-14 items-center justify-center rounded-2xl bg-gradient-to-br from-[#8338ec] to-[#6d28d9] shadow-lg">
                <WandSparkles className="size-7 text-white" />
              </div>
            </div>
            <div className="flex flex-1 flex-col p-6">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-[10px] font-bold uppercase tracking-[0.18em] text-[#8338ec]">Creation</p>
                  <h2 className="mt-0.5 text-[18px] font-semibold text-foreground">Studio</h2>
                </div>
                <span className="rounded-full bg-[#ECFDF5] px-2.5 py-0.5 text-[11px] font-medium text-[#065f46]">Live</span>
              </div>
              <p className="mt-3 text-sm text-muted-foreground">
                AI creative studio — generate, edit, and manage ad creatives at scale.
              </p>
              <div className="mt-5 flex items-center gap-1 text-sm font-medium text-[#8338ec]">
                Open <ArrowRight className="size-4 transition-transform group-hover:translate-x-0.5" />
              </div>
            </div>
          </Link>

          <Link
            href="/supply-smb/no-sdk-no-ua/weekly-brief"
            className="group flex flex-col overflow-hidden rounded-2xl border border-border bg-card shadow-sm transition-all hover:-translate-y-0.5 hover:shadow-md sm:col-span-2 lg:col-span-1"
          >
            <div className="flex h-28 items-center justify-center bg-gradient-to-br from-[#EEF6FB] to-[#E4F0FF]">
              <div className="flex size-14 items-center justify-center rounded-2xl bg-gradient-to-br from-[#0ea5e9] to-[#2563eb] shadow-lg">
                <BarChart2 className="size-7 text-white" />
              </div>
            </div>
            <div className="flex flex-1 flex-col p-6">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-[10px] font-bold uppercase tracking-[0.18em] text-[#0ea5e9]">Analysis</p>
                  <h2 className="mt-0.5 text-[18px] font-semibold text-foreground">Intelligence</h2>
                </div>
                <span className="rounded-full bg-[#ECFDF5] px-2.5 py-0.5 text-[11px] font-medium text-[#065f46]">Live</span>
              </div>
              <p className="mt-3 text-sm text-muted-foreground">
                Market intelligence — prospect discovery, supply signals and insights.
              </p>
              <div className="mt-5 flex items-center gap-1 text-sm font-medium text-[#0ea5e9]">
                Open <ArrowRight className="size-4 transition-transform group-hover:translate-x-0.5" />
              </div>
            </div>
          </Link>
        </div>
      </div>
    </div>
  );
}
