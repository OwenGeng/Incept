import type { ReactNode } from "react";
import { auth } from "@/auth";
import { Sidebar } from "@/components/layout/sidebar";
import { AuthSessionProvider } from "@/components/incept/AuthSessionProvider";
import type { UserRole } from "@/types/next-auth";

export async function AppShell({ children }: { children: ReactNode }) {
  const session = await auth();
  const email = session?.user?.email ?? null;
  const name  = session?.user?.name  ?? null;
  const image = session?.user?.image ?? null;
  const role  = (session?.user?.role ?? null) as UserRole | null;

  return (
    <AuthSessionProvider>
      <div className="flex min-h-screen bg-background text-foreground">
        <Sidebar email={email} name={name} image={image} role={role} />
        <main className="min-h-screen min-w-0 flex-1 overflow-hidden bg-background px-8 py-7">
          {children}
        </main>
      </div>
    </AuthSessionProvider>
  );
}
