import { redirect } from "next/navigation";
import { auth } from "@/auth";
import { isAuthDevSkipped } from "@/lib/auth-mode";

export default async function DocsLayout({ children }: { children: React.ReactNode }) {
  const session = await auth();
  if (!session && !isAuthDevSkipped()) {
    redirect("/sign-in");
  }
  return (
    <div className="min-h-screen bg-background">
      {children}
    </div>
  );
}
