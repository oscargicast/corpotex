import { CalendarCheck, CalendarClock, CheckCircle2, Flame, OctagonAlert, TriangleAlert, type LucideIcon } from "lucide-react";
import Link from "next/link";
import type { CriticalStep, PurchaseOrderListItem } from "@/lib/types";

// Ruta crítica (ADR 0029 §3): the three dates that matter, a timeline with a
// date axis (Hoy, Estimada, Entrega) and the steps with their dates. Under
// 640 px only the list shows.

const DAY = 86_400_000;
const STATUS: Record<CriticalStep["status"], { label: string; bar: string; text: string }> = {
  done: { label: "Hecho", bar: "bg-success", text: "text-success" },
  in_progress: { label: "En curso", bar: "bg-accent", text: "text-accent" },
  pending: { label: "Pendiente", bar: "bg-muted/30", text: "text-muted" },
  late: { label: "Atrasado", bar: "bg-danger", text: "text-danger" },
};

const time = (day: string) => new Date(`${day}T12:00:00-05:00`).getTime();
const limaToday = () => new Date().toLocaleDateString("en-CA", { timeZone: "America/Lima" });
const dayMonth = new Intl.DateTimeFormat("es-PE", { day: "numeric", month: "short", timeZone: "America/Lima" });
const short = (day: string) => dayMonth.format(new Date(time(day))).replace(".", "");
const dayOnly = (day: string) => String(new Date(time(day)).getUTCDate());

// "del 12 al 14 oct", "del 30 sep al 2 oct", "el 12 oct".
function range(start: string, end: string): string {
  if (start === end) return `el ${short(start)}`;
  const sameMonth = start.slice(0, 7) === end.slice(0, 7);
  return `del ${sameMonth ? dayOnly(start) : short(start)} al ${short(end)}`;
}

// Some steps come with the end before the start (a deadline earlier than the
// work before it): the timeline never draws them backwards.
function span(step: CriticalStep): { start: string; end: string; days: number } {
  const end = time(step.end) < time(step.start) ? step.start : step.end;
  return { start: step.start, end, days: Math.round((time(end) - time(step.start)) / DAY) + 1 };
}

type Tone = "ok" | "tight" | "late" | "none";
const TONE: Record<Tone, { text: string; bg: string; icon: LucideIcon; label: string }> = {
  ok: { text: "text-success", bg: "bg-success-soft", icon: CheckCircle2, label: "a tiempo" },
  tight: { text: "text-warning", bg: "bg-warning-soft", icon: TriangleAlert, label: "justa" },
  late: { text: "text-danger", bg: "bg-danger-soft", icon: OctagonAlert, label: "atrasada" },
  none: { text: "text-ink", bg: "bg-surface", icon: CalendarClock, label: "" },
};

// Holgura: green from 2 days, amber 0-1, red when negative.
function slackTone(slack: number | null): Tone {
  if (slack === null) return "none";
  return slack >= 2 ? "ok" : slack >= 0 ? "tight" : "late";
}

export function CriticalPath({
  steps,
  promisedOn,
  estimatedOn,
  slackDays,
  purchaseOrders = [],
}: {
  steps: CriticalStep[];
  promisedOn: string;
  estimatedOn: string | null;
  slackDays: number | null;
  purchaseOrders?: PurchaseOrderListItem[];
}) {
  const tone = slackTone(slackDays);
  const t = TONE[tone];

  return (
    <div className="space-y-5">
      <dl className="grid grid-cols-3 gap-2 sm:gap-3">
        <Fact icon={CalendarCheck} label="Fecha de entrega" value={short(promisedOn)} tone="none" />
        <Fact icon={CalendarClock} label="Estimada" value={estimatedOn ? short(estimatedOn) : "—"} tone={tone} />
        <Fact
          icon={t.icon}
          label="Holgura"
          value={slackDays === null ? "—" : `${slackDays} ${Math.abs(slackDays) === 1 ? "día" : "días"}`}
          note={t.label}
          tone={tone}
        />
      </dl>

      {steps.length ? (
        <>
          <Timeline steps={steps} promisedOn={promisedOn} estimatedOn={estimatedOn} tone={tone} />
          <StepList steps={steps} purchaseOrders={purchaseOrders} />
        </>
      ) : (
        <p className="text-sm text-muted">Sin ruta crítica todavía.</p>
      )}
    </div>
  );
}

