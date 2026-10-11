"use client";

import { Check, Crosshair, Play, Square, Truck } from "lucide-react";
import { Button, Pill } from "@/components/ui";
import type { FleetRoute, LivePosition, Vehicle } from "./fleet-types";
import { deliveries, hhmm, signalOf } from "./fleet-utils";

interface Props {
  vehicles: Vehicle[];
  routes: FleetRoute[];
  positions: Record<number, LivePosition>;
  visible: number[];
  follow: number | null;
  now: number;
  busy: string | null;
  onToggle: (vehicleId: number) => void;
  onFollow: (vehicleId: number | null) => void;
  onStart: (routeId: number) => void;
  onSimulate: (vehicleId: number, on: boolean) => void;
  onDeliver: (routeId: number, stopId: number) => void;
}

const SIGNAL = {
  live: { label: "En vivo", className: "text-success" },
  recent: { label: "Hace un momento", className: "text-muted" },
  none: { label: "Sin señal", className: "text-muted" },
} as const;

// En vivo (ADR 0026 §6): the checkboxes drive both the map layers and the SSE
// subscription. Each vehicle shows its stops against the clock.
export default function LivePanel({ vehicles, routes, positions, visible, follow, now, busy, onToggle, onFollow, onStart, onSimulate, onDeliver }: Props) {
  return (
    <div className="space-y-3">
      {vehicles.map((vehicle) => {
        const route =
          routes.find((r) => r.vehicle?.id === vehicle.id && r.status === "in_progress") ??
          routes.find((r) => r.vehicle?.id === vehicle.id && r.status === "planned") ??
          routes.find((r) => r.vehicle?.id === vehicle.id);
        const position = positions[vehicle.id];
        const signal = signalOf(position?.at ?? vehicle.last_seen_at, now);
        const simulating = position?.simulating ?? vehicle.sim_active;
        const stops = route ? deliveries(route.stops) : [];
        const next = stops.find((s) => !s.delivered_at);
        const checked = visible.includes(vehicle.id);
        return (
          <section key={vehicle.id} className={`rounded-xl ring-1 ring-line ${checked ? "" : "opacity-70"}`}>
            <label className="flex min-h-11 cursor-pointer items-center gap-3 px-3 py-2">
              <input type="checkbox" className="size-5 shrink-0 accent-[var(--color-accent)]" checked={checked} onChange={() => onToggle(vehicle.id)} />
              <span className="size-3 shrink-0 rounded-full" style={{ background: signal === "none" ? "#8a8994" : vehicle.color }} aria-hidden />
              <span className="min-w-0 flex-1">
                <span className="block font-semibold">{vehicle.name}</span>
                <span className="block text-xs text-muted">
                  {route ? `${route.summary.delivered}/${route.summary.deliveries} entregas` : "Sin ruta hoy"}
                  {route?.summary.returns_at && route.status !== "completed" ? ` · vuelve ${hhmm(route.summary.returns_at)}` : ""}
                </span>
              </span>
              <span className={`inline-flex items-center gap-1 text-xs font-medium ${SIGNAL[signal].className}`}>
                {signal === "live" && (
                  <span className="relative flex size-2">
                    <span className="absolute inline-flex size-full animate-ping rounded-full bg-success opacity-75" />
                    <span className="relative inline-flex size-2 rounded-full bg-success" />
                  </span>
                )}
                {SIGNAL[signal].label}
              </span>
            </label>

            {route && (
              <div className="space-y-2 border-t border-line px-3 py-2">
                <div className="flex flex-wrap items-center gap-2">
                  <Pill tone={route.status === "in_progress" ? "info" : route.status === "completed" ? "success" : "neutral"}>{route.status_display}</Pill>
                  {simulating && <Pill tone="warning">Simulando</Pill>}
                  <span className="text-xs text-muted tabular-nums">{route.summary.text}</span>
                </div>
                <div className="flex flex-wrap gap-2">
                  {route.status === "planned" && (
                    <Button kind="dark" className="min-h-11" busy={busy === `start-${route.id}`} onClick={() => onStart(route.id)}>
                      <Truck size={16} aria-hidden />
                      Iniciar ruta
                    </Button>
                  )}
                  {route.status === "in_progress" && (
                    <Button kind={simulating ? "ghost" : "primary"} className="min-h-11" busy={busy === `sim-${vehicle.id}`} onClick={() => onSimulate(vehicle.id, !simulating)}>
                      {simulating ? <Square size={16} aria-hidden /> : <Play size={16} aria-hidden />}
                      {simulating ? "Detener simulación" : "Simular"}
                    </Button>
                  )}
                  {checked && (
                    <Button className="min-h-11" onClick={() => onFollow(follow === vehicle.id ? null : vehicle.id)} aria-pressed={follow === vehicle.id}>
                      <Crosshair size={16} aria-hidden />
                      {follow === vehicle.id ? "Dejar de seguir" : "Seguir"}
                    </Button>
                  )}
                </div>
                <ol className="relative space-y-2 border-l-2 border-line pl-4">
                  {stops.map((stop) => {
                    const isNext = route.status === "in_progress" && stop.id === next?.id;
                    return (
                      <li key={stop.id} className="relative text-sm">
                        <span
                          className="absolute -left-[1.4rem] top-0.5 flex size-4 items-center justify-center rounded-full ring-2 ring-surface"
                          style={{ background: stop.delivered_at ? vehicle.color : isNext ? "#fff" : "var(--color-line)", boxShadow: isNext ? `inset 0 0 0 2px ${vehicle.color}` : undefined }}
                          aria-hidden
                        >
                          {stop.delivered_at && <Check size={11} color="#fff" strokeWidth={3} />}
                        </span>
                        <p className={`truncate ${isNext ? "font-semibold" : "font-medium"}`}>
                          {stop.position}. {stop.name}
                        </p>
                        <p className="text-xs text-muted tabular-nums">
                          {stop.order?.code} ·{" "}
                          {stop.delivered_at ? (
                            <span className="text-success">Entregada {hhmm(stop.delivered_at)}</span>
                          ) : (
                            <>llega {hhmm(stop.eta)}</>
                          )}
                          {stop.on_time === false && <span className="ml-1 font-semibold text-danger">· Atrasada</span>}
                        </p>
                        {isNext && !simulating && (
                          <Button className="mt-1 min-h-9 text-xs" busy={busy === `deliver-${stop.id}`} onClick={() => onDeliver(route.id, stop.id)}>
                            <Check size={14} aria-hidden />
                            Marcar entregada
                          </Button>
                        )}
                      </li>
                    );
                  })}
                </ol>
              </div>
            )}
          </section>
        );
      })}
    </div>
  );
}
