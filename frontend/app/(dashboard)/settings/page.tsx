"use client";

import { CalendarClock, CheckCircle2, Flag } from "lucide-react";
import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import useSWR, { useSWRConfig } from "swr";
import { SkeletonCard, SkeletonLines } from "@/components/skeleton";
import { Button, Card, Pill, SectionTitle } from "@/components/ui";
import { ApiError, apiFetch, fetcher } from "@/lib/api";
import {
  DEFAULT_FOLLOW_UP,
  FOLLOW_UP_MODES,
  type FollowUpMode,
  type FollowUpPreviewItem,
  type FollowUpSettings,
  minutesOf,
  normalizeFollowUp,
  todayWeekday,
  WEEKDAY_NAMES,
  WEEKDAYS,
} from "@/lib/follow-up";

const SETTINGS_URL = "/api/settings/follow-up/";
const PREVIEW_URL = "/api/settings/follow-up/preview/";
const MODES = Object.keys(FOLLOW_UP_MODES) as FollowUpMode[];

const timeFormat = new Intl.DateTimeFormat("es-PE", { timeZone: "America/Lima", hour: "2-digit", minute: "2-digit" });
const isMissing = (err: unknown) => err instanceof ApiError && err.status === 404;

// Configuración › Seguimiento (ADR 0027 §4): how often the agent checks in with
// suppliers, within which hours and days, and what it plans to do today.
export default function FollowUpSettingsPage() {
  const { data, error, mutate } = useSWR<unknown>(SETTINGS_URL, fetcher, { shouldRetryOnError: false });
  const unavailable = isMissing(error);
  const loaded = useMemo(() => (data === undefined ? undefined : normalizeFollowUp(data)), [data]);
  const saved = loaded ?? (unavailable ? DEFAULT_FOLLOW_UP : undefined);

  if (!saved) return error ? <p className="text-sm text-danger">No se pudo cargar la configuración de seguimiento.</p> : <SkeletonCard lines={6} />;

  return (
    <div className="space-y-4">
      <FollowUpForm saved={saved} unavailable={unavailable} onSaved={(next) => mutate(next, { revalidate: false })} />
      <TodayPlan weekdays={saved.weekdays} />
    </div>
  );
}

