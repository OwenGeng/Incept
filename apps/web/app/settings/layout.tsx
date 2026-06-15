import { redirect } from "next/navigation";
import { auth } from "@/auth";
import { isAuthDevSkipped } from "@/lib/auth-mode";
import Link from "next/link";
import { ArrowLeft } from "lucide-react";

export default async function SettingsLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const session = await auth();

  if (!session && !isAuthDevSkipped()) {
    redirect("/sign-in");
  }

  if (!isAuthDevSkipped() && session?.user?.role !== "admin") {
    redirect("/unauthorized");
  }

  const user = session?.user;

  return (
    <div className="min-h-screen bg-muted">
      {/* Header */}
      <header className="border-b border-border bg-card">
        <div className="mx-auto flex max-w-5xl items-center justify-between px-6 py-4">
          <div className="flex items-center gap-4">
            <Link
              href="/"
              className="flex items-center gap-1.5 text-sm text-muted-foreground transition-colors hover:text-foreground"
            >
              <ArrowLeft className="size-4" />
              Back
            </Link>
            <div className="h-4 w-px bg-border" />
            <div className="flex items-center gap-2.5">
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img src="/logo.png" alt="Linglong" className="h-7 w-7 rounded-lg object-contain" />
              <span className="text-[15px] font-semibold tracking-tight text-foreground">Settings</span>
            </div>
          </div>
          <div className="flex items-center gap-3">
            {user?.image && (
              // eslint-disable-next-line @next/next/no-img-element
              <img
                src={user.image}
                alt={user.name ?? "User"}
                referrerPolicy="no-referrer"
                className="h-8 w-8 rounded-full object-cover"
              />
            )}
            <span className="text-sm text-muted-foreground">{user?.name ?? user?.email}</span>
          </div>
        </div>
      </header>

      {/* Content */}
      <div className="mx-auto max-w-5xl px-6 py-8">
        {children}
      </div>
    </div>
  );
}
