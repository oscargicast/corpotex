"use client";

import useSWR from "swr";
import { fetcher } from "./api";
import type { Badges } from "./types";

// One light poll for every view: menu counters, the toast and the Claude banner.
export function useBadges(): Badges | undefined {
  const { data } = useSWR<Badges>("/api/me/badges/", fetcher, { refreshInterval: 5000 });
  return data;
}
