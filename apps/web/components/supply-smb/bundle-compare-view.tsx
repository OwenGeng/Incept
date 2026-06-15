"use client";

import { useRef, useState } from "react";

// ── Types ──────────────────────────────────────────────────────────────────────

type EnrichedRow = Record<string, string>;

const DIAGNOSIS_OPTIONS = [
  { value: "all",      label: "All" },
  { value: "✅ PROSPECT",      label: "✅ Prospect" },
  { value: "① HAS_SDK",        label: "① Has SDK" },
  { value: "② HAS_UA",         label: "② Has UA" },
  { value: "③ PURE_IAP",       label: "③ Pure IAP" },
  { value: "④ NOT_IN_ST",      label: "④ Not in ST" },
  { value: "⑤ FREE",           label: "⑤ Free" },
];

const DIAGNOSIS_COLORS: Record<string, string> = {
  "✅ PROSPECT":   "bg-emerald-100 text-emerald-800",
  "① HAS_SDK":    "bg-blue-100 text-blue-800",
  "② HAS_UA":     "bg-purple-100 text-purple-800",
  "③ PURE_IAP":   "bg-yellow-100 text-yellow-800",
  "④ NOT_IN_ST":  "bg-gray-100 text-gray-600",
  "⑤ FREE":       "bg-gray-100 text-gray-500",
  "⚠ NO_BUNDLE_ID": "bg-red-100 text-red-700",
};

// ── Helpers ────────────────────────────────────────────────────────────────────

function diagnosisColor(d: string): string {
  return DIAGNOSIS_COLORS[d] ?? "bg-gray-100 text-gray-600";
}

function countBy(rows: EnrichedRow[], key: string): Record<string, number> {
  const out: Record<string, number> = {};
  for (const r of rows) {
    const v = r[key] ?? "—";
    out[v] = (out[v] ?? 0) + 1;
  }
  return out;
}

