import Link from "next/link";
import { ArrowRight, Paintbrush } from "lucide-react";
import { DocsBreadcrumb } from "@/components/docs/DocsChrome";

const MODULES = [
  {
    href: "/docs/studio",
    icon: Paintbrush,
    title: "Studio",
    description: "Image, video, and Kakao Bizboard creative generation — workflows, controls, and validation rules.",
  },
];

export default function DocsIndexPage() {
  return (
    <div className="mx-auto max-w-4xl px-8 py-10 pb-20">
      <DocsBreadcrumb trail={[{ label: "Overview" }]} />

      <div className="mb-10">
        <h1 className="text-4xl font-semibold tracking-tight text-foreground">Overview</h1>
        <p className="mt-4 text-sm leading-7 text-muted-foreground max-w-2xl">
          Incept is Moloco&apos;s creative-generation and supply-intelligence platform. Documentation is organized
          by module — pick one below to get started.
        </p>
      </div>

      <div className="grid gap-4 sm:grid-cols-2">
        {MODULES.map((m) => (
          <Link
            key={m.href}
            href={m.href as never}
            className="group flex flex-col gap-3 rounded-2xl border border-border bg-card p-6 transition-colors hover:bg-muted/40"
          >
            <div className="flex items-center justify-between">
              <div className="flex size-10 items-center justify-center rounded-xl bg-soft-accent">
                <m.icon className="size-5 text-accent" />
              </div>
              <ArrowRight className="size-4 text-muted-foreground transition-transform group-hover:translate-x-0.5" />
            </div>
            <div>
              <p className="font-semibold text-foreground">{m.title}</p>
              <p className="mt-1 text-sm text-muted-foreground">{m.description}</p>
            </div>
          </Link>
        ))}
      </div>
    </div>
  );
}
