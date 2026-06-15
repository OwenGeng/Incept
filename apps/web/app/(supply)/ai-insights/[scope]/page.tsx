import { Suspense } from "react";
import { redirect } from "next/navigation";
import { auth } from "@/auth";
import { Topbar } from "@/components/layout/topbar";
import { AiInsightsView } from "@/components/ai-insights/ai-insights-view";
import { getAiInsights } from "@/lib/api";
import { aiInsightsScopeTabs } from "@/lib/supply-navigation";
import { PageSkeleton } from "@/components/ui/page-skeleton";

const VALID_SCOPES = new Set(["no-sdk-no-ua", "sdk-no-ua", "ua-no-sdk"]);

const SCOPE_SUBTITLES: Record<string, string> = {
  "no-sdk-no-ua": "Publishers with no Moloco SDK and no UA spend — cold cross-sell targets.",
  "sdk-no-ua":    "Publishers with SDK integrated but zero Moloco UA spend — warm SDK expansion.",
  "ua-no-sdk":    "Active Moloco UA advertisers whose apps have no SDK integration yet.",
};

type Params = Promise<{ scope: string }>;

async function InsightsContent({ scope }: { scope: string }) {
  const session = await auth();
  const data = await getAiInsights(session?.user ?? undefined, scope);
  return <AiInsightsView data={data} />;
}

export default async function AiInsightsScopePage({ params }: { params: Params }) {
  const { scope } = await params;
  if (!VALID_SCOPES.has(scope)) {
    redirect("/ai-insights/no-sdk-no-ua");
  }

  return (
    <>
      <Topbar
        title="AI Insights"
        subtitle={SCOPE_SUBTITLES[scope]}
        scopeTabs={aiInsightsScopeTabs}
        activeScopeHref={`/ai-insights/${scope}`}
      />
      <Suspense fallback={<PageSkeleton variant="analysis" />}>
        <InsightsContent scope={scope} />
      </Suspense>
    </>
  );
}
