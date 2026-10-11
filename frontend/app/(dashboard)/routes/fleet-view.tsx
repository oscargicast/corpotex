"use client";

import { ChevronLeft, ChevronRight, ListChecks, LocateFixed, Maximize2, Minimize2, PanelLeftClose } from "lucide-react";
import dynamic from "next/dynamic";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import useSWR from "swr";
import { Button } from "@/components/ui";
import { ApiError, apiFetch, fetcher } from "@/lib/api";
import DeliveredPanel from "./delivered-panel";
import type { Dispatch, FleetRoute, PlanDayResult, StopEvent, TrailPoint, Vehicle } from "./fleet-types";
import { addDays, dayLabel, dayOf, todayLima } from "./fleet-utils";
import LivePanel from "./live-panel";
import PlanPanel from "./plan-panel";
import { useNow, useVehicleStream, type StreamMode } from "./use-vehicle-stream";

// Leaflet touches window on import: client only.
const FleetMap = dynamic(() => import("./fleet-map"), { ssr: false, loading: () => <div className="h-full animate-pulse bg-line" /> });

type Tab = "plan" | "live" | "delivered";
const TABS: [Tab, string][] = [
  ["plan", "Planificar"],
  ["live", "En vivo"],
  ["delivered", "Entregadas"],
];

const STREAM_LABEL: Record<StreamMode, string> = {
  off: "",
  connecting: "Conectando…",
  live: "En vivo",
  polling: "Actualiza cada 3 s",
};

function errorText(error: unknown): string {
  if (error instanceof ApiError && error.body && typeof error.body === "object" && "detail" in error.body) return String((error.body as { detail: unknown }).detail);
  return "No se pudo completar la acción. Intenta de nuevo.";
}

