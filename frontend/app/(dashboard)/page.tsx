"use client";

import Link from "next/link";
import useSWR from "swr";
import { AlertList } from "@/components/alert-list";
import { DecisionCard } from "@/components/decision-card";
import { RedistributionCard } from "@/components/redistribution-card";
import { useUser } from "@/components/require-auth";
import { Card, Pill, RISK_LABEL, RISK_TONE, SectionTitle } from "@/components/ui";
import { fetcher } from "@/lib/api";
import { formatDay, formatMoney } from "@/lib/format";
import type { Monitor, PaymentSummary } from "@/lib/types";

export default function MonitorPage() {
  const user = useUser();
  const isManager = user.role === "manager";
  const { data, mutate, error } = useSWR<Monitor>("/api/monitor/", fetcher, { refreshInterval: 3000 });

  if (error && !data) return <p className="text-danger">No se pudo cargar el Monitor.</p>;
  if (!data) return <div className="h-40 animate-pulse rounded-xl bg-line" />;

  const refresh = () => mutate();
  const kpis = [
    { label: "Órdenes en peligro", value: data.kpis.orders_in_danger, alert: data.kpis.orders_in_danger > 0 },
    ...(isManager ? [{ label: "Decisiones pendientes", value: data.kpis.pending_decisions ?? 0, alert: (data.kpis.pending_decisions ?? 0) > 0 }] : []),
    { label: "Pedidos sin avance", value: data.kpis.stalled_purchase_orders, alert: data.kpis.stalled_purchase_orders > 0 },
    { label: "Alertas abiertas", value: data.kpis.open_alerts, alert: false },
  ];

  return (
    <div className="space-y-5">
      <h1 className="text-2xl font-bold tracking-tight">Monitor</h1>

      <div className={`grid grid-cols-2 gap-3 ${kpis.length === 4 ? "lg:grid-cols-4" : "lg:grid-cols-3"}`}>
        {kpis.map((kpi) => (
          <div key={kpi.label} className="rounded-xl bg-surface p-4 ring-1 ring-line">
            <p className="text-xs text-muted">{kpi.label}</p>
            <p className={`mt-1 text-3xl font-bold tabular-nums ${kpi.alert ? "text-danger" : ""}`}>{kpi.value}</p>
          </div>
        ))}
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
              <SectionTitle>Redistribuciones recientes</SectionTitle>
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
                  <li key={order.id} className="py-2.5 first:pt-0 last:pb-0">
                    <div className="flex flex-wrap items-center gap-2">
                      <Link href={`/orders/${order.id}`} className="font-semibold text-accent hover:underline">
                        {order.code}
                      </Link>
                      <span className="text-sm">{order.customer.name}</span>
                      <Pill tone={RISK_TONE[order.risk]}>{RISK_LABEL[order.risk]}</Pill>
                    </div>
                    <p className="mt-1 text-sm text-muted">
                      Prometida {formatDay(order.promised_on)} · estimada{" "}
                      <span className="font-medium text-danger">{formatDay(order.estimated_on)}</span>
                      {order.risk_reason ? ` · ${order.risk_reason}` : ""}
                    </p>
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
