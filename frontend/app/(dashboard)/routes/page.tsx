"use client";

import dynamic from "next/dynamic";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense } from "react";
import useSWR from "swr";
import { RoleGate } from "@/components/require-auth";
import { Card, Pill, SectionTitle } from "@/components/ui";
import { fetcher } from "@/lib/api";
import { formatDay, formatDayTime } from "@/lib/format";
import type { Route } from "@/lib/types";

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

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h1 className="text-2xl font-bold tracking-tight">Rutas de recojo y entrega</h1>
        {compare && (
          <Link href="/routes" className="text-sm font-medium text-accent hover:underline">
            Ver la ruta vigente
          </Link>
        )}
      </div>

      <ul className="flex flex-wrap gap-x-5 gap-y-1 text-sm">
        <Legend dash={false} color="#0062fa" label="Vigente" />
        <Legend dash color="#12773d" label="Propuesta (esperando al Gerente)" />
        <Legend dash color="#8a8994" label="Reemplazada" />
      </ul>

      {!loading && !routes.length && <p className="text-sm text-muted">No hay ruta planificada para hoy.</p>}

      <div className="grid gap-4 xl:grid-cols-[1fr_22rem]">
        <div className="h-[60vh] min-h-[420px]">{loading ? <div className="h-full animate-pulse rounded-xl bg-line" /> : <RouteMap routes={routes} focus={main ?? undefined} />}</div>
        <div className="space-y-4">
          {routes.map((route) => (
            <Card key={route.id}>
              <SectionTitle>
                Ruta del {formatDay(route.date)}
                <Pill tone={route.status === "proposed" ? "success" : route.status === "replaced" ? "neutral" : "info"}>{STATUS_LABEL[route.status]}</Pill>
              </SectionTitle>
              <p className="-mt-1 mb-3 text-sm text-muted tabular-nums">
                {Number(route.distance_km).toFixed(1)} km · {Math.round(route.duration_min / 6) / 10} h
              </p>
              <ol className={`space-y-2 ${route.status === "replaced" ? "opacity-60" : ""}`}>
                {[...route.stops]
                  .sort((a, b) => a.position - b.position)
                  .map((stop) => (
                    <li key={stop.position} className="flex gap-2 text-sm">
                      <span className="w-16 shrink-0 whitespace-nowrap text-xs text-muted tabular-nums">{stop.eta ? formatDayTime(stop.eta).split(", ").pop() : ""}</span>
                      <div className="min-w-0">
                        <p className="font-medium">{stop.name}</p>
                        <p className="text-xs text-muted">
                          {stop.kind === "pickup" ? "Recojo" : "Entrega"}
                          {stop.purchase_order && (
                            <>
                              {" · "}
                              <Link href={`/purchase-orders/${stop.purchase_order.id}`} className="text-accent hover:underline">
                                {stop.purchase_order.code}
                              </Link>
                            </>
                          )}
                          {stop.order && (
                            <>
                              {" · "}
                              <Link href={`/orders/${stop.order.id}`} className="text-accent hover:underline">
                                {stop.order.code}
                              </Link>
                            </>
                          )}
                        </p>
                      </div>
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