// Fleet and live routes (ADR 0026 §6): Producción plans the day by vehicle,
// follows the vehicles live and reviews what was delivered. State in the URL:
// ?tab=live&date=2026-10-11&v=1,2&from=&to=
export default function FleetView() {
  const params = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();
  const today = todayLima();
  const tab = (["plan", "live", "delivered"].includes(params.get("tab") ?? "") ? params.get("tab") : "plan") as Tab;
  const date = params.get("date") ?? today;
  const from = params.get("from") ?? today;
  const to = params.get("to") ?? today;

  const setParams = useCallback(
    (changes: Record<string, string | null>) => {
      const next = new URLSearchParams(params.toString());
      for (const [k, v] of Object.entries(changes)) {
        if (v === null || v === "") next.delete(k);
        else next.set(k, v);
      }
      router.replace(`${pathname}?${next.toString()}`, { scroll: false });
    },
    [params, pathname, router],
  );

  const { data: vehicles = [], mutate: reloadVehicles } = useSWR<Vehicle[]>("/api/vehicles/", fetcher, { refreshInterval: 15000 });
  const routesKey = tab === "delivered" ? "/api/routes/?fleet=1&status=completed" : `/api/routes/?fleet=1&date=${date}&status=planned,in_progress,completed`;
  const { data: routesData, mutate: reloadRoutes } = useSWR<FleetRoute[]>(routesKey, fetcher, { refreshInterval: tab === "live" ? 6000 : 15000 });
  const routes = routesData ?? [];
  const { data: pool = [], mutate: reloadPool } = useSWR<Dispatch[]>(tab === "plan" ? `/api/dispatches/?status=ready&to=${date}` : null, fetcher);
  const { data: delivered } = useSWR<Dispatch[]>(tab === "delivered" ? `/api/dispatches/?status=delivered&from=${from}&to=${to}` : null, fetcher, { refreshInterval: 15000 });

  const allIds = vehicles.map((v) => v.id);
  const visible = useMemo(() => {
    const raw = params.get("v");
    if (raw === null) return allIds;
    return raw.split(",").map(Number).filter((id) => allIds.includes(id));
  }, [params, allIds.join(",")]);

  const onStop = useCallback(
    (_event: StopEvent) => {
      void reloadRoutes();
    },
    [reloadRoutes],
  );
  const { positions, mode } = useVehicleStream(visible, tab === "live", onStop);
  const now = useNow(5000);

  const trailKey = tab === "live" && visible.length ? ["trails", visible.join(","), date] : null;
  const { data: trails = {} } = useSWR<Record<number, TrailPoint[]>>(
    trailKey,
    async () => {
      const entries = await Promise.all(visible.map(async (id) => [id, await apiFetch<TrailPoint[]>(`/api/vehicles/${id}/positions/?from=${date}&to=${date}`)] as const));
      return Object.fromEntries(entries);
    },
    { refreshInterval: 60000 },
  );

  const [lastPlan, setLastPlan] = useState<PlanDayResult | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [follow, setFollow] = useState<number | null>(null);
  const [fitSignal, setFitSignal] = useState(0);

  // Fit once the routes of this view arrive (another tab or day fits again);
  // the user's pan and zoom are kept otherwise.
  const fitKey = routesData && vehicles.length ? `${routesKey}|${from}|${to}` : "";
  useEffect(() => {
    if (fitKey) setFitSignal((n) => n + 1);
  }, [fitKey]);
  useEffect(() => setLastPlan(null), [date]);

  const act = async (key: string, run: () => Promise<unknown>) => {
    setBusy(key);
    setError(null);
    try {
      await run();
      await Promise.all([reloadRoutes(), reloadPool(), reloadVehicles()]);
    } catch (e) {
      setError(errorText(e));
    } finally {
      setBusy(null);
    }
  };

  const shownRoutes = tab === "delivered" ? routes.filter((r) => r.date >= from && r.date <= to) : routes;
  const plantStop = shownRoutes[0]?.stops.find((s) => s.kind === "plant") ?? routes[0]?.stops.find((s) => s.kind === "plant");
  const plant: [number, number] | null = plantStop ? [plantStop.lat, plantStop.lng] : null;

  // Full screen on the map's container (Fullscreen API), or a fixed overlay
  // where the API is missing (iPhone Safari). Esc leaves both.
  const frame = useRef<HTMLDivElement>(null);
  const [nativeFull, setNativeFull] = useState(false);
  const [overlayFull, setOverlayFull] = useState(false);
  const [drawer, setDrawer] = useState(true);
  const fullscreen = nativeFull || overlayFull;
  useEffect(() => {
    const sync = () => setNativeFull(document.fullscreenElement === frame.current);
    const esc = (e: KeyboardEvent) => e.key === "Escape" && setOverlayFull(false);
    document.addEventListener("fullscreenchange", sync);
    window.addEventListener("keydown", esc);
    return () => {
      document.removeEventListener("fullscreenchange", sync);
      window.removeEventListener("keydown", esc);
    };
  }, []);
  const toggleFullscreen = () => {
    if (fullscreen) {
      if (document.fullscreenElement) void document.exitFullscreen();
      setOverlayFull(false);
      return;
    }
    const el = frame.current;
    if (el?.requestFullscreen) el.requestFullscreen().catch(() => setOverlayFull(true));
    else setOverlayFull(true);
  };

  const toggleVehicle = (id: number) => {
    const next = visible.includes(id) ? visible.filter((v) => v !== id) : [...visible, id];
    if (follow === id && !next.includes(id)) setFollow(null);
    setParams({ v: next.length === allIds.length ? null : next.join(",") || "none" });
  };

  const panel =
    tab === "plan" ? (
      <PlanPanel
        date={date}
        today={today}
        vehicles={vehicles}
        routes={routes}
        pool={pool.filter((d) => d.scheduled_on === date || (d.scheduled_on < today && date >= today) || routes.some((r) => r.id === d.route_id))}
        lastPlan={lastPlan}
        busy={busy}
        onPlan={() =>
          act("plan", async () => {
            setLastPlan(await apiFetch<PlanDayResult>("/api/routes/plan-day/", { method: "POST", json: { date } }));
            setFitSignal((n) => n + 1);
          })
        }
        onMove={(orderId, vehicleId) => act(`move-${orderId}`, () => apiFetch(`/api/dispatches/${orderId}/`, { method: "PATCH", json: { vehicle_id: vehicleId } }))}
        onReschedule={(orderId, day) => act(`reschedule-${orderId}`, () => apiFetch(`/api/dispatches/${orderId}/`, { method: "PATCH", json: { scheduled_on: day } }))}
      />
    ) : tab === "live" ? (
      <LivePanel
        vehicles={vehicles}
        routes={routes}
        positions={positions}
        visible={visible}
        follow={follow}
        now={now}
        busy={busy}
        onToggle={toggleVehicle}
        onFollow={setFollow}
        onStart={(routeId) => act(`start-${routeId}`, () => apiFetch(`/api/routes/${routeId}/start/`, { method: "POST" }))}
        onSimulate={(vehicleId, on) =>
          act(`sim-${vehicleId}`, () => apiFetch(`/api/vehicles/${vehicleId}/simulate/`, on ? { method: "POST", json: { speed_factor: 12, interval_s: 3 } } : { method: "DELETE" }))
        }
        onDeliver={(routeId, stopId) => act(`deliver-${stopId}`, () => apiFetch(`/api/routes/${routeId}/stops/${stopId}/deliver/`, { method: "POST" }))}
      />
    ) : (
      <DeliveredPanel from={from} to={to} today={today} rows={delivered} onRange={(a, b) => setParams({ from: a, to: b })} />
    );

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Rutas</h1>
          <p className="text-sm text-muted">Entregas de órdenes a clientes desde la planta, por vehículo.</p>
        </div>
        {tab !== "delivered" && (
          <div className="flex items-center gap-1 rounded-lg bg-surface p-1 ring-1 ring-line">
            <button type="button" className="flex size-11 items-center justify-center rounded-md hover:bg-canvas" onClick={() => setParams({ date: addDays(date, -1) })} aria-label="Día anterior">
              <ChevronLeft size={18} />
            </button>
            <span className="min-w-28 text-center text-sm font-semibold tabular-nums">{date === today ? `Hoy, ${dayLabel(date)}` : dayLabel(date)}</span>
            <button type="button" className="flex size-11 items-center justify-center rounded-md hover:bg-canvas" onClick={() => setParams({ date: addDays(date, 1) })} aria-label="Día siguiente">
              <ChevronRight size={18} />
            </button>
            {date !== today && (
              <button type="button" className="min-h-11 rounded-md px-3 text-sm font-medium text-accent hover:bg-canvas" onClick={() => setParams({ date: null })}>
                Hoy
              </button>
            )}
          </div>
        )}
      </div>

      <div role="tablist" aria-label="Vistas de rutas" className="inline-flex rounded-lg bg-canvas p-1 ring-1 ring-line">
        {TABS.map(([key, label]) => (
          <button
            key={key}
            type="button"
            role="tab"
            aria-selected={tab === key}
            onClick={() => setParams({ tab: key === "plan" ? null : key })}
            className={`min-h-11 rounded-md px-4 text-sm font-semibold ${tab === key ? "bg-surface text-ink shadow-sm ring-1 ring-line" : "text-muted hover:text-ink"}`}
          >
            {label}
          </button>
        ))}
      </div>

      {error && (
        <p role="alert" className="rounded-lg bg-danger-soft px-3 py-2 text-sm text-danger">
          {error}
        </p>
      )}

      <div className="grid gap-4 lg:grid-cols-[23rem_1fr]">
        {!fullscreen && <aside className="order-2 min-w-0 lg:order-1 lg:max-h-[calc(100dvh-13rem)] lg:overflow-y-auto lg:pr-1">{panel}</aside>}
        <div
          ref={frame}
          className={
            fullscreen
              ? `${overlayFull ? "fixed inset-0 z-50" : "h-full w-full"} bg-canvas`
              : "relative order-1 h-[60dvh] min-h-[360px] overflow-hidden rounded-xl ring-1 ring-line lg:order-2 lg:h-[calc(100dvh-13rem)]"
          }
        >
          <div className="relative h-full w-full">
            <FleetMap
              routes={shownRoutes}
              vehicles={vehicles}
              positions={positions}
              trails={tab === "live" ? trails : {}}
              visible={tab === "delivered" ? allIds : visible}
              showVehicles={tab === "live"}
              follow={tab === "live" ? follow : null}
              fitSignal={fitSignal}
              fullscreen={fullscreen}
              now={now}
              plant={plant}
              padLeft={fullscreen && drawer ? 380 : 0}
            />

            <div className="pointer-events-none absolute inset-x-3 top-3 z-[1000] flex items-start justify-between gap-2">
              <div className="pointer-events-auto">
                {fullscreen && (
                  <Button kind="dark" className="min-h-11 shadow" onClick={() => setDrawer((d) => !d)} aria-expanded={drawer}>
                    {drawer ? <PanelLeftClose size={16} aria-hidden /> : <ListChecks size={16} aria-hidden />}
                    {drawer ? "Ocultar panel" : tab === "live" ? "Vehículos" : "Panel"}
                  </Button>
                )}
              </div>
              <div className="pointer-events-auto flex gap-2">
                <Button className="min-h-11 bg-surface shadow" onClick={() => setFitSignal((n) => n + 1)} aria-label="Ajustar el mapa a las rutas y vehículos">
                  <LocateFixed size={16} aria-hidden />
                  <span className="hidden sm:inline">Ajustar</span>
                </Button>
                <Button className="min-h-11 bg-surface shadow" onClick={toggleFullscreen} aria-label={fullscreen ? "Salir de pantalla completa" : "Pantalla completa"}>
                  {fullscreen ? <Minimize2 size={16} aria-hidden /> : <Maximize2 size={16} aria-hidden />}
                </Button>
              </div>
            </div>

            {tab === "live" && mode !== "off" && (
              <span className="absolute bottom-6 left-3 z-[1000] inline-flex items-center gap-1.5 rounded-full bg-surface/95 px-3 py-1 text-xs font-medium shadow ring-1 ring-line">
                <span className={`size-2 rounded-full ${mode === "live" ? "bg-success" : mode === "polling" ? "bg-warning" : "bg-line"}`} aria-hidden />
                {STREAM_LABEL[mode]}
                {follow !== null && ` · siguiendo a ${vehicles.find((v) => v.id === follow)?.name ?? ""}`}
              </span>
            )}

            {fullscreen && drawer && (
              <div className="absolute bottom-3 left-3 top-16 z-[1000] w-[23rem] max-w-[calc(100%-1.5rem)] overflow-y-auto rounded-xl bg-surface/95 p-3 shadow-xl ring-1 ring-line backdrop-blur">
                {panel}
              </div>
            )}
          </div>
        </div>
      </div>
      {tab === "delivered" && delivered && delivered.length > 0 && (
        <p className="text-xs text-muted">
          El mapa muestra las rutas completadas del {dayLabel(from)}
          {from !== to ? ` al ${dayLabel(to)}` : ""}. Las entregas sin ruta registrada salen solo en la lista.
          {delivered.some((d) => d.delivered_at && dayOf(d.delivered_at) !== d.scheduled_on) ? " Algunas salieron otro día del programado." : ""}
        </p>
      )}
    </div>
  );
}