function FollowUpForm({ saved, unavailable, onSaved }: { saved: FollowUpSettings; unavailable: boolean; onSaved: (s: FollowUpSettings) => void }) {
  const [form, setForm] = useState<FollowUpSettings>(saved);
  const [busy, setBusy] = useState(false);
  const [confirmed, setConfirmed] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const { mutate: revalidate } = useSWRConfig();

  const start = minutesOf(form.window_start);
  const end = minutesOf(form.window_end);
  const windowError =
    start === null || end === null
      ? "Completa las dos horas."
      : start >= end
        ? "«Desde» tiene que ser antes que «Hasta»."
        : end - start < 120
          ? "La ventana tiene que durar al menos 2 horas."
          : null;
  const daysError = form.weekdays.length ? null : "Elige al menos un día.";
  const dirty = JSON.stringify(form) !== JSON.stringify(saved);

  useEffect(() => {
    if (!confirmed) return;
    const id = setTimeout(() => setConfirmed(false), 4000);
    return () => clearTimeout(id);
  }, [confirmed]);

  function update(patch: Partial<FollowUpSettings>) {
    setForm((f) => ({ ...f, ...patch }));
    setConfirmed(false);
  }

  function toggleDay(day: number) {
    const days = form.weekdays.includes(day) ? form.weekdays.filter((d) => d !== day) : [...form.weekdays, day];
    update({ weekdays: days.sort((a, b) => a - b) });
  }

  async function save() {
    if (windowError || daysError) return;
    setBusy(true);
    setError(null);
    try {
      const response = await apiFetch<unknown>(SETTINGS_URL, { method: "PATCH", json: form });
      const next = response ? normalizeFollowUp(response) : form;
      setForm(next);
      onSaved(next);
      // Today's plan depends on the window and the days.
      revalidate(PREVIEW_URL);
      setConfirmed(true);
    } catch (err) {
      const detail = err instanceof ApiError ? (err.body as { detail?: string } | null)?.detail : null;
      setError(detail ?? "No se pudo guardar. Inténtalo de nuevo.");
    } finally {
      setBusy(false);
    }
  }

  const mode = FOLLOW_UP_MODES[form.mode];

  return (
    <Card>
      <SectionTitle>Seguimiento a proveedores</SectionTitle>
      <p className="-mt-1 text-sm text-muted">
        Cuándo el agente le escribe a cada proveedor para preguntar por sus pedidos. Como máximo un mensaje al día por proveedor, más un recordatorio si no responde.
      </p>
      {unavailable && (
        <p className="mt-3 rounded-lg bg-warning-soft px-3 py-2 text-sm text-warning">
          El servidor todavía no guarda esta configuración. Se muestran los valores por defecto.
        </p>
      )}

      {/* Mode */}
      <fieldset className="mt-5">
        <legend className="text-sm font-medium">Modo</legend>
        <div className="mt-2 grid grid-cols-3 rounded-lg bg-canvas p-1 ring-1 ring-line" role="radiogroup" aria-label="Modo de seguimiento">
          {MODES.map((key) => {
            const active = form.mode === key;
            return (
              <button
                key={key}
                type="button"
                role="radio"
                aria-checked={active}
                onClick={() => update({ mode: key })}
                className={`min-h-11 rounded-md px-2 text-sm font-semibold transition-colors ${active ? "bg-surface text-ink shadow-sm ring-1 ring-line" : "text-muted hover:text-ink"}`}
              >
                {FOLLOW_UP_MODES[key].label}
              </button>
            );
          })}
        </div>
        <p className="mt-2 text-sm">{mode.about}</p>
        <p className="text-sm text-muted">{mode.reminder}</p>
        <ModeTimeline days={mode.days} />
        <p className="mt-2 text-xs text-muted">
          En cualquier modo escribe si la entrega es hoy o mañana sin confirmar, si el avance va atrasado o si no hay reportes pasado el 30 % del plazo.
        </p>
      </fieldset>

      {/* Window */}
      <fieldset className="mt-6">
        <legend className="text-sm font-medium">Rango horario</legend>
        <div className="mt-2 flex flex-wrap items-start gap-3">
          <label className="text-sm">
            <span className="block text-xs text-muted">Desde</span>
            <input
              type="time"
              value={form.window_start}
              onChange={(e) => update({ window_start: e.target.value })}
              aria-invalid={!!windowError}
              aria-describedby={windowError ? "window-error" : undefined}
              className={`mt-1 min-h-11 rounded-md bg-surface px-3 tabular-nums ring-1 ${windowError ? "ring-danger" : "ring-line"}`}
            />
          </label>
          <label className="text-sm">
            <span className="block text-xs text-muted">Hasta</span>
            <input
              type="time"
              value={form.window_end}
              onChange={(e) => update({ window_end: e.target.value })}
              aria-invalid={!!windowError}
              aria-describedby={windowError ? "window-error" : undefined}
              className={`mt-1 min-h-11 rounded-md bg-surface px-3 tabular-nums ring-1 ${windowError ? "ring-danger" : "ring-line"}`}
            />
          </label>
          <p className="self-end pb-3 text-xs text-muted">Hora de Lima</p>
        </div>
        {windowError && (
          <p id="window-error" className="mt-1 text-sm text-danger" role="alert">
            {windowError}
          </p>
        )}
      </fieldset>

      {/* Days */}
      <fieldset className="mt-6">
        <legend className="text-sm font-medium">Días</legend>
        <div className="mt-2 flex flex-wrap gap-1.5 sm:gap-2">
          {WEEKDAYS.map((label, day) => {
            const on = form.weekdays.includes(day);
            return (
              <button
                key={label}
                type="button"
                aria-pressed={on}
                aria-label={WEEKDAY_NAMES[day]}
                title={WEEKDAY_NAMES[day]}
                onClick={() => toggleDay(day)}
                className={`size-10 rounded-full text-sm font-semibold ring-1 transition-colors sm:size-11 ${on ? "bg-ink text-white ring-ink" : "bg-surface text-muted ring-line hover:bg-canvas"}`}
              >
                {label}
              </button>
            );
          })}
        </div>
        {daysError && (
          <p className="mt-1 text-sm text-danger" role="alert">
            {daysError}
          </p>
        )}
      </fieldset>

      <div className="mt-6 flex flex-wrap items-center gap-3 border-t border-line pt-4">
        <Button kind="primary" busy={busy} disabled={unavailable || !dirty || !!windowError || !!daysError} onClick={save}>
          Guardar
        </Button>
        {confirmed && (
          <span className="flex items-center gap-1.5 text-sm text-success" role="status">
            <CheckCircle2 size={16} aria-hidden /> Guardado. El agente lo aplica desde el próximo minuto.
          </span>
        )}
        {error && (
          <span className="text-sm text-danger" role="alert">
            {error}
          </span>
        )}
      </div>
    </Card>
  );
}

