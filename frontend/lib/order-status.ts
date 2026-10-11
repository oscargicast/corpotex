import type { Role } from "./types";

// How an order's status reads in the dashboard. The API still sends
// "Desglosada" for broken_down; ADR 0029 §1 calls it "Con ficha técnica".
const LABELS: Record<string, string> = { broken_down: "Con ficha técnica" };
// Comercial reads the two statuses before confirmation as one wait (Oscar, 11/10).
const SALES_LABELS: Record<string, string> = { registered: "Esperando a Producción", broken_down: "Esperando a Producción" };

export function orderStatusLabel(status: string, display?: string | null, role?: Role): string {
  if (role === "sales" && SALES_LABELS[status]) return SALES_LABELS[status];
  return LABELS[status] ?? display ?? status;
}
