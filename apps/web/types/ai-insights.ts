export interface InsightItem {
  type: "action" | "alert" | "trend" | "success";
  text: string;
  detail?: string;
  severity: "warning" | "info" | "success" | "neutral";
}

export interface AgentStatus {
  name: string;
  status: "live" | "warming" | "idle";
  detail: string;
  badge?: string | null;
}

export interface ActivityItem {
  companyName?: string | null;
  action: string;
  detail: string;
  date: string;
  activatedBy?: string | null;
}

export interface CallPrepCompany {
  companyName: string;
  prospectLabel: string;
  hqCountry: string;
  teamRouting: string;
  totalApps: number;
  isSupplyVisible: boolean;
}

export interface AiInsightsPayload {
  insights: InsightItem[];
  agents: AgentStatus[];
  recentActivity: ActivityItem[];
  callPrepCompanies: CallPrepCompany[];
  memorySummary: string;
  totalProspects: number;
  p1Count: number;
  p2Count: number;
  leadsTotal: number;
  spendingCount: number;
}
