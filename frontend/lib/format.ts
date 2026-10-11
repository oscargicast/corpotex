import type { Currency } from "./types";

const TZ = "America/Lima";

const day = new Intl.DateTimeFormat("es-PE", { timeZone: TZ, day: "numeric", month: "short" });
const dayTime = new Intl.DateTimeFormat("es-PE", {
  timeZone: TZ,
  day: "numeric",
  month: "short",
  hour: "2-digit",
  minute: "2-digit",
});

// Business dates come as "2026-10-20" (no time): read them as Lima noon so the
// day never shifts with the browser's time zone.
function parse(value: string): Date {
  return new Date(/^\d{4}-\d{2}-\d{2}$/.test(value) ? `${value}T12:00:00-05:00` : value);
}

export function formatDay(value: string | null | undefined): string {
  return value ? day.format(parse(value)) : "—";
}

export function formatDayTime(value: string | null | undefined): string {
  return value ? dayTime.format(parse(value)) : "—";
}

function moneyFormat(currency: Currency, digits: number) {
  return new Intl.NumberFormat("es-PE", {
    style: "currency",
    currency,
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  });
}

const money = {
  PEN: [moneyFormat("PEN", 0), moneyFormat("PEN", 2)],
  USD: [moneyFormat("USD", 0), moneyFormat("USD", 2)],
};

// Decimals arrive as strings from DRF. Whole amounts drop the cents, unit
// prices like 8.50 keep them. Never add PEN and USD together.
export function formatMoney(value: string | number | null | undefined, currency: Currency = "PEN"): string {
  if (value === null || value === undefined || value === "") return "—";
  const amount = Number(value);
  return money[currency][Number.isInteger(amount) ? 0 : 1].format(amount);
}

// Decimals arrive from the API as strings (DRF), and scores can be null until
// the first delivery: never call .toFixed or multiply an API field directly.
export function num(value: string | number | null | undefined): number | null {
  if (value === null || value === undefined || value === "") return null;
  const n = Number(value);
  return Number.isFinite(n) ? n : null;
}

// "4.5", or "—" when there is no value yet.
export function formatNum(value: string | number | null | undefined, digits = 1): string {
  const n = num(value);
  return n === null ? "—" : n.toFixed(digits);
}

// A 0 to 1 score as a whole number ("82"), or "—".
export function formatScore(value: string | number | null | undefined): string {
  const n = num(value);
  return n === null ? "—" : String(Math.round(n * 100));
}

export function daysBetween(from: string, to: string): number {
  return Math.round((parse(to).getTime() - parse(from).getTime()) / 86_400_000);
}
