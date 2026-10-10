"use client";

import Link from "next/link";
import { useState } from "react";
import useSWR from "swr";
import { useUser } from "@/components/require-auth";
import { SimulateOrder } from "@/components/simulate-order";
import { Pill, RISK_LABEL, RISK_TONE } from "@/components/ui";
import { fetcher } from "@/lib/api";
import { formatDay } from "@/lib/format";
import type { OrderListItem, Risk } from "@/lib/types";

const RISKS: (Risk | "")[] = ["", "in_danger", "at_risk", "ok"];

export default function OrdersPage() {
  const user = useUser();
  const [risk, setRisk] = useState<Risk | "">("");
  const [status, setStatus] = useState("");
  const query = new URLSearchParams({ ...(risk && { risk }), ...(status && { status }) }).toString();
  const { data, error } = useSWR<OrderListItem[]>(`/api/orders/${query ? `?${query}` : ""}`, fetcher, {
    refreshInterval: 3000,
  });
  const { data: all } = useSWR<OrderListItem[]>("/api/orders/", fetcher);
  const statuses = [...new Map((all ?? []).map((o) => [o.status, o.status_display])).entries()];

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-2xl font-bold tracking-tight">Órdenes</h1>
        {user.role !== "production" && <SimulateOrder />}
      </div>

      <div className="flex flex-wrap items-center gap-2">
        {RISKS.map((value) => (
          <button
            key={value || "all"}
            type="button"
            onClick={() => setRisk(value)}
            className={`rounded-full px-3 py-1 text-sm ring-1 ${risk === value ? "bg-ink text-white ring-ink" : "bg-surface ring-line"}`}
          >
            {value ? RISK_LABEL[value] : "Todas"}
          </button>
        ))}
        <select
          value={status}
          onChange={(e) => setStatus(e.target.value)}
          className="rounded-md bg-surface px-2 py-1.5 text-sm ring-1 ring-line"
          aria-label="Estado"
        >
          <option value="">Todos los estados</option>
          {statuses.map(([value, label]) => (
            <option key={value} value={value}>
              {label}
            </option>
          ))}
        </select>
      </div>

      {error && !data && <p className="text-danger">No se pudieron cargar las órdenes.</p>}
      {!data && !error && <div className="h-40 animate-pulse rounded-xl bg-line" />}
      {data && !data.length && <p className="text-sm text-muted">No hay órdenes con ese filtro.</p>}

      {data && data.length > 0 && (
        <>
          <ul className="space-y-2 md:hidden">
            {data.map((order) => (
              <li key={order.id}>
                <Link href={`/orders/${order.id}`} className="block rounded-lg bg-surface p-3 ring-1 ring-line">
                  <div className="flex items-center justify-between gap-2">
                    <span className="font-semibold text-accent">{order.code}</span>
                    <Pill tone={RISK_TONE[order.risk]}>{RISK_LABEL[order.risk]}</Pill>
                  </div>
                  <p className="mt-1 text-sm">
                    {order.customer.name} · {order.brand.name}
                  </p>
                  <p className="mt-1 text-xs text-muted">
                    {order.status_display} · {Number(order.total_units)} u. · prometida {formatDay(order.promised_on)}, estimada{" "}
                    {formatDay(order.estimated_on)}
                  </p>
                </Link>
              </li>
            ))}
          </ul>

          <div className="hidden overflow-x-auto rounded-xl bg-surface ring-1 ring-line md:block">
            <table className="w-full text-sm">
              <thead className="border-b border-line text-left text-xs text-muted">
                <tr>
                  <th className="px-4 py-3 font-medium">Orden</th>
                  <th className="px-4 py-3 font-medium">Cliente</th>
                  <th className="px-4 py-3 font-medium">Estado</th>
                  <th className="px-4 py-3 text-right font-medium">Unidades</th>
                  <th className="px-4 py-3 font-medium">Prometida</th>
                  <th className="px-4 py-3 font-medium">Estimada</th>
                  <th className="px-4 py-3 font-medium">Riesgo</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-line">
                {data.map((order) => (
                  <tr key={order.id} className="hover:bg-canvas">
                    <td className="px-4 py-3">
                      <Link href={`/orders/${order.id}`} className="font-semibold text-accent hover:underline">
                        {order.code}
                      </Link>
                    </td>
                    <td className="px-4 py-3">
                      {order.customer.name}
                      <span className="block text-xs text-muted">{order.brand.name}</span>
                    </td>
                    <td className="px-4 py-3">
                      {order.status_display}
                      {order.purchase_orders_summary?.waiting_manager ? (
                        <span className="block text-xs text-warning">{order.purchase_orders_summary.waiting_manager} esperando al Gerente</span>
                      ) : null}
                    </td>
                    <td className="px-4 py-3 text-right tabular-nums">{Number(order.total_units)}</td>
                    <td className="px-4 py-3">{formatDay(order.promised_on)}</td>
                    <td className={`px-4 py-3 ${order.slack_days !== null && order.slack_days < 0 ? "font-semibold text-danger" : ""}`}>
                      {formatDay(order.estimated_on)}
                    </td>
                    <td className="px-4 py-3">
                      <Pill tone={RISK_TONE[order.risk]}>{RISK_LABEL[order.risk]}</Pill>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </div>
  );
}
