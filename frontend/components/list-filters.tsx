"use client";

import { Search, X } from "lucide-react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useCallback } from "react";

// Filters of the lists live in the URL (?view=…&q=…) so a view can be shared
// (ADR 0025 A.7); the pages filter the loaded list in the browser.

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

export function SearchBox({ value, onChange, placeholder }: { value: string; onChange: (value: string) => void; placeholder: string }) {
  return (
    <label className="relative block w-full sm:w-72">
      <Search size={16} className="pointer-events-none absolute left-2.5 top-1/2 -translate-y-1/2 text-muted" aria-hidden />
      <input
        type="search"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        aria-label={placeholder}
        autoComplete="off"
        spellCheck={false}
        className="min-h-11 w-full rounded-md bg-surface pl-8 pr-8 text-base ring-1 ring-line placeholder:text-muted sm:min-h-9 sm:text-sm"
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
