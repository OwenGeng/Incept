import { auth } from "@/auth";
import { Topbar } from "@/components/layout/topbar";
import { DetailedAnalysisView } from "@/components/supply-smb/detailed-analysis-view";
import { getDetailedAnalysis } from "@/lib/api";
import { defaultPageTabs } from "@/lib/supply-navigation";

export default async function NoSdkNoUaDetailedAnalysisPage() {
  const session = await auth();
  const data = await getDetailedAnalysis(session?.user);

  return (
    <div>
      <Topbar
        activeHref="/supply-smb/no-sdk-no-ua/detailed-analysis"
        title="Supply SMB Cross-Sell"
        subtitle="Distribution charts for the No SDK + No UA prospect pool."
        pageTabs={defaultPageTabs}
      />
      <DetailedAnalysisView data={data} />
    </div>
  );
}
