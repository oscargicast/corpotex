"use client";

import { CalendarClock, Sparkles, Truck } from "lucide-react";
import { Button, Pill } from "@/components/ui";
import { formatDay } from "@/lib/format";
import type { Dispatch, FleetRoute, PlanDayResult, Vehicle } from "./fleet-types";
import { addDays, deliveries, hhmm } from "./fleet-utils";

interface Props {
  date: string;
  today: string;
  vehicles: Vehicle[];
  routes: FleetRoute[];
  pool: Dispatch[];
  lastPlan: PlanDayResult | null;
  busy: string | null;
  onPlan: () => void;
  onMove: (orderId: number, vehicleId: number) => void;
  onReschedule: (orderId: number, day: string) => void;
}

// Planificar (ADR 0026 §6): the day's ready orders, one column per vehicle with
// its capacity bar, and what did not fit with its reason.
export default function PlanPanel({ date, today, vehicles, routes, pool, lastPlan, busy, onPlan, onMove, onReschedule }: Props) {
  const live = routes.filter((r) => r.status === "planned" || r.status === "in_progress");
  const onRoute = new Set(live.flatMap((r) => deliveries(r.stops).map((s) => s.order?.id)));
  const waiting = pool.filter((d) => !onRoute.has(d.order.id));
  const reasons = new Map((lastPlan?.unassigned ?? []).map((u) => [u.order_id, u.reason_display]));
  const totalUnits = pool.reduce((sum, d) => sum + d.order.units, 0);
  const capacity = vehicles.reduce((sum, v) => sum + v.capacity_units, 0);

  return (
    <div className="space-y-4">
      <div className="rounded-xl bg-canvas p-3">
        <p className="text-sm">
          <strong className="tabular-nums">{pool.length}</strong> órdenes listas para el {formatDay(date)} ·{" "}
          <span className="tabular-nums">{totalUnits.toLocaleString("es-PE")}</span> prendas · flota de{" "}
          <span className="tabular-nums">{capacity.toLocaleString("es-PE")}</span>
        </p>
        <Button kind="primary" className="mt-3 min-h-11 w-full" busy={busy === "plan"} onClick={onPlan} disabled={date < today}>
          <Sparkles size={16} aria-hidden />
          {live.length ? "Volver a planificar el día" : "Planificar el día"}
        </Button>
        {date < today && <p className="mt-2 text-xs text-muted">Ese día ya pasó: revisa la pestaña Entregadas.</p>}
      </div>

      {vehicles.map((vehicle) => {
        const route = live.find((r) => r.vehicle?.id === vehicle.id) ?? routes.find((r) => r.vehicle?.id === vehicle.id);
        const units = route?.summary.units ?? 0;
        const pct = Math.round((units * 100) / vehicle.capacity_units);
        const locked = route?.status !== "planned";
        return (
          <section key={vehicle.id} className="rounded-xl ring-1 ring-line">
            <header className="flex items-center gap-2 border-b border-line px-3 py-2">
              <span className="size-3 shrink-0 rounded-full" style={{ background: vehicle.color }} aria-hidden />
              <h3 className="font-semibold">{vehicle.name}</h3>
              <span className="text-xs text-muted">{vehicle.kind_display}</span>
              {route && <Pill tone={route.status === "in_progress" ? "info" : route.status === "completed" ? "success" : "neutral"}>{route.status_display}</Pill>}
            </header>
            <div className="space-y-2 px-3 py-2">
              <div>
                <div className="flex justify-between text-xs tabular-nums text-muted">
                  <span>
                    {units.toLocaleString("es-PE")} / {vehicle.capacity_units.toLocaleString("es-PE")} prendas
                  </span>
                  <span className={pct > 100 ? "font-semibold text-danger" : ""}>{pct} %</span>
                </div>
                <div className="mt-1 h-2 overflow-hidden rounded-full bg-canvas" role="meter" aria-valuemin={0} aria-valuemax={100} aria-valuenow={pct} aria-label={`Capacidad de ${vehicle.name}`}>
                  <div className="h-full rounded-full" style={{ width: `${Math.min(pct, 100)}%`, background: pct > 100 ? "var(--color-danger)" : vehicle.color }} />
                </div>
              </div>
              {route ? <p className="text-xs text-muted tabular-nums">{route.summary.text}</p> : <p className="text-xs text-muted">Sin entregas este día.</p>}
              <ol className="space-y-1.5">
                {route &&
                  deliveries(route.stops).map((stop) => (
                    <li key={stop.id} className="flex items-start gap-2 text-sm">
                      <span className="mt-0.5 flex size-5 shrink-0 items-center justify-center rounded-full text-[11px] font-bold text-white tabular-nums" style={{ background: vehicle.color }}>
                        {stop.position}
                      </span>
                      <div className="min-w-0 flex-1">
                        <p className="truncate font-medium">
                          {stop.order?.code} · {stop.name}
                        </p>
                        <p className="text-xs text-muted tabular-nums">
                          {stop.units} prendas · llega {hhmm(stop.eta)}
                          {stop.on_time === false && <span className="ml-1 font-semibold text-danger">· Atrasada</span>}
                        </p>
                        {!locked && stop.order && (
                          <OrderActions orderId={stop.order.id} date={date} vehicles={vehicles.filter((v) => v.id !== vehicle.id)} busy={busy} onMove={onMove} onReschedule={onReschedule} />
                        )}
                      </div>
                    </li>
                  ))}
              </ol>
            </div>
          </section>
        );
      })}

      <section className="rounded-xl ring-1 ring-line">
        <header className="flex items-center gap-2 border-b border-line px-3 py-2">
          <CalendarClock size={16} className="text-muted" aria-hidden />
          <h3 className="font-semibold">Sin asignar</h3>
          <span className="rounded-full bg-canvas px-2 text-xs font-medium text-muted tabular-nums">{waiting.length}</span>
        </header>
        {waiting.length === 0 ? (
          <p className="px-3 py-2 text-sm text-muted">Todas las órdenes listas tienen vehículo.</p>
        ) : (
          <ul className="divide-y divide-line">
            {waiting.map((d) => (
              <li key={d.order.id} className="px-3 py-2 text-sm">
                <p className="font-medium">
                  {d.order.code} · {d.order.customer_name}
                </p>
                <p className="text-xs text-muted tabular-nums">
                  {d.order.units} prendas · promesa {formatDay(d.order.promised_on)}
                  {d.scheduled_on < today && <span className="ml-1 font-semibold text-danger">· Atrasada</span>}
                </p>
                <p className="mt-0.5 text-xs font-medium text-warning">{reasons.get(d.order.id) ?? "Sin vehículo todavía"}</p>
                <div className="mt-1.5 flex flex-wrap gap-2">
                  <Button className="min-h-11" busy={busy === `reschedule-${d.order.id}`} onClick={() => onReschedule(d.order.id, addDays(date, 1))}>
                    Pasar a mañana
                  </Button>
                  <OrderActions orderId={d.order.id} date={date} vehicles={vehicles} busy={busy} onMove={onMove} onReschedule={onReschedule} onlyMove />
                </div>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}

function OrderActions({
  orderId,
  date,
  vehicles,
  busy,
  onMove,
  onReschedule,
  onlyMove = false,
}: {
  orderId: number;
  date: string;
  vehicles: Vehicle[];
  busy: string | null;
  onMove: (orderId: number, vehicleId: number) => void;
  onReschedule: (orderId: number, day: string) => void;
  onlyMove?: boolean;
}) {
  const working = busy === `move-${orderId}` || busy === `reschedule-${orderId}`;
  return (
    <div className="mt-1 flex flex-wrap items-center gap-2">
      <label className="inline-flex items-center gap-1 text-xs text-muted">
        <Truck size={14} aria-hidden />
        <span className="sr-only">Mover a otro vehículo</span>
        <select
          className="min-h-9 rounded-md bg-surface px-2 text-xs text-ink ring-1 ring-line"
          value=""
          disabled={working}
          onChange={(e) => e.target.value && onMove(orderId, Number(e.target.value))}
        >
          <option value="">Mover a…</option>
          {vehicles.map((v) => (
            <option key={v.id} value={v.id}>
              {v.name}
            </option>
          ))}
        </select>
      </label>
      {!onlyMove && (
        <label className="inline-flex items-center gap-1 text-xs text-muted">
          <CalendarClock size={14} aria-hidden />
          <span className="sr-only">Reprogramar a otra fecha</span>
          <input
            type="date"
            className="min-h-9 rounded-md bg-surface px-2 text-xs text-ink ring-1 ring-line"
            min={date}
            defaultValue=""
            disabled={working}
            aria-label="Reprogramar"
            onChange={(e) => e.target.value && e.target.value !== date && onReschedule(orderId, e.target.value)}
          />
        </label>
      )}
    </div>
  );
}
