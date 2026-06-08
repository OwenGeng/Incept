"use client";

/**
 * ProspectFilterBar — unified filter bar used by all three Supply SMB list pages.
 *
 * Supports two interaction modes:
 *   mode="client"  — real-time router.push with debounced search (No-SDK/No-UA)
 *   mode="form"    — native <form method="get"> with Apply button (SDK/UA datasets)
 *
 * Both modes render identical card/grid/input styling.
 */

import { useCallback, useRef, useState } from "react";
import Link from "next/link";
import type { Route } from "next";
import { usePathname, useRouter } from "next/navigation";
import { Card } from "@/components/ui/card";
import { cn } from "@/lib/utils";

// ── Shared CSS constants ───────────────────────────────────────────────────────

export const filterInputCls = [
  "h-10 w-full rounded-xl border border-border bg-card px-3",
  "text-sm text-foreground outline-none transition",
  "focus:border-accent focus:ring-2 focus:ring-soft-accent",
].join(" ");

export const filterLabelCls =
  "text-[11px] font-semibold uppercase tracking-[0.16em] text-muted-foreground";

// ── Filter field descriptor ────────────────────────────────────────────────────

export type FilterSelectOption = { label: string; value: string };

export type FilterField =
  | {
      type: "search";
      key: string;
      label: string;
      placeholder?: string;
    }
  | {
      type: "select";
      key: string;
      label: string;
      options: FilterSelectOption[];
    };

// ── Shared query shape used by client mode ─────────────────────────────────────

type AnyQuery = Record<string, string | undefined>;

/**
 * TopListsQuery — the search/filter/sort/page shape used by No-SDK+No-UA top lists.
 * Exported here so that both the page and the view component share a single type.
 */
export type TopListsQuery = {
  search?: string;
  priority?: string;
  routing?: string;
  supplyVisibility?: string;
  companySortBy?: string;
  companySortDir?: string;
  appSortBy?: string;
  appSortDir?: string;
  companyPage?: string;
  appPage?: string;
};

function buildUrl(pathname: string, query: AnyQuery): string {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(query)) {
    if (value) params.set(key, value);
  }
  const s = params.toString();
  return s ? `${pathname}?${s}` : pathname;
}

// ── Client-side filter bar (real-time, debounced search) ──────────────────────

function ClientFilterBar({
  fields,
  query,
  resetHref,
  preserveKeys,
}: {
  fields: FilterField[];
  query: AnyQuery;
  resetHref: string;
  preserveKeys?: string[];
}) {
  const router = useRouter();
  const pathname = usePathname();
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Each field tracks its own local value for instant input feedback
  const [localValues, setLocalValues] = useState<Record<string, string>>(() =>
    Object.fromEntries(fields.map((f) => [f.key, query[f.key] ?? ""]))
  );

  const navigate = useCallback(
    (updates: AnyQuery) => {
      const preserved: AnyQuery = {};
      for (const key of preserveKeys ?? []) {
        preserved[key] = query[key];
      }
      router.push(buildUrl(pathname, { ...query, ...preserved, ...updates }));
    },
    [query, router, pathname, preserveKeys],
  );

  function handleSearch(key: string, value: string) {
    setLocalValues((v) => ({ ...v, [key]: value }));
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => {
      navigate({ [key]: value, companyPage: "1", appPage: "1" });
    }, 350);
  }

  function handleSelect(key: string, value: string) {
    setLocalValues((v) => ({ ...v, [key]: value }));
    navigate({ [key]: value, companyPage: "1", appPage: "1" });
  }

  return (
    <div className={cn("grid gap-4", `xl:grid-cols-[1.4fr_repeat(${fields.length - 1},minmax(0,1fr))_auto]`)}>
      {fields.map((field) =>
        field.type === "search" ? (
          <label key={field.key} className="flex flex-col gap-1.5">
            <span className={filterLabelCls}>{field.label}</span>
            <input
              value={localValues[field.key] ?? ""}
              onChange={(e) => handleSearch(field.key, e.target.value)}
              placeholder={field.placeholder ?? "search…"}
              className={filterInputCls}
            />
          </label>
        ) : (
          <label key={field.key} className="flex flex-col gap-1.5">
            <span className={filterLabelCls}>{field.label}</span>
            <select
              value={localValues[field.key] ?? "all"}
              onChange={(e) => handleSelect(field.key, e.target.value)}
              className={filterInputCls}
            >
              {field.options.map((opt) => (
                <option key={opt.value} value={opt.value}>
                  {opt.label}
                </option>
              ))}
            </select>
          </label>
        ),
      )}
      {/* Reset */}
      <div className="flex items-end">
        <Link
          href={resetHref as Route}
          onClick={() => setLocalValues(Object.fromEntries(fields.map((f) => [f.key, ""])))}
          className="inline-flex h-10 items-center rounded-xl border border-border bg-muted px-4 text-sm font-semibold text-foreground transition hover:bg-border"
        >
          Reset
        </Link>
      </div>
    </div>
  );
}

