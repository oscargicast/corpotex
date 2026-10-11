// Dates in Lima, whatever the browser's time zone.
const TZ = "America/Lima";
const isoDay = new Intl.DateTimeFormat("en-CA", { timeZone: TZ, year: "numeric", month: "2-digit", day: "2-digit" });
const longDay = new Intl.DateTimeFormat("es-PE", { timeZone: TZ, weekday: "short", day: "numeric", month: "short" });
const clock = new Intl.DateTimeFormat("es-PE", { timeZone: TZ, hour: "2-digit", minute: "2-digit", hour12: false });

export function todayLima(): string {
  return isoDay.format(new Date());
}

export function addDays(day: string, n: number): string {
  const d = new Date(`${day}T12:00:00-05:00`);
  d.setUTCDate(d.getUTCDate() + n);
  return isoDay.format(d);
}

export function dayLabel(day: string): string {
  return longDay.format(new Date(`${day}T12:00:00-05:00`));
}

export function hhmm(value: string | null | undefined): string {
  return value ? clock.format(new Date(value)) : "—";
}

export function dayOf(value: string): string {
  return isoDay.format(new Date(value));
}

// Live under 30 s, no signal after 2 min (ADR 0026 §6).
export type Signal = "live" | "recent" | "none";
export function signalOf(at: string | null | undefined, now: number): Signal {
  if (!at) return "none";
  const age = now - new Date(at).getTime();
  return age < 30_000 ? "live" : age < 120_000 ? "recent" : "none";
}

export function deliveries<T extends { kind: string }>(stops: T[]): T[] {
  return stops.filter((s) => s.kind === "delivery");
}