// A 10-day purchase order: the days the agent would write, then the delivery.
function ModeTimeline({ days }: { days: number[] }) {
  return (
    <div className="mt-3" aria-label={`Ejemplo, pedido de 10 días: escribe los días ${days.join(", ")}`}>
      <p className="text-xs text-muted">Ejemplo: pedido de 10 días</p>
      <ol className="mt-1.5 grid grid-cols-10 gap-1">
        {Array.from({ length: 10 }, (_, i) => i + 1).map((day) => {
          const write = days.includes(day);
          const delivery = day === 10;
          return (
            <li key={day} className="flex flex-col items-center gap-1">
              <span
                className={`flex h-7 w-full items-center justify-center rounded-md text-[11px] font-semibold tabular-nums ${
                  delivery ? "bg-ink text-white" : write ? "bg-accent text-white" : "bg-canvas text-muted"
                }`}
              >
                {delivery ? <Flag size={12} aria-hidden /> : day}
              </span>
              <span className="hidden text-[10px] text-muted sm:block">{delivery ? "entrega" : write ? "escribe" : ""}</span>
            </li>
          );
        })}
      </ol>
      <p className="mt-1 flex items-center gap-3 text-[11px] text-muted sm:hidden">
        <span className="flex items-center gap-1">
          <span className="size-2.5 rounded-sm bg-accent" aria-hidden /> escribe
        </span>
        <span className="flex items-center gap-1">
          <span className="size-2.5 rounded-sm bg-ink" aria-hidden /> entrega
        </span>
      </p>
    </div>
  );
}

// What the agent plans for today, from the preview endpoint.
function TodayPlan({ weekdays }: { weekdays: number[] }) {
  const { data, error } = useSWR<FollowUpPreviewItem[]>(PREVIEW_URL, fetcher, { refreshInterval: 60_000, shouldRetryOnError: false });
  const today = todayWeekday();
  const rows = [...(data ?? [])].sort((a, b) => a.at.localeCompare(b.at));

  return (
    <Card>
      <SectionTitle count={data ? rows.length : undefined}>Plan de hoy</SectionTitle>
      {!data && !error && <SkeletonLines lines={3} />}
      {error && (
        <p className="text-sm text-muted">{isMissing(error) ? "El plan de hoy estará disponible cuando el servidor lo publique." : "No se pudo cargar el plan de hoy."}</p>
      )}
      {data && !rows.length && (
        <div className="flex items-start gap-3 rounded-lg bg-canvas px-4 py-3 text-sm">
          <CalendarClock size={20} className="mt-0.5 shrink-0 text-muted" aria-hidden />
          <p>
            <span className="font-medium">Hoy no hay seguimientos programados.</span>{" "}
            <span className="text-muted">
              {today >= 0 && !weekdays.includes(today)
                ? `El ${WEEKDAY_NAMES[today]} no está entre los días de seguimiento.`
                : "Ningún pedido abierto llega hoy a un punto de control."}
            </span>
          </p>
        </div>
      )}
      {rows.length > 0 && (
        <ul className="divide-y divide-line">
          {rows.map((row, i) => (
            <li key={`${row.supplier.id}-${row.at}-${i}`} className="grid gap-1 py-3 first:pt-0 sm:grid-cols-[6rem_minmax(0,1fr)_auto] sm:items-start sm:gap-3">
              <span className="whitespace-nowrap font-semibold tabular-nums">{timeFormat.format(new Date(row.at))}</span>
              <div className="min-w-0 text-sm">
                <p>
                  <Link href={`/suppliers/${row.supplier.id}`} className="font-medium hover:underline">
                    {row.supplier.name}
                  </Link>
                  {row.purchase_orders.length > 0 && (
                    <span className="text-muted">
                      {" · "}
                      {row.purchase_orders.map((code, j) => (
                        <span key={code}>
                          {j > 0 && ", "}
                          <Link href={`/purchase-orders/${code}`} className="text-accent hover:underline">
                            {code}
                          </Link>
                        </span>
                      ))}
                    </span>
                  )}
                </p>
                <p className="text-muted">{row.reason}</p>
              </div>
              <span className="sm:justify-self-end">
                <Pill tone={row.kind === "reminder" ? "warning" : "info"}>{row.kind === "reminder" ? "Recordatorio" : "Seguimiento"}</Pill>
              </span>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}
