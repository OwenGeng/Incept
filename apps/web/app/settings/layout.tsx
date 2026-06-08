import { redirect } from "next/navigation";
import { auth } from "@/auth";
import { AppShell } from "@/components/layout/app-shell";
import { isAuthDevSkipped } from "@/lib/auth-mode";

export default async function SettingsLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const session = await auth();

  if (!session && !isAuthDevSkipped()) {
    redirect("/sign-in");
  }

  // Only admins can access settings routes
  if (!isAuthDevSkipped() && session?.user?.role !== "admin") {
    redirect("/unauthorized");
  }

  return <AppShell>{children}</AppShell>;
}
