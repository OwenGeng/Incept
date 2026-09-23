"use client";

import Image from "next/image";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { FormEvent, useState } from "react";
import { Archive, Plus, Search, Settings2 } from "lucide-react";

export function VideoProductionShell({ children }: { children: React.ReactNode; userName?: string | null }) {
  const router = useRouter();
  const [projectQuery, setProjectQuery] = useState("");

  function submitProjectSearch(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const query = projectQuery.trim();
    router.push(query ? `/video-production?q=${encodeURIComponent(query)}` : "/video-production");
  }

  return <div className="min-h-screen bg-white text-[#101318]">
    <header className="sticky top-0 z-20 flex h-[72px] items-center border-b border-[#e6e8ec] bg-white/95 px-5 backdrop-blur md:px-10">
      <div className="mx-auto flex w-full max-w-[1440px] items-center gap-4">
        <Link href="/video-production" className="flex shrink-0 items-center gap-2.5" aria-label="Linglong Production home">
          <Image src="/logo.png" alt="Linglong" width={32} height={32} className="size-8 rounded-lg object-contain" />
          <span className="text-lg font-semibold tracking-[-0.035em]">Linglong</span>
          <span className="hidden border-l border-[#d7dbe2] pl-2.5 text-xs font-medium text-[#5f6673] sm:inline">Production</span>
        </Link>
        <form className="relative ml-1 hidden max-w-[360px] flex-1 md:block" onSubmit={submitProjectSearch}>
          <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-[#5f6673]" />
          <input aria-label="Search projects" value={projectQuery} onChange={(event) => setProjectQuery(event.target.value)} placeholder="Search projects" className="h-10 w-full rounded-xl border border-[#e6e8ec] bg-[#fafbfc] pl-9 pr-3 text-sm outline-none placeholder:text-[#7b828e] focus:border-[#171a20]" />
        </form>
        <nav className="ml-auto flex items-center gap-2">
          <Link href="/video-production/assets" className="hidden h-10 items-center gap-2 rounded-lg border border-[#e6e8ec] bg-white px-3 text-xs font-semibold text-[#171a20] hover:bg-[#fafbfc] sm:inline-flex"><Archive className="size-3.5" />Asset library</Link>
          <Link href="/video-production/new" className="inline-flex h-10 items-center gap-2 rounded-lg bg-[#171a20] px-3.5 text-xs font-semibold text-white hover:bg-[#30343c]"><Plus className="size-4" />Create project</Link>
          <Link href="/video-production/delivery" className="grid size-9 place-items-center rounded-lg text-[#5f6673] hover:bg-[#f6f8fb] hover:text-[#171a20]" aria-label="Delivery settings"><Settings2 className="size-4" /></Link>
        </nav>
      </div>
    </header>
    {children}
  </div>;
}
