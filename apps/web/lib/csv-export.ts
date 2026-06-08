/**
 * csv-export.ts — client-side CSV serialization and download utility.
 * Call downloadCsv() only from browser (client components / event handlers).
 */

type CellValue = string | number | boolean | null | undefined;

/** Wrap a cell value in quotes if it contains commas, quotes, or newlines. */
function escapeCell(value: CellValue): string {
  const s = value === null || value === undefined ? "" : String(value);
  if (s.includes(",") || s.includes('"') || s.includes("\n")) {
    return `"${s.replace(/"/g, '""')}"`;
  }
  return s;
}

/** Convert headers + rows to a CSV string. */
export function toCsvString(headers: string[], rows: CellValue[][]): string {
  const lines = [
    headers.map(escapeCell).join(","),
    ...rows.map((row) => row.map(escapeCell).join(",")),
  ];
  return lines.join("\n");
}

/**
 * Trigger a browser download of the given data as a CSV file.
 *
 * @param headers  Column header labels
 * @param rows     Data rows
 * @param filename Download file name (e.g. "top-companies.csv")
 */
export function downloadCsv(
  headers: string[],
  rows: CellValue[][],
  filename: string,
): void {
  const csv = toCsvString(headers, rows);
  const blob = new Blob(["﻿" + csv], { type: "text/csv;charset=utf-8;" }); // BOM for Excel
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename.endsWith(".csv") ? filename : `${filename}.csv`;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}
