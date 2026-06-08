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
  { label: "Leads Pipeline", href: "/supply-smb/leads" },
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
