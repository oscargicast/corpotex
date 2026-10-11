"use client";

import { Search, X } from "lucide-react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useCallback } from "react";

// Filters of the Órdenes and Pedidos lists live in the URL (?status=a,b&q=…)
// so a view can be shared (ADR 0025 A.7). Until backend B6.5 lands, the pages
// filter the loaded list in the browser with the same parameters.

export function useListParams() {
  const params = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();

  const set = useCallback(
    (patch: Record<string, string | string[] | null | undefined>) => {
      const next = new URLSearchParams(params.toString());
      for (const [key, value] of Object.entries(patch)) {
        const joined = Array.isArray(value) ? value.join(",") : value;
        if (joined) next.set(key, joined);
        else next.delete(key);
      }
      const query = next.toString();
      router.replace(query ? `${pathname}?${query}` : pathname, { scroll: false });
    },
    [params, router, pathname],
  );

  return {
    get: (key: string) => params.get(key) ?? "",
    list: (key: string) => (params.get(key) ?? "").split(",").filter(Boolean),
    set,
  };
}

// Canonical order of the chips; statuses the data brings and this list lacks go last.
export const ORDER_STATUSES = ["registered", "broken_down", "confirmed", "sourcing", "in_production", "ready", "delivered", "cancelled"];
export const PURCHASE_ORDER_STATUSES = [
  "suggested",
  "approved",
  "negotiating",
  "confirmed",
  "in_progress",
  "delivered",
  "cancelled",
  "declined_by_supplier",
  "cancelled_by_supplier",
  "rejected_by_supplier",
];

export function statusOptions(items: { status: string; status_display: string }[], order: string[]): { value: string; label: string; count: number }[] {
  const seen = new Map<string, { label: string; count: number }>();
  for (const item of items) {
    const entry = seen.get(item.status) ?? { label: item.status_display, count: 0 };
    entry.count += 1;
    seen.set(item.status, entry);
  }
  const rank = (status: string) => {
    const i = order.indexOf(status);
    return i < 0 ? order.length : i;
  };
  return [...seen.entries()].sort((a, b) => rank(a[0]) - rank(b[0])).map(([value, { label, count }]) => ({ value, label, count }));
}

// Multi-select chips. An empty selection means every status.
export function StatusChips({
  options,
  selected,
  onChange,
  allLabel = "Todos",
}: {
  options: { value: string; label: string; count?: number }[];
  selected: string[];
  onChange: (next: string[]) => void;
  allLabel?: string;
}) {
  const chip = (active: boolean) => `rounded-full px-3 py-1 text-sm ring-1 ${active ? "bg-ink text-white ring-ink" : "bg-surface ring-line hover:bg-canvas"}`;
  return (
    <div className="flex flex-wrap items-center gap-2" role="group" aria-label="Estado">
      <button type="button" aria-pressed={!selected.length} onClick={() => onChange([])} className={chip(!selected.length)}>
        {allLabel}
      </button>
      {options.map((option) => {
        const active = selected.includes(option.value);
        return (
          <button
            key={option.value}
            type="button"
            aria-pressed={active}
            onClick={() => onChange(active ? selected.filter((s) => s !== option.value) : [...selected, option.value])}
            className={chip(active)}
          >
            {option.label}
            {option.count !== undefined && <span className={`ml-1 text-xs ${active ? "text-white/70" : "text-muted"}`}>{option.count}</span>}
          </button>
        );
      })}
    </div>
  );
}

export function SearchBox({ value, onChange, placeholder }: { value: string; onChange: (value: string) => void; placeholder: string }) {
  return (
    <label className="relative block min-w-56 flex-1 sm:max-w-xs">
      <Search size={16} className="pointer-events-none absolute left-2.5 top-1/2 -translate-y-1/2 text-muted" aria-hidden />
      <input
        type="search"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        aria-label={placeholder}
        autoComplete="off"
        spellCheck={false}
        className="w-full rounded-md bg-surface py-1.5 pl-8 pr-8 text-sm ring-1 ring-line placeholder:text-muted"
      />
      {value && (
        <button type="button" onClick={() => onChange("")} className="absolute right-1.5 top-1/2 -translate-y-1/2 rounded p-0.5 text-muted hover:bg-canvas" aria-label="Limpiar búsqueda">
          <X size={14} />
        </button>
      )}
    </label>
  );
}

// Code search: prefix or any part, case-insensitive, over one or more codes.
export function matchesCode(query: string, ...codes: (string | undefined | null)[]): boolean {
  const q = query.trim().toLowerCase();
  if (!q) return true;
  return codes.some((code) => code?.toLowerCase().includes(q));
}
