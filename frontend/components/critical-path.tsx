"use client";

import { CalendarClock, CheckCircle2, ChevronRight, Flame, OctagonAlert, TriangleAlert, X, type LucideIcon } from "lucide-react";
import Link from "next/link";
import { useEffect, useId, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { SkeletonLines } from "./skeleton";
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

const EXPANDED_KEY = "corpotex.criticalPath.expanded";

// Compressed by default (one strip of blocks, Oscar 11/10 06:35); "Ver detalle"
// or the header expands it to the timeline and the dated list, remembered per
// browser.
export function CriticalPath({
  steps,
  promisedOn,
  estimatedOn,
  slackDays,
  purchaseOrders = [],
  actions,
  loading = false,
}: {
  steps: CriticalStep[];
  promisedOn: string;
  estimatedOn: string | null;
  slackDays: number | null;
  purchaseOrders?: PurchaseOrderListItem[];
  actions?: React.ReactNode;
  loading?: boolean;
}) {
  const tone = slackTone(slackDays);
  const [expanded, setExpanded] = useState(false);
  const bodyId = useId();
  useEffect(() => {
    try {
      setExpanded(localStorage.getItem(EXPANDED_KEY) === "1");
    } catch {
      // Storage blocked: compressed it is.
    }
  }, []);
  function toggle() {
    const next = !expanded;
    setExpanded(next);
    try {
      localStorage.setItem(EXPANDED_KEY, next ? "1" : "0");
    } catch {
      // Not remembered, still toggled.
    }
  }
  const slackText =
    slackDays === null ? null : slackDays >= 0 ? `${slackDays} ${slackDays === 1 ? "día" : "días"} de holgura` : `${-slackDays} ${slackDays === -1 ? "día" : "días"} de atraso`;

  return (
    <div>
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
        <button
          type="button"
          onClick={toggle}
          aria-expanded={expanded}
          aria-controls={bodyId}
          className="-ml-1 flex min-h-11 items-center gap-1.5 rounded-md px-1 text-left hover:bg-canvas"
        >
          <ChevronRight size={16} className={`text-muted transition-transform duration-200 motion-reduce:transition-none ${expanded ? "rotate-90" : ""}`} aria-hidden />
          <h2 className="text-base font-semibold">Ruta crítica</h2>
        </button>
        <p className="text-sm tabular-nums text-muted">
          Entrega {short(promisedOn)}
          {estimatedOn && <> · estimada {short(estimatedOn)}</>}
          {slackText && (
            <>
              {" · "}
              <span className={`font-semibold ${TONE[tone].text}`}>{slackText}</span>
            </>
          )}
        </p>
        <div className="ml-auto flex items-center gap-1">
          {actions}
          <button type="button" onClick={toggle} aria-expanded={expanded} aria-controls={bodyId} className="min-h-11 rounded-md px-2 text-sm font-medium text-accent hover:bg-canvas">
            {expanded ? "Comprimir" : "Ver detalle"}
          </button>
        </div>
      </div>

      <div id={bodyId} className="mt-3">
        {loading ? (
          <SkeletonLines lines={3} />
        ) : !steps.length ? (
          <p className="text-sm text-muted">Sin ruta crítica todavía.</p>
        ) : expanded ? (
          <div className="space-y-5">
            <Timeline steps={steps} promisedOn={promisedOn} estimatedOn={estimatedOn} tone={tone} />
            <StepList steps={steps} purchaseOrders={purchaseOrders} />
          </div>
        ) : (
          <Strip steps={steps} purchaseOrders={purchaseOrders} />
        )}
      </div>
    </div>
  );
}

const STRIP: Record<CriticalStep["status"], string> = {
  done: "bg-success text-white",
  in_progress: "bg-accent text-white",
  pending: "bg-canvas text-ink ring-1 ring-inset ring-line",
  late: "bg-danger text-white",
};

// One block per step, as wide as its days; a click shows its dates (a popover,
// a bottom sheet on the phone).
function Strip({ steps, purchaseOrders }: { steps: CriticalStep[]; purchaseOrders: PurchaseOrderListItem[] }) {
  const [open, setOpen] = useState<{ id: string; left: number; sheet: boolean } | null>(null);
  const wrap = useRef<HTMLDivElement | null>(null);
  const spans = steps.map(span);
  const byId = new Map(purchaseOrders.map((po) => [po.id, po]));
  const current = open ? steps.find((s) => s.id === open.id) : undefined;

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(null);
    };
    const onDown = (e: MouseEvent) => {
      if (!open.sheet && wrap.current && !wrap.current.contains(e.target as Node)) setOpen(null);
    };
    document.addEventListener("keydown", onKey);
    document.addEventListener("mousedown", onDown);
    return () => {
      document.removeEventListener("keydown", onKey);
      document.removeEventListener("mousedown", onDown);
    };
  }, [open]);

  return (
    <div ref={wrap} className="relative">
      <div className="flex h-10 gap-1">
        {steps.map((step, i) => {
          const s = spans[i];
          const active = open?.id === step.id;
          return (
            <button
              key={step.id}
              type="button"
              title={`${step.name} · ${range(s.start, s.end)} · ${s.days} ${s.days === 1 ? "día" : "días"}`}
              aria-label={`${step.name}, ${range(s.start, s.end)}, ${STATUS[step.status].label}${step.critical ? ", crítico" : ""}`}
              aria-expanded={active}
              onClick={(e) => {
                if (active) return setOpen(null);
                const el = e.currentTarget;
                const width = wrap.current?.offsetWidth ?? 0;
                const left = Math.min(Math.max(el.offsetLeft + el.offsetWidth / 2 - 144, 0), Math.max(width - 288, 0));
                setOpen({ id: step.id, left, sheet: window.matchMedia("(max-width: 639px)").matches });
              }}
              style={{ flexGrow: s.days, flexBasis: 0 }}
              className={`@container flex min-w-7 items-center justify-center gap-1 overflow-hidden rounded-md px-1.5 text-xs font-medium transition-[filter,box-shadow] duration-200 hover:brightness-110 hover:ring-2 hover:ring-ink/50 motion-reduce:transition-none sm:justify-start sm:px-2 ${STRIP[step.status]} ${active ? "ring-2 ring-ink" : ""}`}
            >
              {step.critical && <Flame size={12} className="shrink-0" aria-hidden />}
              {/* The name shows when the block itself is wide enough (a container query, not a share of the total). */}
              <span className="hidden min-w-0 truncate @min-[3rem]:inline">{step.name}</span>
            </button>
          );
        })}
      </div>
      <p className="mt-1.5 flex flex-wrap gap-x-3 text-[11px] text-muted">
        {Object.values(STATUS).map((st) => (
          <span key={st.label} className="flex items-center gap-1">
            <span className={`inline-block size-2 rounded-sm ${st.bar}`} aria-hidden /> {st.label}
          </span>
        ))}
        <span className="flex items-center gap-1">
          <Flame size={11} className="text-danger" aria-hidden /> Crítico
        </span>
      </p>

      {current && open && !open.sheet && (
        <div role="dialog" aria-label={current.name} className="magic-in absolute top-12 z-20 w-72 rounded-xl bg-surface p-3 text-sm shadow-xl ring-1 ring-line" style={{ left: open.left }}>
          <StepDetails step={current} po={current.purchase_order_id ? byId.get(current.purchase_order_id) : undefined} />
        </div>
      )}
      {current && open?.sheet &&
        createPortal(
          <div className="fixed inset-0 z-50 flex items-end bg-ink/40" onMouseDown={(e) => e.target === e.currentTarget && setOpen(null)}>
            <div role="dialog" aria-modal="true" aria-label={current.name} className="sheet-in w-full rounded-t-2xl bg-surface p-5 pb-8 text-sm shadow-2xl">
              <div className="flex justify-end">
                <button type="button" onClick={() => setOpen(null)} aria-label="Cerrar" className="-mr-2 -mt-2 flex size-11 items-center justify-center rounded-md text-muted">
                  <X size={18} aria-hidden />
                </button>
              </div>
              <StepDetails step={current} po={current.purchase_order_id ? byId.get(current.purchase_order_id) : undefined} />
            </div>
          </div>,
          document.body,
        )}
    </div>
  );
}

