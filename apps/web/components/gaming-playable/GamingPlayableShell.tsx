"use client";

import Image from "next/image";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { CircleHelp, FileImage, Grid2X2, LayoutTemplate, Plus, ShieldCheck } from "lucide-react";
import { AppSidebar, type SidebarNavItem } from "@/components/ui/app-sidebar";

const navigation = [
  { kind: "simple" as const, key: "playables", label: "My Playables", icon: Grid2X2, href: "/gaming-playable" },
  { kind: "simple" as const, key: "templates", label: "Templates", icon: LayoutTemplate, href: "/gaming-playable/templates" },
  { kind: "simple" as const, key: "assets", label: "Assets", icon: FileImage, href: "/gaming-playable/assets" },
  { kind: "simple" as const, key: "delivery", label: "Delivery & QA", icon: ShieldCheck, href: "/gaming-playable/delivery" },
] satisfies SidebarNavItem[];

export function GamingPlayableShell({ children, userName }: { children: React.ReactNode; userName?: string | null }) {
  const pathname = usePathname();
  const isActive = (key: string) => key === "playables" ? pathname === "/gaming-playable" : pathname.startsWith(`/gaming-playable/${key}`);

  return (
    <div className="flex min-h-screen bg-[#F7F8FB] text-slate-900">
      <div className="hidden shrink-0 md:block">
        <AppSidebar
          productName="GamingPlayable"
          brandTitle="Linglong"
          brandSubtitle="Lab"
          logo="/logo.png"
          storageKey="gaming-playable"
          expandedWidthClassName="w-60"
          items={navigation}
          isActive={isActive}
          navigationLabel="GamingPlayable navigation"
          primaryAction={{ label: "New playable", icon: Plus, href: "/gaming-playable/new", className: "bg-[#F97316] hover:bg-[#EA580C] focus-visible:ring-[#FB923C]" }}
          activeItemClassName="bg-[#FFF7ED] font-semibold text-[#C2410C]"
          activeIconClassName="text-[#C2410C]"
          user={{ name: userName }}
          footerContent={<Link href="/docs" className="flex h-10 items-center gap-3 rounded-lg px-3 text-sm font-medium text-slate-600 transition hover:bg-slate-100 hover:text-slate-950"><CircleHelp className="size-4" />Playable specs</Link>}
        />
      </div>
      <div className="min-w-0 flex-1">
        <header className="sticky top-0 z-20 flex h-[72px] items-center justify-between border-b border-slate-200 bg-white/95 px-5 backdrop-blur md:px-8">
          <Link href="/" aria-label="Return to Linglong home" className="flex items-center gap-2 rounded-lg focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#FB923C] md:hidden"><Image src="/logo.png" alt="Linglong" width={32} height={32} className="size-8 rounded-lg object-contain" /><span className="text-sm font-semibold">GamingPlayable</span></Link>
          <div className="hidden text-sm text-slate-500 md:block">Interactive ad creation workspace</div>
          <div className="flex items-center gap-3"><a href="/docs" className="text-sm font-medium text-slate-600 hover:text-slate-950">Help</a><span className="hidden rounded-full border border-[#FED7AA] bg-[#FFF7ED] px-3 py-1 text-xs font-semibold text-[#C2410C] sm:inline">HTML5 playable</span></div>
        </header>
        {children}
      </div>
    </div>
  );
}
