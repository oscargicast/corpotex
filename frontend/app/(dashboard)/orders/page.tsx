"use client";

import { CheckCircle2, Plus } from "lucide-react";
import Link from "next/link";
import { Suspense, useState } from "react";
import useSWR from "swr";
import { ORDER_STATUSES, SearchBox, StatusChips, statusOptions, useListParams } from "@/components/list-filters";
import { useUser } from "@/components/require-auth";
import { SkeletonTable } from "@/components/skeleton";
import { Button, Pill, RISK_LABEL, RISK_TONE } from "@/components/ui";
import { ApiError, apiFetch, fetcher } from "@/lib/api";
import { formatDay } from "@/lib/format";
import { canCreateOrder } from "@/lib/orders";
import type { BreakDownResult, OrderListItem, Risk } from "@/lib/types";

const RISKS: (Risk | "")[] = ["", "in_danger", "at_risk", "ok"];

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
  const risk = params.get("risk") as Risk | "";
  const statuses = params.list("status");
  const q = params.get("q");
  // The API filters (B6.5): ?risk=&status=a,b&q=. The unfiltered list feeds the
  // chip counts and the registered count.
  const query = new URLSearchParams({ ...(risk && { risk }), ...(statuses.length && { status: statuses.join(",") }), ...(q && { q }) }).toString();
  const { data, error, mutate } = useSWR<OrderListItem[]>(`/api/orders/${query ? `?${query}` : ""}`, fetcher, { refreshInterval: 3000, keepPreviousData: true });
  const { data: all } = useSWR<OrderListItem[]>("/api/orders/", fetcher, { refreshInterval: 5000 });
  const options = statusOptions(all ?? [], ORDER_STATUSES);
  const filtered = data ?? [];
  const filtering = !!(risk || statuses.length || q);

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-2xl font-bold tracking-tight">Órdenes</h1>
        <div className="flex flex-wrap gap-2">
          {canCreateOrder(user) && (
            <Link href="/orders/new" className="inline-flex items-center justify-center gap-1.5 rounded-md bg-ink px-3 py-2 text-sm font-semibold text-white hover:bg-ink/90">
              <Plus size={16} /> Nueva orden
            </Link>
          )}
        </div>
      </div>

      {/* "Desglosar N registradas" (BreakDownPanel, below) is no longer mounted:
          orders are born broken down (ADR 0028). */}

      <div className="flex flex-wrap items-center gap-2">
        <div className="flex flex-wrap items-center gap-2" role="group" aria-label="Riesgo">
          {RISKS.map((value) => (
            <button
              key={value || "all"}
              type="button"
              aria-pressed={risk === value}
              onClick={() => params.set({ risk: value })}
              className={`rounded-full px-3 py-1 text-sm ring-1 ${risk === value ? "bg-ink text-white ring-ink" : "bg-surface ring-line hover:bg-canvas"}`}
            >
              {value ? RISK_LABEL[value] : "Todas"}
            </button>
          ))}
        </div>
        <SearchBox value={q} onChange={(value) => params.set({ q: value })} placeholder="Buscar por código (CP-2026-01…)" />
      </div>
      {options.length > 0 && <StatusChips options={options} selected={statuses} onChange={(next) => params.set({ status: next })} allLabel="Todos los estados" />}

      {error && !data && <p className="text-danger">No se pudieron cargar las órdenes.</p>}
      {!data && !error && <SkeletonTable rows={7} cols={7} />}
      {data && !filtered.length && (
        <div className="rounded-xl bg-surface p-6 text-center text-sm text-muted ring-1 ring-line">
          {filtering ? (
            <>
              <p>Ninguna orden coincide con {q ? `“${q}”` : "esos filtros"}.</p>
              <Button className="mt-3" onClick={() => params.set({ risk: null, status: null, q: null })}>
                Limpiar filtros
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
                {filtered.map((order) => (
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

// Break down every registered order at once (ADR 0025 A.6), Gerente and
// Producción: confirmation, then POST /api/orders/break-down/ and a summary
// ({broken_down: [codes], skipped: [{code, reason}]}).
function BreakDownPanel({ orders, open, onClose, onDone }: { orders: OrderListItem[]; open: boolean; onClose: () => void; onDone: () => void }) {
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<BreakDownResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function run() {
    setBusy(true);
    setError(null);
    try {
      const data = await apiFetch<BreakDownResult>("/api/orders/break-down/", { method: "POST", json: { order_ids: orders.map((o) => o.id) } });
      setResult(data);
      onClose();
      onDone();
    } catch (err) {
      setError(err instanceof ApiError ? ((err.body as { detail?: string } | null)?.detail ?? "No se pudo desglosar.") : "No se pudo desglosar.");
    } finally {
      setBusy(false);
    }
  }

  if (open) {
    return (
      <div className="flex flex-wrap items-center gap-2 rounded-lg bg-warning-soft px-3 py-2 text-sm text-warning">
        Se desglosan contra el inventario {orders.length === 1 ? "la orden" : `las ${orders.length} órdenes`} {orders.map((o) => o.code).join(", ")}. Después
        Producción confirma cada desglose.
        <Button kind="dark" className="py-1" busy={busy} onClick={run}>
          Desglosar ahora
        </Button>
        <Button className="py-1" disabled={busy} onClick={onClose}>
          Cancelar
        </Button>
        {error && <span className="w-full text-danger">{error}</span>}
      </div>
    );
  }
  if (!result) return null;
  return (
    <div className="rounded-lg bg-success-soft px-3 py-2 text-sm text-success" role="status">
      <p className="flex items-center gap-1.5 font-semibold">
        <CheckCircle2 size={16} />
        {result.broken_down.length === 1 ? "1 orden desglosada" : `${result.broken_down.length} órdenes desglosadas`}
        {result.broken_down.length > 0 && `: ${result.broken_down.join(", ")}`}
      </p>
      {result.skipped.length > 0 && (
        <ul className="mt-1 text-warning">
          {result.skipped.map((s) => (
            <li key={s.code}>
              {s.code}: {s.reason}
            </li>
          ))}
        </ul>
      )}
      <button type="button" onClick={() => setResult(null)} className="mt-1 text-xs underline">
        Cerrar
      </button>
    </div>
  );
}
