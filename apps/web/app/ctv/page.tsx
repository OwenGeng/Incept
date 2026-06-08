import { redirect } from "next/navigation";
import { AppShell } from "@/components/layout/app-shell";
import { Topbar } from "@/components/layout/topbar";
import { Card } from "@/components/ui/card";
import { auth } from "@/auth";
import { isAuthDevSkipped } from "@/lib/auth-mode";

export default async function CtvPage() {
  const session = await auth();

  if (!session && !isAuthDevSkipped()) {
    redirect("/sign-in");
  }

  return (
    <AppShell>
      <Topbar title="CTV" subtitle="CTV module scaffold for the next implementation phase." />
      <Card className="p-8">
        <h2 className="text-2xl font-semibold text-foreground">CTV is queued next</h2>
        <p className="mt-4 max-w-3xl text-sm leading-8 text-muted-foreground">
          This surface is reserved for the future CTV module. The current phase focuses
          on Supply SMB, but the navigation and shell are already ready to host the
          CTV-specific KPI, campaign, and AI reporting experience.
        </p>
      </Card>
    </AppShell>
  );
}
