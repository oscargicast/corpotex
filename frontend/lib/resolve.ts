"use client";

import useSWR from "swr";
import { fetcher } from "./api";

// Detail URLs take an id (/orders/12) or a business code (/orders/CP-2026-0001),
// which the assistant's chat links use. A code resolves with ?code=.
export function useResolvedId(resource: "orders" | "purchase-orders", param: string) {
  const numeric = /^\d+$/.test(param);
  const { data, error } = useSWR<{ id: number }[]>(
    numeric ? null : `/api/${resource}/?code=${encodeURIComponent(param)}`,
    fetcher,
  );
  if (numeric) return { id: Number(param), notFound: false };
  if (data) return { id: data[0]?.id ?? null, notFound: !data.length };
  return { id: null, notFound: !!error };
}
