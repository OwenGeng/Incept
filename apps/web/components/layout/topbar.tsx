/**
 * Topbar — Scout page header.
 * Delegates to the shared AppHeader (variant="page") so all pages
 * automatically get the Feedback + Docs buttons.
 */

import { AppHeader } from "@/components/ui/app-header";

type NavTab = { label: string; href: string };

export function Topbar({
  activeHref,
  title,
  subtitle,
  pageTabs = [],
  scopeTabs,
  activeScopeHref,
  datasetTabs,
  activeDatasetHref,
  docsHref = "/docs",
}: {
  activeHref?: string;
  title: string;
  subtitle: string;
  pageTabs?: NavTab[];
  scopeTabs?: NavTab[];
  activeScopeHref?: string;
  datasetTabs?: NavTab[];
  activeDatasetHref?: string;
  /** Docs link target @default "/docs" — override for a page's own docs subpage */
  docsHref?: string;
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
      docsHref={docsHref}
    />
  );
}
