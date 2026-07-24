export type SupplyScopeKey = "no-sdk-no-ua" | "sdk-no-ua" | "ua-no-sdk";

export const supplyScopeTabs = [
  {
    key: "no-sdk-no-ua" as const,
    label: "No SDK + No UA",
    href: "/supply-smb/no-sdk-no-ua/weekly-brief",
  },
  {
    key: "sdk-no-ua" as const,
    label: "SDK + No UA",
    href: "/supply-smb/sdk-no-ua/list-1/top-lists",
  },
  {
    key: "ua-no-sdk" as const,
    label: "UA + No SDK",
    href: "/supply-smb/ua-no-sdk/top-lists",
  },
];

export const defaultPageTabs = [
  { label: "Weekly Brief", href: "/supply-smb/no-sdk-no-ua/weekly-brief" },
  { label: "Top Lists", href: "/supply-smb/no-sdk-no-ua/top-lists" },
  { label: "Detailed Analysis", href: "/supply-smb/no-sdk-no-ua/detailed-analysis" },
];

export const leadsPageTabs = [
  { label: "Weekly Brief", href: "/supply-smb/no-sdk-no-ua/weekly-brief" },
  { label: "Top Lists", href: "/supply-smb/no-sdk-no-ua/top-lists" },
  { label: "Detailed Analysis", href: "/supply-smb/no-sdk-no-ua/detailed-analysis" },
  { label: "Leads Pipeline", href: "/supply-smb/leads" },
];


export const genericAnalysisTabs = (baseHref: string) => [
  { label: "Top Lists", href: `${baseHref}/top-lists` },
  { label: "Detailed Analysis", href: `${baseHref}/detailed-analysis` },
];

export const aiInsightsScopeTabs = [
  { label: "No SDK + No UA", href: "/ai-insights/no-sdk-no-ua", scope: "no-sdk-no-ua" },
  { label: "SDK + No UA",    href: "/ai-insights/sdk-no-ua",    scope: "sdk-no-ua" },
  { label: "UA + No SDK",    href: "/ai-insights/ua-no-sdk",    scope: "ua-no-sdk" },
];

export const askAiDatasetTabs = [
  { label: "No SDK + No UA", href: "/ask-ai/no-sdk-no-ua", dataset: "no-sdk-no-ua" },
  { label: "SDK + No UA",    href: "/ask-ai/sdk-no-ua",    dataset: "sdk-no-ua" },
  { label: "UA + No SDK",    href: "/ask-ai/ua-no-sdk",    dataset: "ua-no-sdk" },
];