function downloadCsv(rows: EnrichedRow[], filename: string) {
  if (!rows.length) return;
  const headers = Object.keys(rows[0]);
  const escape = (v: string) => `"${(v ?? "").replace(/"/g, '""')}"`;
  const lines = [
    headers.map(escape).join(","),
    ...rows.map((r) => headers.map((h) => escape(r[h] ?? "")).join(",")),
  ];
  const blob = new Blob([lines.join("\n")], { type: "text/csv;charset=utf-8;" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

// ── Component ──────────────────────────────────────────────────────────────────

export function BundleCompareView() {
  const fileRef = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [bundleIdColumn, setBundleIdColumn] = useState("bundle_id");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [rows, setRows] = useState<EnrichedRow[]>([]);
  const [diagnosisFilter, setDiagnosisFilter] = useState("all");
  const [dragging, setDragging] = useState(false);

  const headers = rows.length ? Object.keys(rows[0]) : [];
  const diagnosisCounts = rows.length ? countBy(rows, "moloco_diagnosis") : {};
  const filtered =
    diagnosisFilter === "all"
      ? rows
      : rows.filter((r) => r.moloco_diagnosis === diagnosisFilter);

  // Moloco-specific columns shown on the right side of the table
  const molocoColumns = [
    "moloco_diagnosis",
    "moloco_has_sdk",
    "moloco_ua_spend_90d",
    "st_app_name",
    "st_company",
    "st_hq_country",
    "st_monetization",
  ];
  // Original columns (everything else)
  const originalColumns = headers.filter((h) => !molocoColumns.includes(h));
  const displayColumns = [...originalColumns, ...molocoColumns.filter((c) => headers.includes(c))];

  async function handleSubmit() {
    if (!file) return;
    setLoading(true);
    setError(null);
    setRows([]);
    try {
      const formData = new FormData();
      formData.append("file", file);
      formData.append("bundle_id_column", bundleIdColumn);
      const res = await fetch("/api/incept/api/v1/supply-smb/enrich-bundles", {
        method: "POST",
        body: formData,
      });
      if (!res.ok) {
        const detail = await res.json().catch(() => ({}));
        throw new Error(detail?.detail ?? `Server error ${res.status}`);
      }
      const data: EnrichedRow[] = await res.json();
      setRows(data);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Unknown error");
    } finally {
      setLoading(false);
    }
  }

  function handleDrop(e: React.DragEvent) {
    e.preventDefault();
    setDragging(false);
    const f = e.dataTransfer.files[0];
    if (f?.name.endsWith(".csv")) setFile(f);
  }

  return (
    <div className="mx-auto max-w-7xl space-y-6 px-4 py-6">

      {/* Upload card */}
      <div className="rounded-xl border bg-card p-6 shadow-sm">
        <h2 className="mb-1 text-base font-semibold">上传外部数据 CSV</h2>
        <p className="mb-4 text-sm text-muted-foreground">
          支持广大大、SensorTower 等来源导出的 CSV。上传后自动比对 Moloco BQ 数据，追加诊断标签列。
        </p>

        {/* Drop zone */}
        <div
          className={`mb-4 flex cursor-pointer flex-col items-center justify-center rounded-lg border-2 border-dashed px-6 py-8 transition-colors ${
            dragging ? "border-primary bg-primary/5" : "border-muted-foreground/30 hover:border-primary/60"
          }`}
          onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
          onDragLeave={() => setDragging(false)}
          onDrop={handleDrop}
          onClick={() => fileRef.current?.click()}
        >
          <input
            ref={fileRef}
            type="file"
            accept=".csv"
            className="hidden"
            onChange={(e) => setFile(e.target.files?.[0] ?? null)}
          />
          {file ? (
            <p className="text-sm font-medium">{file.name}</p>
          ) : (
            <p className="text-sm text-muted-foreground">拖拽 CSV 到此处，或点击选择文件</p>
          )}
        </div>

        {/* Column selector */}
        <div className="mb-4 flex items-center gap-3">
          <label className="whitespace-nowrap text-sm font-medium">Bundle ID 列名</label>
          <input
            type="text"
            value={bundleIdColumn}
            onChange={(e) => setBundleIdColumn(e.target.value)}
            className="rounded-md border px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-primary/40"
            placeholder="bundle_id"
          />
          <span className="text-xs text-muted-foreground">（广大大默认为 bundle_id）</span>
        </div>

        <button
          onClick={handleSubmit}
          disabled={!file || loading}
          className="rounded-lg bg-primary px-5 py-2 text-sm font-medium text-primary-foreground transition hover:opacity-90 disabled:opacity-40"
        >
          {loading ? "比对中…" : "开始比对"}
        </button>

        {error && (
          <p className="mt-3 text-sm text-destructive">{error}</p>
        )}
      </div>

      {/* Results */}
      {rows.length > 0 && (
        <div className="space-y-4">

          {/* Summary chips */}
          <div className="flex flex-wrap gap-2">
            {Object.entries(diagnosisCounts)
              .sort((a, b) => b[1] - a[1])
              .map(([diag, count]) => (
                <span
                  key={diag}
                  className={`rounded-full px-3 py-1 text-xs font-medium ${diagnosisColor(diag)}`}
                >
                  {diag} · {count}
                </span>
              ))}
          </div>

          {/* Toolbar */}
          <div className="flex items-center justify-between gap-4">
            <div className="flex items-center gap-2">
              <label className="text-sm font-medium">筛选</label>
              <select
                value={diagnosisFilter}
                onChange={(e) => setDiagnosisFilter(e.target.value)}
                className="rounded-md border px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-primary/40"
              >
                {DIAGNOSIS_OPTIONS.map((o) => (
                  <option key={o.value} value={o.value}>{o.label}</option>
                ))}
              </select>
              <span className="text-sm text-muted-foreground">
                {filtered.length} / {rows.length} 条
              </span>
            </div>
            <button
              onClick={() => downloadCsv(rows, `bundle_compare_${Date.now()}.csv`)}
              className="rounded-lg border px-4 py-1.5 text-sm font-medium transition hover:bg-muted"
            >
              下载完整 CSV
            </button>
          </div>

          {/* Table */}
          <div className="overflow-x-auto rounded-xl border shadow-sm">
            <table className="w-full text-xs">
              <thead>
                <tr className="border-b bg-muted/50">
                  {displayColumns.map((col) => (
                    <th
                      key={col}
                      className={`whitespace-nowrap px-3 py-2 text-left font-semibold ${
                        molocoColumns.includes(col) ? "bg-blue-50 text-blue-700" : ""
                      }`}
                    >
                      {col}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {filtered.map((row, i) => (
                  <tr key={i} className="border-b last:border-0 hover:bg-muted/30">
                    {displayColumns.map((col) => (
                      <td key={col} className="max-w-[200px] truncate px-3 py-1.5">
                        {col === "moloco_diagnosis" ? (
                          <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${diagnosisColor(row[col] ?? "")}`}>
                            {row[col] ?? "—"}
                          </span>
                        ) : (
                          row[col] ?? "—"
                        )}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}
