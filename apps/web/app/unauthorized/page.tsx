import Link from "next/link";
import { ShieldX, Sparkles } from "lucide-react";
import { auth } from "@/auth";
import { signOut } from "@/auth";

export default async function UnauthorizedPage() {
  const session = await auth();

  return (
    <div className="flex min-h-screen items-center justify-center bg-muted p-6">
      <div className="w-full max-w-[440px]">
        <div className="mb-6 flex items-center gap-3">
          <div className="flex size-10 items-center justify-center rounded-2xl bg-soft-accent text-accent">
            <Sparkles className="size-4" />
          </div>
          <span className="text-[15px] font-semibold text-foreground">Linglong</span>
        </div>

        <div className="rounded-[24px] border border-border bg-card p-8 shadow-sm">
          <div className="mb-5 flex size-12 items-center justify-center rounded-2xl bg-danger-soft">
            <ShieldX className="size-5 text-destructive" />
          </div>

          <h1 className="text-[22px] font-semibold text-foreground">Access Restricted</h1>
          <p className="mt-3 text-sm leading-7 text-muted-foreground">
            Your account{session?.user?.email ? ` (${session.user.email})` : ""} does not have
            permission to view this page. Contact your Linglong administrator to request access.
          </p>

          <div className="mt-6 flex flex-col gap-3">
            <Link
              href="/supply-smb/no-sdk-no-ua/weekly-brief"
              className="inline-flex h-10 items-center justify-center rounded-xl bg-accent px-5 text-sm font-semibold text-white transition hover:bg-accent/90"
            >
              Go to Home
            </Link>
            <form
              action={async () => {
                "use server";
                await signOut({ redirectTo: "/sign-in" });
              }}
            >
              <button
                type="submit"
                className="inline-flex h-10 w-full items-center justify-center rounded-xl border border-border bg-muted px-5 text-sm font-semibold text-muted-foreground transition hover:bg-muted"
              >
                Sign out and switch account
              </button>
            </form>
          </div>
        </div>
      </div>
    </div>
  );
}
