import { redirect } from "next/navigation";
import { signIn } from "@/auth";
import { auth } from "@/auth";
import { isAuthDevSkipped } from "@/lib/auth-mode";

export default async function SignInPage() {
  const session = await auth();

  if (session || isAuthDevSkipped()) {
    redirect("/");
  }

  return (
    <div className="flex min-h-screen flex-col items-center justify-center bg-background px-4">

      {/* Brand */}
      <div className="mb-8 flex flex-col items-center gap-3">
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img
          src="/logo.png"
          alt=""
          width={52}
          height={52}
          style={{ width: 52, height: 52, borderRadius: 12, objectFit: "contain" }}
        />
        <div className="text-center">
          <div className="text-[26px] font-semibold tracking-tight text-foreground">Incept</div>
          <div className="mt-0.5 text-sm text-muted-foreground">AI Operating System</div>
        </div>
      </div>

      {/* Sign-in card */}
      <div className="w-full max-w-[420px] overflow-hidden rounded-[20px] border border-border bg-card shadow-sm">

        <div className="px-8 pt-8 pb-6 text-center">
          <h1 className="text-[18px] font-semibold text-foreground">Sign in to Incept</h1>
          <p className="mt-1.5 text-sm text-muted-foreground">
            Use your Moloco Google account to continue
          </p>
        </div>

        <div className="border-t border-border px-8 py-6">
          <form
            action={async () => {
              "use server";
              await signIn("google", { redirectTo: "/" });
            }}
          >
            <button
              type="submit"
              className="inline-flex h-11 w-full items-center justify-center gap-3 rounded-xl border border-border bg-card text-sm font-medium text-foreground shadow-sm transition hover:bg-muted"
            >
              {/* Google "G" icon */}
              <svg width="18" height="18" viewBox="0 0 18 18" aria-hidden="true">
                <path d="M17.64 9.205c0-.638-.057-1.252-.164-1.841H9v3.481h4.844a4.14 4.14 0 0 1-1.796 2.716v2.259h2.908c1.702-1.567 2.684-3.875 2.684-6.615Z" fill="#4285F4"/>
                <path d="M9 18c2.43 0 4.467-.806 5.956-2.18l-2.908-2.259c-.806.54-1.837.86-3.048.86-2.344 0-4.328-1.584-5.036-3.711H.957v2.332A8.997 8.997 0 0 0 9 18Z" fill="#34A853"/>
                <path d="M3.964 10.71A5.41 5.41 0 0 1 3.682 9c0-.593.102-1.17.282-1.71V4.958H.957A8.996 8.996 0 0 0 0 9c0 1.452.348 2.827.957 4.042l3.007-2.332Z" fill="#FBBC05"/>
                <path d="M9 3.58c1.321 0 2.508.454 3.44 1.345l2.582-2.58C13.463.891 11.426 0 9 0A8.997 8.997 0 0 0 .957 4.958L3.964 7.29C4.672 5.163 6.656 3.58 9 3.58Z" fill="#EA4335"/>
              </svg>
              Continue with Google
            </button>
          </form>
        </div>
      </div>

      {/* Footer note */}
      <p className="mt-6 text-center text-[12.5px] text-muted-foreground">
        Access is restricted to @moloco.com accounts
      </p>
    </div>
  );
}
