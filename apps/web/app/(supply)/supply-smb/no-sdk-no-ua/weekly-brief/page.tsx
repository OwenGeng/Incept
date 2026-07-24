import { auth } from "@/auth";
import { Topbar } from "@/components/layout/topbar";
import { WeeklyBriefView } from "@/components/supply-smb/weekly-brief-view";
import { getWeeklyBrief, getWeeklyBriefSummary } from "@/lib/api";
import { defaultPageTabs } from "@/lib/supply-navigation";

export default async function NoSdkNoUaWeeklyBriefPage() {
  const session = await auth();
  // Fast — BQ-cached, no LLM call. Awaited so the page has real numbers on first paint.
  const data = await getWeeklyBrief(session?.user);
  // Slow — hits Gemini on cache miss. NOT awaited here; passed down as a promise
  // so Suspense can stream it in without blocking the Topbar/nav or the rest of the page.
  const summaryPromise = getWeeklyBriefSummary(session?.user);

  return (
    <div>
      <Topbar
        activeHref="/supply-smb/no-sdk-no-ua/weekly-brief"
        title="Supply SMB Cross-Sell"
        subtitle="Weekly meeting brief for the active supply opportunity."
        pageTabs={defaultPageTabs}
      />
      <WeeklyBriefView data={data} summaryPromise={summaryPromise} />
    </div>
  );
}
