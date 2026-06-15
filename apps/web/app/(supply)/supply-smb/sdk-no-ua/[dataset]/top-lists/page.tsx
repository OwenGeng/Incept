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

type Params = Promise<{ dataset: string }>;

const DATASET_LABELS: Record<string, string> = {
  "list-1": "List 1 — Cold Prospect · SDK integrated, no Moloco UA yet",
  "list-2": "List 2 — Expansion · Some UA exists, untapped SDK apps remain",
};

export default async function SdkNoUaTopListsPage({
  params,
  searchParams,
}: {
  params: Params;
  searchParams?: SearchParams;
}) {
  const session = await auth();
  const { dataset } = await params;
  const query = (await searchParams) ?? {};
  const datasetKey = ["list-1", "list-2"].includes(dataset) ? dataset : "list-1";
  const basePath = `/supply-smb/sdk-no-ua/${dataset}/top-lists`;
  const data = await getDatasetTopLists(datasetKey, session?.user, query);

  return (
    <div className="min-w-0">
      <Topbar
        activeHref={basePath}
        title="Supply SMB — SDK + No UA"
        subtitle={DATASET_LABELS[datasetKey] ?? data.subtitle}
        pageTabs={genericAnalysisTabs(`/supply-smb/sdk-no-ua/${dataset}`)}
      />
      <DatasetTopListsView data={data} query={query} basePath={basePath} />
    </div>
  );
}