function Fact({ icon: Icon, label, value, note, tone }: { icon: LucideIcon; label: string; value: string; note?: string; tone: Tone }) {
  const t = TONE[tone];
  return (
    <div className={`rounded-xl p-3 ring-1 ring-line ${tone === "none" ? "bg-surface" : t.bg}`}>
      <dt className="flex items-center gap-1.5 text-xs text-muted">
        <Icon size={14} className={tone === "none" ? "text-muted" : t.text} aria-hidden />
        {label}
      </dt>
      <dd className={`mt-0.5 font-semibold tabular-nums ${t.text}`}>
        {value}
        {note && <span className="ml-1 text-xs font-medium">· {note}</span>}
      </dd>
    </div>
  );
}

function Timeline({ steps, promisedOn, estimatedOn, tone }: { steps: CriticalStep[]; promisedOn: string; estimatedOn: string | null; tone: Tone }) {
  const today = limaToday();
  const spans = steps.map(span);
  const start = Math.min(time(today), ...spans.map((s) => time(s.start)));
  const end = Math.max(time(promisedOn), estimatedOn ? time(estimatedOn) : 0, ...spans.map((s) => time(s.end))) + DAY;
  const pct = (at: number) => ((at - start) / (end - start)) * 100;
  const base = [
    { key: "ent", label: "Entrega", day: promisedOn, line: "border-ink", text: "text-ink" },
    ...(estimatedOn ? [{ key: "est", label: "Estimada", day: estimatedOn, line: tone === "late" ? "border-danger" : tone === "tight" ? "border-warning" : "border-success", text: TONE[tone].text }] : []),
    { key: "hoy", label: "Hoy", day: today, line: "border-accent", text: "text-accent" },
  ];
  // One label row per marker that would touch another (29 and 30 oct side by side).
  const placed: { p: number; row: number }[] = [];
  const markers = base.map((m) => {
    const p = pct(time(m.day));
    let row = 0;
    while (placed.some((o) => o.row === row && Math.abs(o.p - p) < 14)) row += 1;
    placed.push({ p, row });
    return { ...m, row };
  });
  // Labels near an edge align to it instead of overflowing.
  const place = (p: number) => (p < 8 ? "translate-x-0" : p > 92 ? "-translate-x-full" : "-translate-x-1/2");

  return (
    <div className="hidden sm:block" aria-hidden>
      <div className="grid grid-cols-[13rem_minmax(0,1fr)] gap-x-3">
        {/* Axis */}
        <span />
        <div className="relative" style={{ height: (Math.max(...markers.map((m) => m.row)) + 1) * 15 + 30 }}>
          {markers.map((m) => {
            const p = pct(time(m.day));
            return (
              <span key={m.key} className={`absolute whitespace-nowrap text-[11px] font-semibold ${m.text} ${place(p)}`} style={{ left: `${p}%`, top: m.row * 15 }}>
                {m.label} {short(m.day)}
              </span>
            );
          })}
          <span className="absolute inset-x-0 bottom-4 border-t border-line" />
          <span className="absolute bottom-0 left-0 text-[11px] tabular-nums text-muted">{short(new Date(start).toISOString().slice(0, 10))}</span>
          <span className="absolute bottom-0 right-0 text-[11px] tabular-nums text-muted">{short(new Date(end - DAY).toISOString().slice(0, 10))}</span>
        </div>

        {/* Bars, with the markers' lines across them */}
        <div className="col-span-2 grid grid-cols-[13rem_minmax(0,1fr)] gap-x-3 gap-y-2">
          {steps.map((step, i) => {
            const s = spans[i];
            const left = pct(time(s.start));
            const width = Math.max(pct(time(s.end) + DAY) - left, 1.5);
            return (
              <div key={step.id} className="contents">
                <span className="flex min-w-0 items-center gap-1 text-sm" title={step.name}>
                  {step.critical && <Flame size={13} className="shrink-0 text-danger" aria-hidden />}
                  <span className="truncate">{step.name}</span>
                </span>
                <span className="relative h-6 rounded bg-canvas">
                  {markers.map((m) => (
                    <span key={m.key} className={`absolute inset-y-[-4px] border-l-2 border-dashed ${m.line} opacity-70`} style={{ left: `${pct(time(m.day))}%` }} />
                  ))}
                  <span
                    className={`absolute inset-y-0 rounded ${STATUS[step.status].bar} ${step.critical ? "ring-2 ring-ink/70" : ""}`}
                    style={{ left: `${left}%`, width: `${width}%` }}
                    title={`${step.name}: ${range(s.start, s.end)} · ${STATUS[step.status].label}`}
                  />
                </span>
              </div>
            );
          })}
        </div>
      </div>
      <ul className="mt-3 flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted">
        {Object.values(STATUS).map((st) => (
          <li key={st.label} className="flex items-center gap-1">
            <span className={`inline-block size-2.5 rounded-sm ${st.bar}`} />
            {st.label}
          </li>
        ))}
        <li className="flex items-center gap-1">
          <Flame size={12} className="text-danger" /> Crítico
        </li>
      </ul>
    </div>
  );
}

