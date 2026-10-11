"use client";

import { Pause } from "lucide-react";
import Link from "next/link";
import useSWR from "swr";
import { AlertList } from "@/components/alert-list";
import { DecisionCard } from "@/components/decision-card";
import { OnboardingBanner } from "@/components/onboarding-banner";
import { RedistributionCard } from "@/components/redistribution-card";
import { useUser } from "@/components/require-auth";
import { Card, Pill, RISK_LABEL, RISK_TONE, ROW_HOVER, SectionTitle } from "@/components/ui";
import { fetcher } from "@/lib/api";
import { formatDay, formatMoney, num } from "@/lib/format";
import type { Monitor, PaymentSummary, PlantLoad } from "@/lib/types";
import { SkeletonMonitor } from "@/components/skeleton";

export default function MonitorPage() {
  const user = useUser();
  const isManager = user.role === "manager";
  const { data, mutate, error } = useSWR<Monitor>("/api/monitor/", fetcher, { refreshInterval: 3000 });

  if (error && !data) return <p className="text-danger">No se pudo cargar el Monitor.</p>;
  if (!data) return <SkeletonMonitor />;

  const refresh = () => mutate();
  const kpis = [
    { label: "Órdenes en peligro", value: data.kpis.orders_in_danger, alert: data.kpis.orders_in_danger > 0 },
    ...(isManager ? [{ label: "Decisiones pendientes", value: data.kpis.pending_decisions ?? 0, alert: (data.kpis.pending_decisions ?? 0) > 0 }] : []),
    { label: "Pedidos sin avance", value: data.kpis.stalled_purchase_orders, alert: data.kpis.stalled_purchase_orders > 0 },
    { label: "Alertas abiertas", value: data.kpis.open_alerts, alert: false },
  ];
  const plant = data.plant ?? null;
  const cols = kpis.length + (plant ? 2 : 0);

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center gap-3">
        <h1 className="text-2xl font-bold tracking-tight">Monitor</h1>
        {data.agent?.paused && (
          <Pill tone="warning">
            <Pause size={12} className="mr-1" aria-hidden /> Agente en pausa
          </Pill>
        )}
      </div>
      <OnboardingBanner />

      <div className={`grid grid-cols-2 gap-3 ${LG_COLS[cols] ?? "lg:grid-cols-4"}`}>
        {kpis.map((kpi) => (
          <div key={kpi.label} className="rounded-xl bg-surface p-4 ring-1 ring-line">
            <p className="text-xs text-muted">{kpi.label}</p>
            <p className={`mt-1 text-3xl font-bold tabular-nums ${kpi.alert ? "text-danger" : ""}`}>{kpi.value}</p>
          </div>
        ))}
        {plant && <PlantKpi plant={plant} />}
      </div>

      <div className="grid gap-5 xl:grid-cols-2">
        <div className="space-y-5">
          {isManager && (
            <Card>
              <SectionTitle count={data.decisions.length}>Decisiones pendientes</SectionTitle>
              {data.decisions.length ? (
                <div className="space-y-3">
                  {data.decisions.map((decision) => (
                    <DecisionCard key={decision.id} decision={decision} onResolved={refresh} />
                  ))}
                </div>
              ) : (
                <p className="text-sm text-muted">Nada por decidir.</p>
              )}
            </Card>
          )}
          {data.redistributions.length > 0 && (
            <Card>
              <SectionTitle count={data.redistributions.length}>Redistribuciones recientes</SectionTitle>
              <div className="space-y-3">
                {data.redistributions.map((decision) => (
                  <RedistributionCard key={decision.id} decision={decision} />
                ))}
              </div>
            </Card>
          )}
          <Card>
            <SectionTitle count={data.orders_in_danger.length}>Órdenes en peligro</SectionTitle>
            {data.orders_in_danger.length ? (
              <ul className="divide-y divide-line">
                {data.orders_in_danger.map((order) => (
                  <li key={order.id} className="py-2 first:pt-0 last:pb-0">
                    {/* One line; the reason in full as the tooltip. */}
                    <Link
                      href={`/orders/${order.id}`}
                      title={order.risk_reason || undefined}
                      className={`-mx-2 flex min-h-11 flex-wrap items-center gap-x-2 gap-y-0.5 rounded-md px-2 py-1 text-sm ${ROW_HOVER}`}
                    >
                      <span className="shrink-0 whitespace-nowrap font-semibold text-accent">{order.code}</span>
                      <span className="min-w-0 flex-1 truncate sm:flex-none">{order.customer.name}</span>
                      <Pill tone={RISK_TONE[order.risk]}>{RISK_LABEL[order.risk]}</Pill>
                      <span className="w-full text-xs tabular-nums text-muted sm:ml-auto sm:w-auto sm:shrink-0">
                        entrega {formatDay(order.promised_on)} · <span className="font-medium text-danger">est. {formatDay(order.estimated_on)}</span>
                      </span>
                    </Link>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="text-sm text-muted">Todas las órdenes llegan a tiempo.</p>
            )}
          </Card>
        </div>

        <div className="space-y-5">
          <Card>
            <SectionTitle count={data.alerts.length}>Alertas</SectionTitle>
            <AlertList alerts={data.alerts} canAcknowledge={isManager} onChange={refresh} />
          </Card>
          {isManager && data.payments_by_supplier && <Payments rows={data.payments_by_supplier} />}
        </div>
      </div>
    </div>
  );
}

// Deposited and pending per supplier, always per currency (no PEN + USD sums).
function Payments({ rows }: { rows: PaymentSummary[] }) {
  return (
    <Card>
      <SectionTitle>Pagos a proveedores</SectionTitle>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="text-left text-xs text-muted">
            <tr>
              <th className="pb-2 font-medium">Proveedor</th>
              <th className="pb-2 text-right font-medium">Depositado</th>
              <th className="pb-2 text-right font-medium">Saldo</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-line">
            {rows.map((row) => (
              <tr key={`${row.supplier.id}-${row.currency}`}>
                <td className="py-2">
                  <Link href={`/suppliers/${row.supplier.id}`} className="hover:underline">
                    {row.supplier.name}
                  </Link>
                  {row.overdue_count > 0 && (
                    <span className="ml-2">
                      <Pill tone="danger">{row.overdue_count} vencido{row.overdue_count > 1 ? "s" : ""}</Pill>
                    </span>
                  )}
                </td>
                <td className="py-2 text-right tabular-nums">{formatMoney(row.paid, row.currency)}</td>
                <td className={`py-2 text-right tabular-nums ${Number(row.pending) > 0 ? "font-semibold" : "text-muted"}`}>
                  {formatMoney(row.pending, row.currency)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Card>
  );
}

// Literal classes so Tailwind sees them: the plant KPI takes two columns.
const LG_COLS: Record<number, string> = { 3: "lg:grid-cols-3", 4: "lg:grid-cols-4", 5: "lg:grid-cols-5", 6: "lg:grid-cols-6" };

// Own plant load (ADR 0030): it left the suppliers list and lives here.
function PlantKpi({ plant }: { plant: PlantLoad }) {
  const pct = Math.round(num(plant.load_pct) ?? 0);
  const full = pct >= 85;
  return (
    <div className="col-span-2 rounded-xl bg-surface p-4 ring-1 ring-line">
      <p className="flex items-baseline justify-between gap-2 text-xs text-muted">
        <span>Capacidad de planta</span>
        {full && <span className="font-medium text-danger">Saturada</span>}
      </p>
      <p className={`mt-1 text-3xl font-bold tabular-nums ${full ? "text-danger" : ""}`}>{pct} %</p>
      <div
        className="mt-2 h-2 overflow-hidden rounded-full bg-canvas"
        role="meter"
        aria-label={`Carga de ${plant.name}`}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={pct}
      >
        <div className={`h-full rounded-full ${full ? "bg-danger" : "bg-success"}`} style={{ width: `${Math.min(pct, 100)}%` }} />
      </div>
      <p className="mt-2 text-xs tabular-nums text-muted">
        {plant.units_in_progress} u. en curso de {plant.weekly_capacity} u./semana · {plant.open_purchase_orders}{" "}
        {plant.open_purchase_orders === 1 ? "pedido de taller" : "pedidos de taller"}
      </p>
    </div>
  );
}
