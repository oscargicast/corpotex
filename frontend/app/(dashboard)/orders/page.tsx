"use client";

import { FilterX, Plus } from "lucide-react";
import Link from "next/link";
import { Suspense } from "react";
import useSWR from "swr";
import { FilterBar } from "@/components/filter-bar";
import { matchesCode, useListParams } from "@/components/list-filters";
import { useUser } from "@/components/require-auth";
import { SkeletonTable } from "@/components/skeleton";
import { Button, buttonClass, CARD_HOVER, Pill, RISK_LABEL, RISK_TONE, ROW_HOVER } from "@/components/ui";
import { orderStatusLabel } from "@/lib/order-status";
import { fetcher } from "@/lib/api";
import { formatDay } from "@/lib/format";
import { canCreateOrder } from "@/lib/orders";
import type { OrderListItem, Role } from "@/lib/types";

// One list per role (Oscar, 11/10): Comercial follows its orders until
// Producción confirms and then until the supplier answers; Producción opens on
// what it has to review; the Gerente sees every cut. The chips and the search
// filter the loaded list in the browser; the choice lives in the URL.
type View = "all" | "to_confirm" | "confirmed" | "awaiting" | "danger";
const BEFORE_CONFIRM = ["registered", "broken_down"];
const VIEWS: Record<Role, { key: View; label: string }[]> = {
  sales: [
    { key: "all", label: "Todas" },
    { key: "to_confirm", label: "Por confirmar" },
    { key: "confirmed", label: "Confirmadas" },
    { key: "awaiting", label: "Avance pedido" },
  ],
  production: [
    { key: "to_confirm", label: "Por revisar" },
    { key: "confirmed", label: "Confirmadas" },
    { key: "all", label: "Todas" },
  ],
  manager: [
    { key: "all", label: "Todas" },
    { key: "to_confirm", label: "Por confirmar" },
    { key: "confirmed", label: "Confirmadas" },
    { key: "awaiting", label: "Avance pedido" },
    { key: "danger", label: "En peligro" },
  ],
};
const TESTS: Record<View, (order: OrderListItem) => boolean> = {
  all: () => true,
  to_confirm: (o) => BEFORE_CONFIRM.includes(o.status),
  confirmed: (o) => !BEFORE_CONFIRM.includes(o.status) && o.status !== "cancelled",
  awaiting: (o) => !!o.awaiting_reply, // undefined until the API sends it
  danger: (o) => o.risk === "in_danger",
};

export default function OrdersPage() {
  return (
    <Suspense>
      <Orders />
    </Suspense>
  );
}

function Orders() {
  const user = useUser();
  const params = useListParams();
  const views = VIEWS[user.role];
  const view = (views.some((v) => v.key === params.get("view")) ? params.get("view") : views[0].key) as View;
  const q = params.get("q");
  const { data, error } = useSWR<OrderListItem[]>("/api/orders/", fetcher, { refreshInterval: 3000 });
  const all = data ?? [];
  const filtered = all.filter((o) => TESTS[view](o) && matchesCode(q, o.code, o.customer.name));
  const filtering = view !== views[0].key || !!q;
  const statusLabel = (o: OrderListItem) => orderStatusLabel(o.status, o.status_display, user.role);

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-2xl font-bold tracking-tight">Órdenes</h1>
        <div className="flex flex-wrap gap-2">
          {canCreateOrder(user) && (
            <Link href="/orders/new" className={buttonClass("primary")}>
              <Plus size={16} aria-hidden /> Nueva orden
            </Link>
          )}
        </div>
      </div>

      <FilterBar
        search={{ value: q, onChange: (value) => params.set({ q: value }), placeholder: "Buscar por código o cliente" }}
        chips={{
          label: "Órdenes",
          value: view,
          onChange: (next) => params.set({ view: next === views[0].key ? null : next }),
          options: views.map((v) => ({ key: v.key, label: v.label, count: all.filter((o) => TESTS[v.key](o)).length })),
        }}
      />

      {error && !data && <p className="text-danger">No se pudieron cargar las órdenes.</p>}
      {!data && !error && <SkeletonTable rows={7} cols={7} />}
      {data && !filtered.length && (
        <div className="rounded-xl bg-surface p-6 text-center text-sm text-muted ring-1 ring-line">
          {filtering ? (
            <>
              <p>Ninguna orden coincide con {q ? `“${q}”` : "ese filtro"}.</p>
              <Button className="mt-3" onClick={() => params.set({ view: null, q: null })}>
                <FilterX size={16} aria-hidden /> Limpiar filtros
              </Button>
            </>
          ) : (
            <p>Todavía no hay órdenes.</p>
          )}
        </div>
      )}

      {filtered.length > 0 && (
        <>
          <ul className="space-y-2 md:hidden">
            {filtered.map((order) => (
              <li key={order.id}>
                <Link href={`/orders/${order.id}`} className={`block rounded-lg bg-surface p-3 ring-1 ring-line ${CARD_HOVER}`}>
                  <div className="flex items-center justify-between gap-2">
                    <span className="font-semibold text-accent">{order.code}</span>
                    <Pill tone={RISK_TONE[order.risk]}>{RISK_LABEL[order.risk]}</Pill>
                  </div>
                  <p className="mt-1 text-sm">
                    {order.customer.name} · {order.brand.name}
                  </p>
                  <p className="mt-1 text-xs text-muted">
                    {statusLabel(order)}
                    {order.awaiting_reply && " · esperando respuesta del proveedor"} · {Number(order.total_units)} u. · entrega {formatDay(order.promised_on)}, estimada{" "}
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
                  <th className="px-4 py-3 font-medium">Fecha de entrega</th>
                  <th className="px-4 py-3 font-medium">Estimada</th>
                  <th className="px-4 py-3 font-medium">Riesgo</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-line">
                {filtered.map((order) => (
                  <tr key={order.id} className={ROW_HOVER}>
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
                      {statusLabel(order)}
                      {order.awaiting_reply ? (
                        <span className="block text-xs text-warning">esperando respuesta del proveedor</span>
                      ) : order.purchase_orders_summary?.waiting_manager ? (
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
