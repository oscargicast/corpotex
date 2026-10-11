"use client";

import { ArrowLeft, Pencil, XCircle } from "lucide-react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useState } from "react";
import useSWR from "swr";
import { AlertList } from "@/components/alert-list";
import { CriticalPath } from "@/components/critical-path";
import { PurchaseOrderList } from "@/components/purchase-order-list";
import { RedistributionCard } from "@/components/redistribution-card";
import { useUser } from "@/components/require-auth";
import { StatusTimeline } from "@/components/status-timeline";
import { Thumb } from "@/components/thumb";
import { Button, Card, Pill, RISK_LABEL, RISK_TONE, SectionTitle } from "@/components/ui";
import { apiFetch, fetcher } from "@/lib/api";
import { formatDay, formatMoney } from "@/lib/format";
import { useResolvedId } from "@/lib/resolve";
import { CUSTOMIZATION, type OrderDetail } from "@/lib/types";
import { SkeletonDetail } from "@/components/skeleton";
import { canCancelOrder, canEditOrder } from "@/lib/orders";

export default function OrderDetailPage() {
  const params = useParams<{ id: string }>();
  const user = useUser();
  const { id, notFound } = useResolvedId("orders", decodeURIComponent(params.id));
  const { data: order, mutate } = useSWR<OrderDetail>(id ? `/api/orders/${id}/` : null, fetcher, { refreshInterval: 3000 });
  const [confirming, setConfirming] = useState(false);
  const [cancelling, setCancelling] = useState(false);
  const [cancelBusy, setCancelBusy] = useState(false);
  const [cancelError, setCancelError] = useState<string | null>(null);

  if (notFound) return <p className="text-muted">No existe la orden {decodeURIComponent(params.id)}.</p>;
  if (!order) return <SkeletonDetail />;

  const canConfirm = order.status === "broken_down" && user.role !== "sales";

  async function cancelOrder() {
    setCancelBusy(true);
    setCancelError(null);
    try {
      await apiFetch(`/api/orders/${order!.id}/cancel/`, { method: "POST" });
      setCancelling(false);
      mutate();
    } catch {
      setCancelError("No se pudo cancelar. Inténtalo de nuevo.");
    } finally {
      setCancelBusy(false);
    }
  }

  async function confirm() {
    setConfirming(true);
    try {
      await mutate(apiFetch<OrderDetail>(`/api/orders/${order!.id}/confirm/`, { method: "POST" }), { revalidate: true });
    } finally {
      setConfirming(false);
    }
  }

  return (
    <div className="space-y-5">
      <Link href="/orders" className="inline-flex items-center gap-1 text-sm text-muted hover:text-ink">
        <ArrowLeft size={16} /> Órdenes
      </Link>

      <header className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="flex flex-wrap items-center gap-2">
            <h1 className="text-2xl font-bold tracking-tight">{order.code}</h1>
            <Pill tone={RISK_TONE[order.risk]}>{RISK_LABEL[order.risk]}</Pill>
            <Pill>{order.status_display}</Pill>
          </div>
          <p className="mt-1 text-sm text-muted">
            {order.customer.name} · {order.brand.name} · {Number(order.total_units)} unidades
            {order.total_amount ? ` · ${formatMoney(order.total_amount)}` : ""}
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          {canEditOrder(user, order) && (
            <Link href={`/orders/${order.id}/edit`} className="inline-flex items-center justify-center gap-1.5 rounded-md px-3 py-2 text-sm font-semibold text-ink ring-1 ring-line hover:bg-canvas">
              <Pencil size={16} /> Editar
            </Link>
          )}
          {canCancelOrder(user, order) && !cancelling && (
            <Button onClick={() => setCancelling(true)}>
              <XCircle size={16} /> Cancelar orden
            </Button>
          )}
          {canConfirm && (
            <Button kind="primary" onClick={confirm} busy={confirming}>
              {confirming ? "Confirmando…" : "Confirmar desglose"}
            </Button>
          )}
        </div>
      </header>

      {cancelling && (
        <div className="flex flex-wrap items-center gap-2 rounded-lg bg-danger-soft px-3 py-2 text-sm text-danger" role="alert">
          Se cancela la orden {order.code} y sus pedidos pendientes. No se puede deshacer.
          <Button kind="danger" className="py-1" busy={cancelBusy} onClick={cancelOrder}>
            Cancelar orden
          </Button>
          <Button className="py-1" disabled={cancelBusy} onClick={() => setCancelling(false)}>
            Volver
          </Button>
          {cancelError && <span className="w-full">{cancelError}</span>}
        </div>
      )}

      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <Fact label="Emitida" value={formatDay(order.issued_on)} />
        <Fact label="Prometida al cliente" value={formatDay(order.promised_on)} />
        <Fact
          label="Estimada"
          value={formatDay(order.estimated_on)}
          tone={order.slack_days !== null && order.slack_days < 0 ? "text-danger" : undefined}
        />
        <Fact
          label="Holgura"
          value={order.slack_days === null ? "—" : `${order.slack_days} días`}
          tone={order.slack_days !== null && order.slack_days < 0 ? "text-danger" : undefined}
        />
      </div>
      {order.risk_reason && <p className="rounded-lg bg-warning-soft px-4 py-2 text-sm text-warning">{order.risk_reason}</p>}

      <Card>
        <SectionTitle>Estado</SectionTitle>
        <StatusTimeline flow="order" status={order.status} statusDisplay={order.status_display} history={order.status_history} />
      </Card>

      <Card>
        <SectionTitle>Ruta crítica</SectionTitle>
        <CriticalPath steps={order.critical_path} promisedOn={order.promised_on} />
      </Card>

      {order.redistributions.map((decision) => (
        <RedistributionCard key={decision.id} decision={decision} />
      ))}

      <div className="grid gap-5 xl:grid-cols-2">
        <Card>
          <SectionTitle count={order.items.length}>Prendas</SectionTitle>
          <ul className="space-y-3">
            {order.items.map((item) => (
              <li key={item.id} className="flex gap-3">
                <Thumb src={item.product.image} alt={item.product.name} size={56} />
                <div className="min-w-0 text-sm">
                  <p className="font-semibold">
                    {item.quantity} × {item.product.name}
                  </p>
                  <p className="text-muted">
                    {[item.color, CUSTOMIZATION[item.customization] ?? item.customization, item.unit_price && `${formatMoney(item.unit_price)} c/u`]
                      .filter(Boolean)
                      .join(" · ")}
                  </p>
                  <p className="mt-1 flex flex-wrap gap-1">
                    {Object.entries(item.sizes).map(([size, qty]) => (
                      <span key={size} className="rounded bg-canvas px-1.5 text-xs tabular-nums">
                        {size}: {qty}
                      </span>
                    ))}
                  </p>
                </div>
              </li>
            ))}
          </ul>
        </Card>

        {order.requirements.length > 0 && (
          <Card>
            <SectionTitle count={order.requirements.length}>Desglose contra inventario</SectionTitle>
            <ul className="divide-y divide-line">
              {order.requirements.map((req) => {
                const thing = req.material ?? req.product;
                return (
                  <li key={req.id} className="flex gap-3 py-2.5 first:pt-0 last:pb-0">
                    <Thumb src={thing?.image} alt={thing?.name ?? ""} />
                    <div className="min-w-0 flex-1 text-sm">
                      <div className="flex flex-wrap items-center justify-between gap-2">
                        <p className="font-medium">{thing?.name}</p>
                        <Pill tone={req.status === "pending" ? "warning" : "neutral"}>{req.status_display}</Pill>
                      </div>
                      <p className="text-xs text-muted tabular-nums">
                        {req.kind_display} · necesita {Number(req.qty_needed)} {req.material?.unit ?? "u."} · stock{" "}
                        {Number(req.qty_from_stock)} · a pedir <strong className="text-ink">{Number(req.qty_to_order)}</strong>
                      </p>
                      {req.purchase_orders.length > 0 && (
                        <p className="mt-1 flex flex-wrap gap-x-3 text-xs">
                          {req.purchase_orders.map((po) => (
                            <Link key={po.id} href={`/purchase-orders/${po.id}`} className="text-accent hover:underline">
                              {po.code} · {po.supplier_name} · {Number(po.quantity)}
                            </Link>
                          ))}
                        </p>
                      )}
                    </div>
                  </li>
                );
              })}
            </ul>
          </Card>
        )}
      </div>

      <Card>
        <SectionTitle count={order.purchase_orders.length}>Pedidos a proveedores y talleres</SectionTitle>
        <PurchaseOrderList items={order.purchase_orders} />
      </Card>

      {order.alerts.length > 0 && (
        <Card>
          <SectionTitle count={order.alerts.length}>Alertas</SectionTitle>
          <AlertList alerts={order.alerts} canAcknowledge={user.role === "manager"} onChange={() => mutate()} />
        </Card>
      )}
    </div>
  );
}

function Fact({ label, value, tone }: { label: string; value: string; tone?: string }) {
  return (
    <div className="rounded-xl bg-surface p-3 ring-1 ring-line">
      <p className="text-xs text-muted">{label}</p>
      <p className={`mt-0.5 font-semibold tabular-nums ${tone ?? ""}`}>{value}</p>
    </div>
  );
}
