"use client";

import { ArrowLeft } from "lucide-react";
import Link from "next/link";
import { useParams } from "next/navigation";
import useSWR from "swr";
import { ChatThread } from "@/components/chat-thread";
import { DecisionCard } from "@/components/decision-card";
import { Payments } from "@/components/payments";
import { ProgressForm } from "@/components/progress-form";
import { ProgressTimeline } from "@/components/progress-timeline";
import { useUser } from "@/components/require-auth";
import { StatusTimeline } from "@/components/status-timeline";
import { Thumb } from "@/components/thumb";
import { Card, Pill, SectionTitle } from "@/components/ui";
import { fetcher } from "@/lib/api";
import { formatDay, formatDayTime, formatMoney, num } from "@/lib/format";
import { useResolvedId } from "@/lib/resolve";
import type { ChatMessage, PurchaseOrderDetail } from "@/lib/types";
import { SkeletonDetail } from "@/components/skeleton";

export default function PurchaseOrderDetailPage() {
  const params = useParams<{ id: string }>();
  const user = useUser();
  const isManager = user.role === "manager";
  const { id, notFound } = useResolvedId("purchase-orders", decodeURIComponent(params.id));
  const { data: po, mutate } = useSWR<PurchaseOrderDetail>(id ? `/api/purchase-orders/${id}/` : null, fetcher, {
    refreshInterval: 3000,
  });
  // Supplier conversations hold sensitive data: only the Gerente sees them (rule of 10/10).
  const { data: chat } = useSWR<{ typing: boolean; messages: ChatMessage[] }>(
    isManager && po?.conversation_id ? `/api/conversations/${po.conversation_id}/messages/` : null,
    fetcher,
    { refreshInterval: 3000 },
  );

  if (notFound) return <p className="text-muted">No existe el pedido {decodeURIComponent(params.id)}.</p>;
  if (!po) return <SkeletonDetail />;

  const today = new Date().toISOString().slice(0, 10);
  const open = !["delivered", "cancelled", "cancelled_by_supplier", "rejected_by_supplier"].includes(po.status);

  return (
    <div className="space-y-5">
      <Link href="/purchase-orders" className="inline-flex items-center gap-1 text-sm text-muted hover:text-ink">
        <ArrowLeft size={16} /> Pedidos
      </Link>

      <header>
        <div className="flex flex-wrap items-center gap-2">
          <h1 className="text-2xl font-bold tracking-tight">{po.code}</h1>
          {po.waiting_manager ? <Pill tone="warning">Esperando al Gerente</Pill> : <Pill>{po.status_display}</Pill>}
          <Pill tone="info">{po.kind_display}</Pill>
        </div>
        <p className="mt-1 text-sm text-muted">
          {po.supplier.name} ·{" "}
          {po.orders.map((o, i) => (
            <span key={o.id}>
              {i > 0 && ", "}
              <Link href={`/orders/${o.id}`} className="text-accent hover:underline">
                {o.code}
              </Link>{" "}
              ({o.customer_name})
            </span>
          ))}
          {po.total_amount ? ` · ${formatMoney(po.total_amount, po.currency)}` : ""}
        </p>
        {isManager && (
          <p className="mt-1 text-sm">
            Asignado a <strong>{po.supplier.name}</strong>
            {po.changed_by_manager && <span className="text-warning"> (el Gerente cambió la sugerencia del matching)</span>} ·{" "}
            <Link href={`/suppliers/${po.supplier.id}?po=${po.id}`} className="font-medium text-accent hover:underline">
              ver evaluación →
            </Link>
          </p>
        )}
        {po.redistributed_from && (
          <p className="mt-1 text-sm">
            Nace de la redistribución de{" "}
            <Link href={`/purchase-orders/${po.redistributed_from.id}`} className="text-accent hover:underline">
              {po.redistributed_from.code}
            </Link>
          </p>
        )}
      </header>

      {isManager && po.pending_decision && (
        <DecisionCard decision={po.pending_decision} onResolved={() => mutate()} />
      )}

      <Card>
        <SectionTitle>Estado</SectionTitle>
        <StatusTimeline flow="purchase_order" status={po.status} statusDisplay={po.status_display} history={po.status_history} />
      </Card>

      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <Fact label="Avance" value={`${po.units_done} / ${Number(po.total_units)}`} />
        <Fact label="Límite interno" value={formatDay(po.internal_due_on)} />
        <Fact label="Acordado" value={formatDay(po.committed_on)} />
        <Fact label="Último avance" value={formatDayTime(po.last_progress_at)} />
      </div>

      {po.redistributed_into.length > 0 && (
        <Card>
          <SectionTitle>Se redistribuyó en</SectionTitle>
          <ul className="space-y-1 text-sm">
            {po.redistributed_into.map((child) => (
              <li key={child.id}>
                <Link href={`/purchase-orders/${child.id}`} className="font-medium text-accent hover:underline">
                  {child.code}
                </Link>{" "}
                · {child.supplier_name} · {num(child.quantity)} u. · {child.status_display}
              </li>
            ))}
          </ul>
        </Card>
      )}

      <div className="grid gap-5 xl:grid-cols-2">
        <Card>
          <SectionTitle>Ítems</SectionTitle>
          <ul className="space-y-3">
            {po.items.map((item) => (
              <li key={item.id} className="flex gap-3 text-sm">
                <Thumb src={item.image} alt={item.name} />
                <div>
                  <p className="font-medium">{item.name}</p>
                  <p className="text-xs text-muted tabular-nums">
                    {item.order_code} · {Number(item.quantity)} pedidas · {Number(item.qty_delivered)} entregadas
                    {item.unit_price ? ` · ${formatMoney(item.unit_price, po.currency)} c/u` : ""}
                  </p>
                </div>
              </li>
            ))}
          </ul>
          {po.terms && <p className="mt-3 rounded-md bg-canvas px-3 py-2 text-sm">Términos: {po.terms}</p>}
        </Card>

        <Card>
          <SectionTitle count={po.progress_reports.length}>Avances</SectionTitle>
          {po.progress_reports.length ? (
            <ProgressTimeline reports={po.progress_reports} total={Number(po.total_units)} />
          ) : (
            <p className="text-sm text-muted">Sin avances todavía.</p>
          )}
          {open && user.role !== "sales" && (
            <div className="mt-4 border-t border-line pt-4">
              <ProgressForm purchaseOrderId={po.id} current={po.units_done} total={Number(po.total_units)} onSaved={() => mutate()} />
            </div>
          )}
        </Card>

        {isManager && (
          <Card>
            <SectionTitle>Pagos</SectionTitle>
            <p className="mb-3 text-sm tabular-nums">
              Depositado <strong>{formatMoney(po.paid_amount, po.currency)}</strong> · saldo{" "}
              <strong>{formatMoney(po.pending_amount, po.currency)}</strong>
            </p>
            <Payments payments={po.payments} currency={po.currency} today={today} canPay onChange={() => mutate()} />
          </Card>
        )}

        {isManager && po.conversation_id && (
          <Card className="xl:col-span-2">
            <SectionTitle>Chat con el proveedor</SectionTitle>
            <ChatThread messages={chat?.messages ?? []} typing={chat?.typing} />
          </Card>
        )}
      </div>
    </div>
  );
}

function Fact({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-xl bg-surface p-3 ring-1 ring-line">
      <p className="text-xs text-muted">{label}</p>
      <p className="mt-0.5 font-semibold tabular-nums">{value}</p>
    </div>
  );
}
