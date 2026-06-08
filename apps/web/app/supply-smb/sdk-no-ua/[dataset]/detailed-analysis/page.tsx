import { auth } from "@/auth";
import { Topbar } from "@/components/layout/topbar";
import { DetailedAnalysisView } from "@/components/supply-smb/detailed-analysis-view";
import { getDatasetDetailedAnalysis } from "@/lib/api";
import { genericAnalysisTabs } from "@/lib/supply-navigation";

type Params = Promise<{ dataset: string }>;

const DATASET_LABELS: Record<string, string> = {
  "list-1": "List 1 — Cold Prospect · SDK integrated, no Moloco UA yet",
  "list-2": "List 2 — Expansion · Some UA exists, untapped SDK apps remain",
};

export default async function SdkNoUaDetailedAnalysisPage({ params }: { params: Params }) {
  const session = await auth();
  const { dataset } = await params;
  const datasetKey = ["list-1", "list-2"].includes(dataset) ? dataset : "list-1";
  const basePath = `/supply-smb/sdk-no-ua/${dataset}`;
  const data = await getDatasetDetailedAnalysis(datasetKey, session?.user);

  return (
    <div>
      <Topbar
        activeHref={`${basePath}/detailed-analysis`}
        title="Supply SMB — SDK + No UA"
        subtitle={DATASET_LABELS[datasetKey] ?? "Evidence layer for SDK-integrated, no-UA expansion paths."}
        pageTabs={genericAnalysisTabs(basePath)}
      />
      <DetailedAnalysisView data={data} />
    </div>
  );
}
