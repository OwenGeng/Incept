import { redirect } from "next/navigation";
import { auth } from "@/auth";
import { AppShell } from "@/components/layout/app-shell";
import { isAuthDevSkipped } from "@/lib/auth-mode";

export default async function SupplyLayout({
  children
}: {
  children: React.ReactNode;
}) {
  const session = await auth();

  if (!session && !isAuthDevSkipped()) {
    redirect("/sign-in");
  }

  const allowed = session?.user?.allowedProjects;
  if (!isAuthDevSkipped() && allowed && !allowed.includes("supply-smb") && session?.user?.role !== "admin") {
    redirect("/ai-insights");
  }

  return <AppShell>{children}</AppShell>;
}
