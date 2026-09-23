import { notFound, redirect } from "next/navigation";
import { auth } from "@/auth";
import { isAuthDevSkipped } from "@/lib/auth-mode";
import { VideoProductionShell } from "@/components/video-production/VideoProductionShell";
import { isDeferredProductSurfaceEnabled } from "@/lib/release-surfaces";

export default async function VideoProductionLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  if (!isDeferredProductSurfaceEnabled("videoProduction")) notFound();
  const session = await auth();
  if (!session && !isAuthDevSkipped()) redirect("/sign-in?callbackUrl=/video-production");
  if (session?.user?.role === "agency") redirect("/unauthorized");
  return <VideoProductionShell userName={session?.user?.name}>{children}</VideoProductionShell>;
}