// "Corte · del 12 al 14 oct · 2 días", the supplier's dates and lateness.
function StepDetails({ step, po }: { step: CriticalStep; po?: PurchaseOrderListItem }) {
  const s = span(step);
  const st = STATUS[step.status];
  const committed = po?.committed_on ?? null;
  const internal = po?.internal_due_on ?? null;
  const pastLimit = !!internal && time(committed ?? s.end) > time(internal);
  return (
    <div className="space-y-1">
      <p className="flex flex-wrap items-center gap-x-2 font-semibold">
        {step.name}
        {step.critical && (
          <span className="inline-flex items-center gap-0.5 text-xs text-danger">
            <Flame size={12} aria-hidden /> crítico
          </span>
        )}
      </p>
      <p className="tabular-nums">
        {range(s.start, s.end)} · {s.days} {s.days === 1 ? "día" : "días"}
      </p>
      {(committed || internal) && (
        <p className={`text-xs tabular-nums ${pastLimit ? "text-danger" : "text-muted"}`}>
          {[committed && `comprometido ${short(committed)}`, internal && `límite ${short(internal)}`].filter(Boolean).join(" · ")}
        </p>
      )}
      {!!step.late_by && step.late_by > 0 && (
        <p className="flex items-center gap-1 text-xs font-semibold text-danger">
          <OctagonAlert size={12} aria-hidden /> llega {step.late_by} {step.late_by === 1 ? "día" : "días"} tarde
        </p>
      )}
      <p className={`flex items-center gap-1.5 text-xs font-medium ${st.text}`}>
        <span className={`inline-block size-2 rounded-full ${st.bar}`} aria-hidden /> {st.label}
      </p>
      {step.purchase_order_id && (
        <Link href={`/purchase-orders/${step.purchase_order_id}`} className="inline-flex min-h-11 items-center text-xs font-medium text-accent hover:underline sm:min-h-0">
          Ver pedido {po?.code ?? ""}
        </Link>
      )}
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
