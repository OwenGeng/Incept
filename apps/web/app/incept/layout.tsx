import { redirect } from "next/navigation";
import { auth } from "@/auth";
import { isAuthDevSkipped } from "@/lib/auth-mode";
import { AuthSessionProvider } from "@/components/incept/AuthSessionProvider";

export default async function StudioLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const session = await auth();

  if (!session && !isAuthDevSkipped()) {
    redirect("/sign-in");
  }

  // Studio is for all Moloco users. Agency accounts are Scout-only.
  if (session?.user?.role === "agency") {
    redirect("/supply-smb/no-sdk-no-ua/weekly-brief");
  }

  return (
    <AuthSessionProvider>
      {children}
    </AuthSessionProvider>
  );
}
