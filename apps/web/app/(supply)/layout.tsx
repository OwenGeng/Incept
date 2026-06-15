import { redirect } from "next/navigation";
import { auth } from "@/auth";
import { isAuthDevSkipped } from "@/lib/auth-mode";
import { AppShell } from "@/components/layout/app-shell";

export default async function SupplyGroupLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const session = await auth();
  if (!session && !isAuthDevSkipped()) {
    redirect("/sign-in");
  }
  return <AppShell>{children}</AppShell>;
}
