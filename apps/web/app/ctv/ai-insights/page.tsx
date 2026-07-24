import { Topbar } from "@/components/layout/topbar";
import { Card } from "@/components/ui/card";
import { Sparkles } from "lucide-react";

export default function CtvAiInsightsPage() {
  return (
    <>
      <Topbar title="AI Insights" subtitle="AI-powered CTV intelligence and trend analysis." docsHref="/docs" />
      <Card className="p-10 text-center">
        <div className="mx-auto mb-5 flex size-16 items-center justify-center rounded-2xl bg-gradient-to-br from-[#f97316] to-[#ea580c] shadow-lg">
          <Sparkles className="size-8 text-white" />
        </div>
        <h2 className="text-xl font-semibold text-foreground">CTV AI Insights — Coming Soon</h2>
        <p className="mx-auto mt-3 max-w-md text-sm leading-7 text-muted-foreground">
          Weekly AI analysis with historical memory — trend detection, anomaly alerts,
          and strategic recommendations for your CTV business.
        </p>
      </Card>
    </>
  );
}
