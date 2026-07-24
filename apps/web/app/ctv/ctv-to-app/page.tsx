import { Topbar } from "@/components/layout/topbar";
import { Card } from "@/components/ui/card";
import { Smartphone } from "lucide-react";

export default function CtvToAppPage() {
  return (
    <>
      <Topbar title="CTV to App" subtitle="Cross-screen attribution for CTV-to-app installs and engagement." docsHref="/docs" />
      <Card className="p-10 text-center">
        <div className="mx-auto mb-5 flex size-16 items-center justify-center rounded-2xl bg-gradient-to-br from-[#8338ec] to-[#6d28d9] shadow-lg">
          <Smartphone className="size-8 text-white" />
        </div>
        <h2 className="text-xl font-semibold text-foreground">CTV to App — Coming Soon</h2>
        <p className="mx-auto mt-3 max-w-md text-sm leading-7 text-muted-foreground">
          This module will track app install and engagement signals driven by CTV exposure —
          cross-device attribution, install lift, and retention analytics.
        </p>
      </Card>
    </>
  );
}
