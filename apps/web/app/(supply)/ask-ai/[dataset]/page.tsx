import { redirect } from "next/navigation";
import { Topbar } from "@/components/layout/topbar";
import { ChatView } from "@/components/ask-ai/chat-view";
import { askAiDatasetTabs } from "@/lib/supply-navigation";

const VALID_DATASETS = new Set(["no-sdk-no-ua", "sdk-no-ua", "ua-no-sdk"]);

const DATASET_SUBTITLES: Record<string, string> = {
  "no-sdk-no-ua": "Publishers with no SDK and no UA spend — cold cross-sell targets.",
  "sdk-no-ua":    "SDK-integrated publishers with zero Moloco UA spend — warm expansion targets.",
  "ua-no-sdk":    "Active Moloco UA advertisers whose apps have no SDK integration yet.",
};

type Params = Promise<{ dataset: string }>;

export default async function AskAiDatasetPage({ params }: { params: Params }) {
  const { dataset } = await params;
  if (!VALID_DATASETS.has(dataset)) {
    redirect("/ask-ai/no-sdk-no-ua");
  }

  return (
    <div className="flex h-[calc(100vh-56px)] flex-col">
      <Topbar
        title="Ask AI"
        subtitle={DATASET_SUBTITLES[dataset]}
        scopeTabs={askAiDatasetTabs}
        activeScopeHref={`/ask-ai/${dataset}`}
      />
      <div className="min-h-0 flex-1">
        <ChatView module="supply" dataset={dataset} />
      </div>
    </div>
  );
}
