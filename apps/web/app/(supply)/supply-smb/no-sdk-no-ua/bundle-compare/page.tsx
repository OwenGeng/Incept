import { auth } from "@/auth";
import { Topbar } from "@/components/layout/topbar";
import { BundleCompareView } from "@/components/supply-smb/bundle-compare-view";
import { defaultPageTabs } from "@/lib/supply-navigation";

export default async function BundleComparePage() {
  await auth();
  return (
    <div>
      <Topbar
        activeHref="/supply-smb/no-sdk-no-ua/bundle-compare"
        title="Supply SMB Cross-Sell"
        subtitle="Upload external data (广大大 / SensorTower) to tag bundle IDs with Moloco status."
        pageTabs={defaultPageTabs}
      />
      <BundleCompareView />
    </div>
  );
}
