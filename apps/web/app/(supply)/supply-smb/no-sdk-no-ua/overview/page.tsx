import { auth } from "@/auth";
import { Topbar } from "@/components/layout/topbar";
import { ColdProspectOverviewView } from "@/components/supply-smb/cold-prospect-overview-view";
import { getColdProspectOverview, getColdProspectApps } from "@/lib/api";

const INTELLIGENCE_TABS = [
  { label: "Overview", href: "/supply-smb/no-sdk-no-ua/overview" },
  { label: "Weekly Brief", href: "/supply-smb/no-sdk-no-ua/weekly-brief" },
  { label: "Top Lists", href: "/supply-smb/no-sdk-no-ua/top-lists" },
  { label: "Detailed Analysis", href: "/supply-smb/no-sdk-no-ua/detailed-analysis" },
];

export default async function ColdProspectOverviewPage() {
  const session = await auth();

  const [overview, appsPayload] = await Promise.all([
    getColdProspectOverview(session?.user),
    getColdProspectApps(session?.user, { page: "1" }),
  ]);

  return (
    <div className="min-w-0">
      <Topbar
        activeHref="/supply-smb/no-sdk-no-ua/overview"
        title="Intelligence"
        subtitle="Cold Prospect Pipeline — No SDK + No UA"
        pageTabs={INTELLIGENCE_TABS}
      />
      <ColdProspectOverviewView overview={overview} apps={appsPayload} />
    </div>
  );
}
