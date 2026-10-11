// Small shared pieces. Tailwind only; swap the tokens, not these.
import type { Risk, Severity } from "@/lib/types";
import { num } from "@/lib/format";

export function Card({ className = "", children }: { className?: string; children: React.ReactNode }) {
  return <section className={`rounded-xl bg-surface p-4 ring-1 ring-line sm:p-5 ${className}`}>{children}</section>;
}

export function SectionTitle({ children, count }: { children: React.ReactNode; count?: number }) {
  return (
    <h2 className="mb-3 flex items-center gap-2 text-base font-semibold">
      {children}
      {count !== undefined && <span className="rounded-full bg-canvas px-2 text-xs font-medium text-muted">{count}</span>}
    </h2>
  );
}

const TONES = {
  danger: "bg-danger-soft text-danger",
  warning: "bg-warning-soft text-warning",
  success: "bg-success-soft text-success",
  neutral: "bg-canvas text-muted",
  info: "bg-accent/10 text-accent",
} as const;

export type Tone = keyof typeof TONES;

export function Pill({ tone = "neutral", children }: { tone?: Tone; children: React.ReactNode }) {
  return (
    <span className={`inline-flex items-center whitespace-nowrap rounded-full px-2 py-0.5 text-xs font-medium ${TONES[tone]}`}>{children}</span>
  );
}

export const SEVERITY_TONE: Record<Severity, Tone> = { critical: "danger", warning: "warning", info: "info" };
export const RISK_TONE: Record<Risk, Tone> = { in_danger: "danger", at_risk: "warning", ok: "success" };
export const RISK_LABEL: Record<Risk, string> = { in_danger: "En peligro", at_risk: "En riesgo", ok: "A tiempo" };

export type ButtonKind = "primary" | "secondary" | "danger";
// Old names still used under routes/ and in numbers.tsx (the rutas session owns
// them): both render as the secondary, so no fourth look sneaks back in.
type LegacyKind = "dark" | "ghost";
const normalize = (kind: ButtonKind | LegacyKind): ButtonKind => (kind === "dark" || kind === "ghost" ? "secondary" : kind);
type ButtonSize = "md" | "sm";
const BUTTONS: Record<ButtonKind, string> = {
  // Three looks and nothing else (Oscar, 11/10): the primary is the brand
  // color, one per view; the secondary is the neutral outline; danger is the
  // red outline for Cancelar orden and Descartar. Same height, radius, weight
  // and hover across the three; every button starts with its icon.
  primary: "bg-brand text-ink hover:bg-brand-hover",
  secondary: "bg-surface text-ink ring-1 ring-line hover:bg-canvas hover:ring-ink/30",
  danger: "bg-surface text-danger ring-1 ring-danger/40 hover:bg-danger-soft hover:ring-danger",
};
// Same height and radius everywhere: md for page actions, sm inside tables
// and cards (44 px on the phone either way).
const SIZES: Record<ButtonSize, string> = {
  md: "min-h-11 px-4 text-sm sm:min-h-10",
  sm: "min-h-11 px-3 text-xs sm:min-h-8",
};

// The button look, for <Link>s and custom buttons that must match <Button>.
export function buttonClass(kind: ButtonKind | LegacyKind = "secondary", size: ButtonSize = "md"): string {
  return `inline-flex items-center justify-center gap-1.5 rounded-md font-semibold transition-colors duration-150 disabled:cursor-default disabled:opacity-50 ${SIZES[size]} ${BUTTONS[normalize(kind)]}`;
}

// Rows and cards that open something: the same hover everywhere.
export const ROW_HOVER = "transition-colors duration-150 hover:bg-canvas";
export const CARD_HOVER = "transition-shadow duration-150 hover:shadow-md hover:ring-ink/25";

// Small ring that spins in the current text color (buttons, send icons).
export function Spinner({ className = "" }: { className?: string }) {
  return <span className={`inline-block size-4 shrink-0 animate-spin rounded-full border-2 border-current border-t-transparent ${className}`} aria-hidden />;
}

// `busy` disables the button and shows a spinner in front of the label, so
// every POST/PATCH gives feedback until the response arrives.
export function Button({
  kind = "secondary",
  className = "",
  busy = false,
  size = "md",
  disabled,
  children,
  ...props
}: React.ButtonHTMLAttributes<HTMLButtonElement> & { kind?: ButtonKind | LegacyKind; size?: ButtonSize; busy?: boolean }) {
  return (
    <button
      type="button"
      {...props}
      disabled={disabled || busy}
      aria-busy={busy || undefined}
      className={`${buttonClass(kind, size)} ${className}`}
    >
      {busy && <Spinner />}
      {children}
    </button>
  );
}

// Score bar for the matching criteria (0 to 1; the API may send it as a string).
export function ScoreBar({ label, value }: { label: string; value: string | number | null | undefined }) {
  const pct = Math.round(Math.max(0, Math.min(1, num(value) ?? 0)) * 100);
  return (
    <div className="grid grid-cols-[6.5rem_1fr_2.5rem] items-center gap-2 text-xs">
      <span className="text-muted">{label}</span>
      <span className="h-2 overflow-hidden rounded-full bg-canvas">
        <span className="block h-full rounded-full bg-accent" style={{ width: `${pct}%` }} />
      </span>
      <span className="text-right tabular-nums">{pct}</span>
    </div>
  );
}

export const CRITERIA_LABELS: Record<string, string> = {
  on_time: "Cumplimiento",
  price: "Precio",
  load: "Carga libre",
  quality: "Calidad",
  lead_time: "Plazo",
  capacity: "Capacidad",
};
