"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { Search, ChevronRight, ArrowLeft } from "lucide-react";
import { DOCS_NAV, type DocsNavChild, type DocsNavSection } from "./docs-nav";

function matchesQuery(label: string, query: string): boolean {
  return label.toLowerCase().includes(query.toLowerCase());
}

function filterSections(sections: DocsNavSection[], query: string): DocsNavSection[] {
  if (!query.trim()) return sections;
  return sections.reduce<DocsNavSection[]>((acc, section) => {
    const sectionMatches = matchesQuery(section.label, query);
    const children = (section.children ?? []).filter((c: DocsNavChild) => matchesQuery(c.label, query));
    if (sectionMatches || children.length > 0) {
      acc.push({ ...section, children: sectionMatches ? section.children : children });
    }
    return acc;
  }, []);
}

export function DocsChrome({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const [query, setQuery] = useState("");

  const sections = useMemo(() => filterSections(DOCS_NAV, query), [query]);

  return (
    <div className="flex min-h-screen flex-col bg-background">
      {/* Top bar */}
      <header className="flex h-16 shrink-0 items-center gap-6 border-b border-border px-6">
        <Link href="/docs" className="flex items-center gap-2 shrink-0">
          <span className="font-semibold text-foreground">Documentation</span>
        </Link>
        <div className="relative w-full max-w-sm">
          <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
          <input
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search docs"
            className="w-full rounded-lg border border-border bg-card py-2 pl-9 pr-3 text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-accent/30"
          />
        </div>
      </header>

      <div className="flex flex-1 min-h-0">
        {/* Sidebar */}
        <nav className="hidden w-64 shrink-0 overflow-y-auto border-r border-border px-4 py-6 sm:block">
          <Link
            href="/"
            className="mb-4 flex items-center gap-2 rounded-lg px-3 py-2 text-sm text-muted-foreground transition-colors hover:bg-muted/60 hover:text-foreground"
          >
            <ArrowLeft className="size-4 shrink-0" />
            Back to Linglong Lab
          </Link>
          <div className="mb-3 border-t border-border" />
          <ul className="space-y-0.5">
            {sections.map((section) => {
              const isSectionActive = pathname === section.href;
              return (
                <li key={section.href}>
                  <Link
                    href={section.href as never}
                    className={`flex items-center gap-2 rounded-lg px-3 py-2 text-sm font-medium transition-colors ${
                      isSectionActive
                        ? "bg-soft-accent text-accent"
                        : "text-foreground hover:bg-muted/60"
                    }`}
                  >
                    <section.icon className="size-4 shrink-0" />
                    {section.label}
                  </Link>
                  {section.children && section.children.length > 0 && (
                    <ul className="mt-0.5 ml-4 space-y-0.5 border-l border-border pl-3">
                      {section.children.map((child) => {
                        const isChildActive = pathname === child.href;
                        return (
                          <li key={child.href}>
                            <Link
                              href={child.href as never}
                              className={`block rounded-lg px-3 py-1.5 text-sm transition-colors ${
                                isChildActive
                                  ? "bg-soft-accent text-accent font-medium"
                                  : "text-muted-foreground hover:bg-muted/60 hover:text-foreground"
                              }`}
                            >
                              {child.label}
                            </Link>
                          </li>
                        );
                      })}
                    </ul>
                  )}
                </li>
              );
            })}
            {sections.length === 0 && (
              <li className="px-3 py-2 text-sm text-muted-foreground">No matching pages</li>
            )}
          </ul>
        </nav>

        {/* Content */}
        <main className="min-w-0 flex-1 overflow-y-auto">{children}</main>
      </div>
    </div>
  );
}

export function DocsBreadcrumb({ trail }: { trail: { label: string; href?: string }[] }) {
  return (
    <div className="mb-6 flex items-center gap-1.5 text-sm text-muted-foreground">
      {trail.map((item, i) => (
        <span key={item.label} className="flex items-center gap-1.5">
          {i > 0 && <ChevronRight className="size-3.5" />}
          {item.href ? (
            <Link href={item.href as never} className="hover:text-foreground">{item.label}</Link>
          ) : (
            <span className="text-foreground">{item.label}</span>
          )}
        </span>
      ))}
    </div>
  );
}
