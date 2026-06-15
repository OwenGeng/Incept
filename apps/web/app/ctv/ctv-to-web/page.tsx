import { Topbar } from "@/components/layout/topbar";
import { Card } from "@/components/ui/card";
import { Globe } from "lucide-react";

export default function CtvToWebPage() {
  return (
    <>
      <Topbar title="CTV to Web" subtitle="Cross-screen analytics for CTV-to-web conversion." />
      <Card className="p-10 text-center">
        <div className="mx-auto mb-5 flex size-16 items-center justify-center rounded-2xl bg-gradient-to-br from-[#3a86ff] to-[#356fec] shadow-lg">
          <Globe className="size-8 text-white" />
        </div>
        <h2 className="text-xl font-semibold text-foreground">CTV to Web — Coming Soon</h2>
        <p className="mx-auto mt-3 max-w-md text-sm leading-7 text-muted-foreground">
          This module will surface downstream web impact of your CTV inventory —
          conversion funnels, audience overlap, and attribution analytics.
        </p>
      </Card>
    </>
  );
}
