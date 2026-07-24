import { redirect } from "next/navigation";
import { auth } from "@/auth";
import { isAuthDevSkipped } from "@/lib/auth-mode";
import { DocsChrome } from "@/components/docs/DocsChrome";

export default async function DocsLayout({ children }: { children: React.ReactNode }) {
  const session = await auth();
  if (!session && !isAuthDevSkipped()) {
    redirect("/sign-in");
  }
  return <DocsChrome>{children}</DocsChrome>;
}
