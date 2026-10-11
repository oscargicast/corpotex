// Small shared pieces. Tailwind only; swap the tokens, not these.
import type { Risk, Severity } from "@/lib/types";

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

type ButtonKind = "primary" | "dark" | "ghost" | "danger";
const BUTTONS: Record<ButtonKind, string> = {
  // Orange is reserved for the main action, with dark text on top.
  primary: "bg-brand text-ink hover:bg-brand-hover",
  dark: "bg-ink text-white hover:bg-ink/90",
  ghost: "text-ink ring-1 ring-line hover:bg-canvas",
  danger: "bg-danger text-white hover:bg-danger/90",
};

export function Button({
  kind = "ghost",
  className = "",
  ...props
}: React.ButtonHTMLAttributes<HTMLButtonElement> & { kind?: ButtonKind }) {
  return (
    <button
      type="button"
      {...props}
      className={`inline-flex items-center justify-center gap-1.5 rounded-md px-3 py-2 text-sm font-semibold disabled:opacity-50 ${BUTTONS[kind]} ${className}`}
    />
  );
}

// Score bar for the matching criteria (0 to 1).
export function ScoreBar({ label, value }: { label: string; value: number }) {
  const pct = Math.round(Math.max(0, Math.min(1, value)) * 100);
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
