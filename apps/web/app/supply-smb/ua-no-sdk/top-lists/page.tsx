import { auth } from "@/auth";
import { Topbar } from "@/components/layout/topbar";
import { DatasetTopListsView } from "@/components/supply-smb/dataset-top-lists-view";
import { getDatasetTopLists } from "@/lib/api";
import { genericAnalysisTabs } from "@/lib/supply-navigation";

type SearchParams = Promise<{
  search?: string;
  routing?: string;
  hqCountry?: string;
  monetization?: string;
  companySortBy?: string;
  companySortDir?: string;
  appSortBy?: string;
  appSortDir?: string;
  companyPage?: string;
  appPage?: string;
}>;

export default async function UaNoSdkTopListsPage({ searchParams }: { searchParams?: SearchParams }) {
  const session = await auth();
  const query = (await searchParams) ?? {};
  const basePath = "/supply-smb/ua-no-sdk/top-lists";
  const data = await getDatasetTopLists("list-3", session?.user, query);

  return (
    <div className="min-w-0">
      <Topbar
        activeHref={basePath}
        title="Supply SMB — UA + No SDK"
        subtitle={data.subtitle}
        pageTabs={genericAnalysisTabs("/supply-smb/ua-no-sdk")}
      />
      <DatasetTopListsView data={data} query={query} basePath={basePath} />
    </div>
  );
}
