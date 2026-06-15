import { auth } from "@/auth";
import { Topbar } from "@/components/layout/topbar";
import { DetailedAnalysisView } from "@/components/supply-smb/detailed-analysis-view";
import { getDatasetDetailedAnalysis } from "@/lib/api";
import { genericAnalysisTabs } from "@/lib/supply-navigation";

export default async function UaNoSdkDetailedAnalysisPage() {
  const session = await auth();
  const data = await getDatasetDetailedAnalysis("list-3", session?.user);

  return (
    <div>
      <Topbar
        activeHref="/supply-smb/ua-no-sdk/detailed-analysis"
        title="Supply SMB Cross-Sell"
        subtitle="Distribution charts for the UA + No SDK prospect pool."
        pageTabs={genericAnalysisTabs("/supply-smb/ua-no-sdk")}
      />
      <DetailedAnalysisView data={data} />
    </div>
  );
}
