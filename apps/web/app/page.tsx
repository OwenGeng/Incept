import { redirect } from "next/navigation";
import { auth } from "@/auth";
import { isAuthDevSkipped } from "@/lib/auth-mode";
import Link from "next/link";
import { ArrowRight, BarChart3, WandSparkles } from "lucide-react";

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
            <img src="/logo.png" alt="Incept" className="h-7 w-7 rounded-lg object-contain" />
            <span className="text-[15px] font-semibold tracking-tight text-foreground">Incept</span>
          </div>
          <div className="flex items-center gap-3">
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
        <p className="text-[11px] font-semibold uppercase tracking-[0.2em] text-muted-foreground">
          Moloco NBS · AI Operating System
        </p>
        <h1 className="mt-3 text-[32px] font-semibold tracking-tight text-foreground">
          Choose your workspace
        </h1>
      </div>

      {/* Product cards */}
      <div className="mx-auto max-w-4xl px-6 pb-16">
        <div className="grid gap-4 sm:grid-cols-2">

          {/* Scout */}
          <Link
            href="/supply-smb/no-sdk-no-ua/weekly-brief"
            className="group flex flex-col overflow-hidden rounded-2xl border border-border bg-card shadow-sm transition-all hover:-translate-y-0.5 hover:shadow-md"
          >
            <div className="flex h-28 items-center justify-center bg-gradient-to-br from-[#EFF6FF] to-[#E0E9FF]">
              <div className="flex size-14 items-center justify-center rounded-2xl bg-gradient-to-br from-[#3a86ff] to-[#356fec] shadow-lg">
                <BarChart3 className="size-7 text-white" />
              </div>
            </div>
            <div className="flex flex-1 flex-col p-6">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-[10px] font-bold uppercase tracking-[0.18em] text-[#356fec]">Analysis</p>
                  <h2 className="mt-0.5 text-[18px] font-semibold text-foreground">Scout</h2>
                </div>
                <span className="rounded-full bg-[#ECFDF5] px-2.5 py-0.5 text-[11px] font-medium text-[#065f46]">Live</span>
              </div>
              <p className="mt-3 text-sm text-muted-foreground">
                Supply SMB intelligence — prospect ranking, weekly briefs, and AI-powered cross-sell signals.
              </p>
              <div className="mt-5 flex items-center gap-1 text-sm font-medium text-[#356fec]">
                Open <ArrowRight className="size-4 transition-transform group-hover:translate-x-0.5" />
              </div>
            </div>
          </Link>

          {/* Studio — only for Moloco users (agency redirected above) */}
          <Link
            href="/incept"
            className="group flex flex-col overflow-hidden rounded-2xl border border-border bg-card shadow-sm transition-all hover:-translate-y-0.5 hover:shadow-md"
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
                AI creative workspace — generate, edit, and manage ad creatives at scale.
              </p>
              <div className="mt-5 flex items-center gap-1 text-sm font-medium text-[#8338ec]">
                Open <ArrowRight className="size-4 transition-transform group-hover:translate-x-0.5" />
              </div>
            </div>
          </Link>

        </div>
      </div>
    </div>
  );
}