function StepList({ steps, purchaseOrders }: { steps: CriticalStep[]; purchaseOrders: PurchaseOrderListItem[] }) {
  const byId = new Map(purchaseOrders.map((po) => [po.id, po]));
  return (
    <ol className="divide-y divide-line border-t border-line">
      {steps.map((step) => {
        const s = span(step);
        const st = STATUS[step.status];
        const po = step.purchase_order_id ? byId.get(step.purchase_order_id) : undefined;
        const committed = po?.committed_on ?? null;
        const internal = po?.internal_due_on ?? null;
        // Past the internal limit: the committed date, or the step's own end without one.
        const pastLimit = !!internal && time(committed ?? s.end) > time(internal);
        return (
          <li key={step.id} className="flex flex-wrap items-start justify-between gap-x-4 gap-y-1 py-2.5">
            <div className="min-w-0">
              <p className="flex flex-wrap items-center gap-x-2 gap-y-0.5 font-medium">
                {step.purchase_order_id ? (
                  <Link href={`/purchase-orders/${step.purchase_order_id}`} className="text-accent hover:underline">
                    {step.name}
                  </Link>
                ) : (
                  step.name
                )}
                {step.critical && (
                  <span className="inline-flex items-center gap-0.5 text-xs font-semibold text-danger">
                    <Flame size={12} aria-hidden /> crítico
                  </span>
                )}
              </p>
              <p className="text-sm tabular-nums text-muted">
                {range(s.start, s.end)} · {s.days} {s.days === 1 ? "día" : "días"}
              </p>
              {!!step.late_by && step.late_by > 0 && (
                <p className="flex items-center gap-1 text-xs font-semibold text-danger">
                  <OctagonAlert size={12} aria-hidden /> llega {step.late_by} {step.late_by === 1 ? "día" : "días"} tarde
                </p>
              )}
              {(committed || internal) && (
                <p className={`text-xs tabular-nums ${pastLimit ? "text-danger" : "text-muted"}`}>
                  {[committed && `comprometido ${short(committed)}`, internal && `límite interno ${short(internal)}`].filter(Boolean).join(" · ")}
                  {pastLimit && " · pasa el límite"}
                </p>
              )}
            </div>
            <span className={`inline-flex items-center gap-1.5 text-xs font-medium ${st.text}`}>
              <span className={`inline-block size-2 rounded-full ${st.bar}`} aria-hidden />
              {st.label}
            </span>
          </li>
        );
      })}
    </ol>
  );
}
