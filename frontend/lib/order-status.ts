// How an order's status reads in the dashboard. The API still sends
// "Desglosada" for broken_down; ADR 0029 §1 calls it "Con ficha técnica".
const LABELS: Record<string, string> = { broken_down: "Con ficha técnica" };

export function orderStatusLabel(status: string, display?: string | null): string {
  return LABELS[status] ?? display ?? status;
}
