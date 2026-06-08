import { auth } from "@/auth";
import { Topbar } from "@/components/layout/topbar";
import { LeadsView } from "@/components/supply-smb/leads-view";
import { getLeads } from "@/lib/api";
import { leadsPageTabs } from "@/lib/supply-navigation";

type SearchParams = Promise<{ attribution?: string }>;

export default async function LeadsPage({ searchParams }: { searchParams?: SearchParams }) {
  const session = await auth();
  const params = (await searchParams) ?? {};
  const withAttribution = params.attribution === "true";
  const data = await getLeads(session?.user ?? undefined, withAttribution);

  return (
    <div>
      <Topbar
        activeHref="/supply-smb/leads"
        title="Supply SMB Cross-Sell"
        subtitle="Lead pipeline — track companies sent to agencies and attribute DSP conversions."
        pageTabs={leadsPageTabs}
      />
      <LeadsView data={data} />
    </div>
  );
}
