export type PriorityTier = "P1" | "P2" | "P3";

export interface BriefMetric {
  label: string;
  value: string;
  note: string;
}

export interface SelectionStep {
  title: string;
  subtitle: string;
  detail: string;
}

export interface PriorityCard {
  tier: PriorityTier;
  label: string;
  companies: number;
  apps?: number;
  delta: string;
  note: string;
  route: string;
}

export interface HighlightCard {
  label: string;
  value: string;
  detail: string;
}

export interface SupportingChart {
  title: string;
  description: string;
  rows: Array<{
    label: string;
    value: number;
    display: string;
    color: string;
  }>;
}

export interface FunnelStep {
  label: string;
  description: string;
  companies: number;
  apps: number;
}

export interface WeeklyBriefPayload {
  title: string;
  dateRange: string;
  refreshStatus: string;
  summary: string;
  opportunity: string;
  bigThings: string[];
  weekChanges: string[];
  selectionSteps: SelectionStep[];
  priorities: PriorityCard[];
  highlights: HighlightCard[];
  supportingCharts: SupportingChart[];
  funnelSteps: FunnelStep[];
}

export interface WeeklyBriefSummaryPayload {
  summary: string;
  opportunity: string;
  bigThings: string[];
  weekChanges: string[];
}

export interface CompanyRow {
  companyName: string;
  priority: PriorityTier;
  companyProspectLabel: string;
  hqCountry: string;
  finalHqCountry: string;
  website: string;
  teamRouting: string;
  appCount: number;
  totalApps: number;
  osMix: string;
  genres: string;
  totalDownloads: number;
  totalDownloadsLatestMonth: number;
  totalMau: number;
  maxPaidFrac: number;
  monetizationTypes: string;
  anyActiveUa: boolean;
  allUaNetworks: string;
  allActiveNetworks: string;
  isMolocoSupplyVisible: boolean;
  anyMolocoSupply: boolean;
  molocoMediaCost30d: number;
}

export interface AppRow {
  appMarketBundle: string;
  os: string;
  priority: PriorityTier;
  prospectLabel: string;
  appName: string;
  companyName: string;
  teamRouting: string;
  genre: string;
  monetizationType: string;
  downloadsLatestMonth: number;
  downloadGrowthRateMom: number;
  activeUaNetworks: string;
  isMolocoSupplyVisible: boolean;
  molocoMediaCostUsd30d: number;
  topDlCountryT1: string;
  activeOtherExchangeSdks: string;
}

export interface TopListsPayload {
  filters: Array<{
    label: string;
    value: string;
    tone?: "default" | "blue" | "purple" | "green";
  }>;
  companies: CompanyRow[];
  apps: AppRow[];
  companyPage: number;
  companyTotal: number;
  appPage: number;
  appTotal: number;
  pageSize: number;
}

export interface AnalysisRow {
  label: string;
  value: string;
  amount: number;
  color?: string;
}

export interface AnalysisGroup {
  label: string;
  segments: AnalysisRow[];
}

export interface AnalysisModule {
  title: string;
  caption: string;
  /** "bar" = horizontal bar (default), "pie" = donut, "stacked_group" = grouped stacked bars */
  chartType?: "bar" | "pie" | "stacked_group";
  rows: AnalysisRow[];
  groups?: AnalysisGroup[];
}

export interface MethodologySection {
  title: string;
  items: string[];
}

export interface DetailedAnalysisPayload {
  modules: AnalysisModule[];
  methodology: MethodologySection[];
}

export interface GenericTableColumn {
  key: string;
  label: string;
  format: "text" | "number" | "currency" | "percent" | "boolean" | "badge";
  width?: string | null;
}

export interface GenericTableRow {
  key: string;
  cells: Record<string, string | number | boolean | null>;
}

export interface GenericTablePayload {
  title: string;
  subtitle: string;
  columns: GenericTableColumn[];
  rows: GenericTableRow[];
  page: number;
  total: number;
  pageSize: number;
  sortBy: string;
  sortDir: string;
}

export interface FilterOption {
  label: string;
  value: string;
}

export interface FilterControl {
  key: string;
  label: string;
  options: FilterOption[];
}

export interface GenericTopListsPayload {
  datasetKey: string;
  title: string;
  subtitle: string;
  filters: Array<{
    label: string;
    value: string;
    tone?: "default" | "blue" | "purple" | "green";
  }>;
  controls: FilterControl[];
  companiesTable: GenericTablePayload;
  appsTable: GenericTablePayload;
}

// ── Lead Tracking ─────────────────────────────────────────────────────────────

export interface LeadCreate {
  companyName: string;
  listSource: string;
  teamRouting: string;
  sentToTeam: string;
  notes?: string;
  activatedBy: string;
}

export interface LeadRecord {
  leadId: string;
  companyName: string;
  listSource: string;
  teamRouting: string;
  sentToTeam: string;
  notes: string;
  activatedBy: string;
  status: "sent" | "opened" | "spending";
  activatedDate: string;
  lastUpdated: string;
  convertedDate?: string;
  totalSpend90d?: number;
  isAttributed: boolean;
}

export interface LeadListPayload {
  leads: LeadRecord[];
  total: number;
  attributedCount: number;
  spendingCount: number;
}

export interface RefreshSnapshotResponse {
  weekStartDate: string;
  snapshotWritten: boolean;
  message: string;
}
