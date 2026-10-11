import type { AssistantContext } from "./types";

// The view the user is on, sent with every message so "¿y esta orden?" works.
const VIEWS: [RegExp, string, string?][] = [
  [/^\/$/, "monitor"],
  [/^\/orders\/([^/]+)$/, "orders", "order"],
  [/^\/orders$/, "orders"],
  [/^\/purchase-orders\/([^/]+)$/, "purchase_orders", "purchase_order"],
  [/^\/purchase-orders$/, "purchase_orders"],
  [/^\/suppliers\/([^/]+)$/, "suppliers", "supplier"],
  [/^\/suppliers$/, "suppliers"],
  [/^\/inventory/, "inventory"],
  [/^\/routes/, "routes"],
  [/^\/simulator/, "simulator"],
  [/^\/style/, "style"],
  [/^\/onboarding/, "onboarding"],
];

export function contextFor(path: string): AssistantContext {
  for (const [pattern, view, detailView] of VIEWS) {
    const match = path.match(pattern);
    if (!match) continue;
    const id = match[1] && /^\d+$/.test(match[1]) ? Number(match[1]) : undefined;
    return { path, view: detailView && match[1] ? detailView : view, ...(id !== undefined && { id }) };
  }
  return { path, view: "monitor" };
}
