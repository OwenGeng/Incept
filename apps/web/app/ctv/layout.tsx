import { redirect } from "next/navigation";
import { auth } from "@/auth";
import { isAuthDevSkipped } from "@/lib/auth-mode";
import { CtvAppShell } from "@/components/layout/ctv-app-shell";

export default async function CtvLayout({ children }: { children: React.ReactNode }) {
  const session = await auth();
  if (!session && !isAuthDevSkipped()) {
    redirect("/sign-in");
  }
  return <CtvAppShell>{children}</CtvAppShell>;
}
