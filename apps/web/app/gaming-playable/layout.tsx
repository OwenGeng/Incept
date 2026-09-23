import { notFound, redirect } from "next/navigation";
import { auth } from "@/auth";
import { GamingPlayableShell } from "@/components/gaming-playable/GamingPlayableShell";
import { isAuthDevSkipped } from "@/lib/auth-mode";
import { isDeferredProductSurfaceEnabled } from "@/lib/release-surfaces";

export default async function GamingPlayableLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  if (!isDeferredProductSurfaceEnabled("gamingPlayable")) notFound();
  const session = await auth();
  if (!session && !isAuthDevSkipped()) redirect("/sign-in?callbackUrl=/gaming-playable");
  if (session?.user?.role === "agency") redirect("/unauthorized");
  return <GamingPlayableShell userName={session?.user?.name}>{children}</GamingPlayableShell>;
}
