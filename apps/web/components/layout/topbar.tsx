/**
 * Topbar — Scout page header.
 * Delegates to the shared AppHeader (variant="page") so all pages
 * automatically get the Feedback + Docs buttons.
 */

import { AppHeader } from "@/components/ui/app-header";
import { defaultPageTabs } from "@/lib/supply-navigation";

type NavTab = { label: string; href: string };

export function Topbar({
  activeHref,
  title,
  subtitle,
  pageTabs = defaultPageTabs,
  scopeTabs,
  activeScopeHref,
  datasetTabs,
  activeDatasetHref,
}: {
  activeHref?: string;
  title: string;
  subtitle: string;
  pageTabs?: NavTab[];
  scopeTabs?: NavTab[];
  activeScopeHref?: string;
  datasetTabs?: NavTab[];
  activeDatasetHref?: string;
}) {
  return (
    <AppHeader
      variant="page"
      title={title}
      subtitle={subtitle}
      showActions
      activeHref={activeHref}
      pageTabs={pageTabs}
      scopeTabs={scopeTabs}
      activeScopeHref={activeScopeHref}
      datasetTabs={datasetTabs}
      activeDatasetHref={activeDatasetHref}
    />
  );
}
