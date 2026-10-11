"use client";

import { Factory } from "lucide-react";
import dynamic from "next/dynamic";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense } from "react";
import useSWR from "swr";
import { RoleGate } from "@/components/require-auth";
import { isPlant } from "@/components/route-map";
import { Card, Pill, SectionTitle } from "@/components/ui";
import { fetcher } from "@/lib/api";
import { formatDay, formatDayTime } from "@/lib/format";
import type { Route, RouteStop } from "@/lib/types";
import { SkeletonCard } from "@/components/skeleton";

// Leaflet touches window on import: client only.
const RouteMap = dynamic(() => import("@/components/route-map"), {
  ssr: false,
  loading: () => <div className="h-full min-h-[420px] animate-pulse rounded-xl bg-line" />,
});

const STATUS_LABEL: Record<Route["status"], string> = {
  proposed: "Propuesta",
  planned: "Planificada",
  in_progress: "En curso",
  completed: "Completada",
  replaced: "Reemplazada",
  discarded: "Descartada",
};

export default function RoutesPage() {
  return (
    <RoleGate roles={["manager", "production"]}>
      <Suspense>
        <Routes />
      </Suspense>
    </RoleGate>
  );
}

// Delivery routes: the van leaves the plant, delivers the day's orders to the
// customers and comes back (ADR 0024). Suppliers ship by agency, so no pickups.
function Routes() {
  const params = useSearchParams();
  const before = params.get("before");
  const after = params.get("after");
  const compare = !!(before && after);

  // Scene mode (from the Redistribución card): both routes by id, in any status.
  const { data: beforeRoute } = useSWR<Route>(compare ? `/api/routes/${before}/` : null, fetcher, { refreshInterval: 3000 });
  const { data: afterRoute } = useSWR<Route>(compare ? `/api/routes/${after}/` : null, fetcher, { refreshInterval: 3000 });
  const { data: current, error } = useSWR<{ current: Route | null; replaced: Route | null }>(
    compare ? null : "/api/routes/?current=1",
    fetcher,
    { refreshInterval: 5000 },
  );

  const routes = (compare ? [beforeRoute, afterRoute] : [current?.current, current?.replaced]).filter(
    (r): r is Route => !!r && r.status !== "discarded",
  );
  const main = compare ? afterRoute : current?.current;
  const loading = compare ? !beforeRoute || !afterRoute : !current && !error;
  const moved = compare && beforeRoute && afterRoute ? movedDeliveries(beforeRoute, afterRoute) : [];

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h1 className="text-2xl font-bold tracking-tight">Rutas de entrega</h1>
        {compare && (
          <Link href="/routes" className="text-sm font-medium text-accent hover:underline">
            Ver la ruta vigente
          </Link>
        )}
      </div>
      <p className="-mt-2 text-sm text-muted">Entregas de órdenes a clientes desde la planta. Los proveedores envían por agencia.</p>

      <ul className="flex flex-wrap gap-x-5 gap-y-1 text-sm">
        <Legend dash={false} color="#0062fa" label="Vigente" />
        <Legend dash color="#12773d" label="Propuesta (esperando al Gerente)" />
        <Legend dash color="#8a8994" label="Reemplazada" />
      </ul>

      {moved.length > 0 && afterRoute && beforeRoute && (
        <p className="rounded-lg bg-success-soft px-3 py-2 text-sm">
          {moved.map((stop, i) => (
            <span key={stop.position}>
              {i > 0 && " · "}
              La entrega a <strong>{stop.customer?.name}</strong>
              {stop.order ? ` (${stop.order.code})` : ""} pasa del {formatDay(beforeRoute.date)} al <strong>{formatDay(afterRoute.date)}</strong>.
            </span>
          ))}
        </p>
      )}

      {!loading && !routes.length && <p className="text-sm text-muted">No hay entregas planificadas para hoy.</p>}

      <div className="grid gap-4 xl:grid-cols-[1fr_22rem]">
        <div className="h-[60vh] min-h-[420px]">{loading ? <div className="h-full animate-pulse rounded-xl bg-line" /> : <RouteMap routes={routes} focus={main ?? undefined} />}</div>
        <div className="space-y-4">
          {loading && <SkeletonCard lines={4} />}
          {routes.map((route) => (
            <Card key={route.id}>
              <SectionTitle>
                Ruta de entregas del {formatDay(route.date)}
                <Pill tone={route.status === "proposed" ? "success" : route.status === "replaced" ? "neutral" : "info"}>{STATUS_LABEL[route.status]}</Pill>
              </SectionTitle>
              <p className="-mt-1 mb-3 text-sm text-muted tabular-nums">
                {deliveries(route).length} {deliveries(route).length === 1 ? "entrega" : "entregas"} · {Number(route.distance_km).toFixed(1)} km ·{" "}
                {Math.round(Number(route.duration_min) / 6) / 10} h
              </p>
              <ol className={`space-y-2 ${route.status === "replaced" ? "opacity-60" : ""}`}>
                {[...route.stops]
                  .sort((a, b) => a.position - b.position)
                  .map((stop) => (
                    <li key={stop.position} className="flex gap-2 text-sm">
                      <span className="w-16 shrink-0 whitespace-nowrap text-xs text-muted tabular-nums">{stop.eta ? formatDayTime(stop.eta).split(", ").pop() : ""}</span>
                      {isPlant(stop, route) ? (
                        <div className="flex min-w-0 items-center gap-2 text-muted">
                          <Factory size={16} className="shrink-0" aria-hidden />
                          <p>{stop.position === 0 ? "Salida de la planta" : "Regreso a la planta"}</p>
                        </div>
                      ) : (
                        <div className="min-w-0">
                          <p className="font-medium">{stop.customer ? `Entrega a ${stop.customer.name}` : stop.name}</p>
                          <p className="text-xs text-muted">
                            {stop.customer && stop.name !== stop.customer.name ? stop.name : stop.address}
                            {stop.order && (
                              <>
                                {" · orden "}
                                <Link href={`/orders/${stop.order.id}`} className="text-accent hover:underline">
                                  {stop.order.code}
                                </Link>
                              </>
                            )}
                          </p>
                        </div>
                      )}
                    </li>
                  ))}
              </ol>
            </Card>
          ))}
          {main?.status === "proposed" && (
            <p className="rounded-lg bg-warning-soft px-3 py-2 text-sm text-warning">
              La ruta nueva se aplica cuando el Gerente aprueba la redistribución en el Monitor.
            </p>
          )}
        </div>
      </div>
    </div>
  );
}

function deliveries(route: Route): RouteStop[] {
  return route.stops.filter((stop) => !isPlant(stop, route));
}

// The deliveries the redistribution moved to the new day: in the proposed route
// and tied to an order the original day's route also carried (or, when the
// backend already took them off that day, every delivery of the new route).
function movedDeliveries(before: Route, after: Route): RouteStop[] {
  const beforeOrders = new Set(deliveries(before).map((s) => s.order?.id).filter(Boolean));
  const shared = deliveries(after).filter((s) => s.order && beforeOrders.has(s.order.id));
  const moved = shared.length ? shared : deliveries(after);
  return before.date === after.date ? [] : moved.filter((s) => s.customer);
}

function Legend({ color, dash, label }: { color: string; dash: boolean; label: string }) {
  return (
    <li className="flex items-center gap-2">
      <svg width="28" height="6" aria-hidden>
        <line x1="0" y1="3" x2="28" y2="3" stroke={color} strokeWidth="4" strokeDasharray={dash ? "6 4" : undefined} />
      </svg>
      {label}
    </li>
  );
}
