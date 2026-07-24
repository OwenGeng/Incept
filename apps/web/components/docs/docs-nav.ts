import type { LucideIcon } from "lucide-react";
import { Home, Paintbrush, BarChart3 } from "lucide-react";

export interface DocsNavChild {
  href: string;
  label: string;
}

export interface DocsNavSection {
  href: string;
  label: string;
  icon: LucideIcon;
  children?: DocsNavChild[];
}

export const DOCS_NAV: DocsNavSection[] = [
  { href: "/docs", label: "Overview", icon: Home },
  { href: "/docs/studio", label: "Studio", icon: Paintbrush },
  {
    href: "/docs/intelligence",
    label: "Intelligence",
    icon: BarChart3,
    children: [
      { href: "/docs/intelligence/cold-prospect-pipeline", label: "Cold Prospect Pipeline" },
    ],
  },
];