// ── Form-based filter bar (submit on Apply) ───────────────────────────────────

function FormFilterBar({
  fields,
  query,
  resetHref,
  hiddenFields,
}: {
  fields: FilterField[];
  query: AnyQuery;
  resetHref: string;
  hiddenFields?: Record<string, string>;
}) {
  const cols = fields.length + 1; // +1 for the button column
  return (
    <form
      method="get"
      className={cn("grid gap-4", `xl:grid-cols-[1.4fr_repeat(${fields.length - 1},minmax(0,1fr))_auto]`)}
    >
      {fields.map((field) =>
        field.type === "search" ? (
          <label key={field.key} className="flex flex-col gap-1.5">
            <span className={filterLabelCls}>{field.label}</span>
            <input
              name={field.key}
              defaultValue={query[field.key] ?? ""}
              placeholder={field.placeholder ?? "search…"}
              className={filterInputCls}
            />
          </label>
        ) : (
          <label key={field.key} className="flex flex-col gap-1.5">
            <span className={filterLabelCls}>{field.label}</span>
            <select
              name={field.key}
              defaultValue={query[field.key] ?? "all"}
              className={filterInputCls}
            >
              {field.options.map((opt) => (
                <option key={opt.value} value={opt.value}>
                  {opt.label}
                </option>
              ))}
            </select>
          </label>
        ),
      )}

      {/* Buttons */}
      <div className="flex items-end gap-2">
        <button
          type="submit"
          className="inline-flex h-10 items-center justify-center rounded-xl bg-accent px-4 text-sm font-semibold text-white shadow-[0_2px_8px_rgba(53,111,236,0.22)] transition hover:bg-accent/90"
        >
          Apply
        </button>
        <Link
          href={resetHref as Route}
          className="inline-flex h-10 items-center justify-center rounded-xl border border-border bg-muted px-4 text-sm font-semibold text-foreground transition hover:bg-border"
        >
          Reset
        </Link>
      </div>

      {/* Preserve sort + page state across filter changes */}
      {hiddenFields &&
        Object.entries(hiddenFields).map(([name, value]) => (
          <input key={name} type="hidden" name={name} value={value} />
        ))}
    </form>
  );
}

// ── Exported wrapper ───────────────────────────────────────────────────────────

export function ProspectFilterBar({
  mode,
  fields,
  query,
  resetHref,
  preserveKeys,
  hiddenFields,
}: {
  mode: "client" | "form";
  fields: FilterField[];
  query: AnyQuery;
  resetHref: string;
  /** Client mode: query keys to preserve across navigation (e.g. sort keys) */
  preserveKeys?: string[];
  /** Form mode: extra <input type="hidden"> entries (e.g. sort state) */
  hiddenFields?: Record<string, string>;
}) {
  return (
    <Card className="border-[#DCE8FA] bg-[#F8FBFF] p-5 shadow-sm">
      {mode === "client" ? (
        <ClientFilterBar
          fields={fields}
          query={query}
          resetHref={resetHref}
          preserveKeys={preserveKeys}
        />
      ) : (
        <FormFilterBar
          fields={fields}
          query={query}
          resetHref={resetHref}
          hiddenFields={hiddenFields}
        />
      )}
    </Card>
  );
}
