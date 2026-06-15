import { auth } from "@/auth";
import { Topbar } from "@/components/layout/topbar";
import { WeeklyBriefView } from "@/components/supply-smb/weekly-brief-view";
import { getWeeklyBrief } from "@/lib/api";
import { defaultPageTabs } from "@/lib/supply-navigation";

export default async function NoSdkNoUaWeeklyBriefPage() {
  const session = await auth();
  const data = await getWeeklyBrief(session?.user);

  return (
    <div>
      <Topbar
        activeHref="/supply-smb/no-sdk-no-ua/weekly-brief"
        title="Supply SMB Cross-Sell"
        subtitle="Weekly meeting brief for the active supply opportunity."
        pageTabs={defaultPageTabs}
      />
      <WeeklyBriefView data={data} />
    </div>
  );
}
