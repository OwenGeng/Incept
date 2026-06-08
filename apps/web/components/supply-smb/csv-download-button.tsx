"use client";

/**
 * CsvDownloadButton — tiny client component that triggers a CSV download.
 *
 * Usage: embed inside any server component that has the table data available.
 * The button does NOT need the data at render time — only on click.
 */

import { Download } from "lucide-react";
import { downloadCsv } from "@/lib/csv-export";

type Props = {
  headers: string[];
  rows: (string | number | boolean | null | undefined)[][];
  filename: string;
  /** Extra classes for the button wrapper */
  className?: string;
};

export function CsvDownloadButton({ headers, rows, filename, className }: Props) {
  return (
    <button
      onClick={() => downloadCsv(headers, rows, filename)}
      title="Download CSV"
      className={
        className ??
        "inline-flex h-8 w-8 items-center justify-center rounded-lg border border-border bg-card text-muted-foreground transition hover:border-accent hover:text-accent"
      }
    >
      <Download className="size-3.5" />
    </button>
  );
}
