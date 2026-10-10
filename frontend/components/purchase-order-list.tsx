import Link from "next/link";
import { formatDay, formatMoney } from "@/lib/format";
import type { PurchaseOrderListItem } from "@/lib/types";
import { Pill, SEVERITY_TONE } from "./ui";

// Table on desktop, cards on mobile. Used by /purchase-orders and the order detail.
export function PurchaseOrderList({ items }: { items: PurchaseOrderListItem[] }) {
  if (!items.length) return <p className="text-sm text-muted">Sin pedidos.</p>;
  const showAmounts = items.some((po) => po.total_amount);

  return (
    <>
      <ul className="space-y-2 md:hidden">
        {items.map((po) => (
          <li key={po.id}>
            <Link href={`/purchase-orders/${po.id}`} className="block rounded-lg bg-surface p-3 ring-1 ring-line">
              <div className="flex items-center justify-between gap-2">
                <span className="font-semibold text-accent">{po.code}</span>
                <Status po={po} />
              </div>
              <p className="mt-1 text-sm">{po.supplier.name}</p>
              <Progress po={po} />
              <p className="mt-1 text-xs text-muted">
                {po.kind_display} · {dueLabel(po)}
              </p>
            </Link>
          </li>
        ))}
      </ul>

      <div className="hidden overflow-x-auto md:block">
        <table className="w-full text-sm">
          <thead className="text-left text-xs text-muted">
            <tr>
              <th className="pb-2 font-medium">Pedido</th>
              <th className="pb-2 font-medium">Proveedor</th>
              <th className="pb-2 font-medium">Estado</th>
              <th className="pb-2 font-medium">Avance</th>
              <th className="pb-2 font-medium">Fecha</th>
              {showAmounts && <th className="pb-2 text-right font-medium">Monto</th>}
            </tr>
          </thead>
          <tbody className="divide-y divide-line">
            {items.map((po) => (
              <tr key={po.id}>
                <td className="py-2.5 pr-3">
                  <Link href={`/purchase-orders/${po.id}`} className="font-semibold text-accent hover:underline">
                    {po.code}
                  </Link>
                  <span className="block text-xs text-muted">{po.kind_display}</span>
                </td>
                <td className="py-2.5 pr-3">
                  {po.supplier.name}
                  <span className="block text-xs text-muted">{po.orders.map((o) => o.code).join(", ")}</span>
                </td>
                <td className="py-2.5 pr-3">
                  <Status po={po} />
                </td>
                <td className="w-40 py-2.5 pr-3">
                  <Progress po={po} />
                </td>
                <td className="py-2.5 pr-3 text-xs">{dueLabel(po)}</td>
                {showAmounts && <td className="py-2.5 text-right tabular-nums">{formatMoney(po.total_amount, po.currency)}</td>}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
}

function Status({ po }: { po: PurchaseOrderListItem }) {
  return (
    <span className="flex flex-wrap items-center gap-1">
      {po.waiting_manager ? <Pill tone="warning">Esperando al Gerente</Pill> : <Pill>{po.status_display}</Pill>}
      {po.alert_severity && <Pill tone={SEVERITY_TONE[po.alert_severity]}>alerta</Pill>}
      {po.redistributed_from && <span className="text-xs text-muted">de {po.redistributed_from.code}</span>}
    </span>
  );
}

function Progress({ po }: { po: PurchaseOrderListItem }) {
  return (
    <span className="mt-1 flex items-center gap-2 text-xs tabular-nums">
      <span className="h-1.5 flex-1 overflow-hidden rounded-full bg-canvas">
        <span className="block h-full rounded-full bg-success" style={{ width: `${po.progress_pct}%` }} />
      </span>
      {po.units_done}/{po.total_units}
    </span>
  );
}

function dueLabel(po: PurchaseOrderListItem): string {
  if (po.committed_on) return `Acordado ${formatDay(po.committed_on)}`;
  if (po.internal_due_on) return `Límite ${formatDay(po.internal_due_on)}`;
  return "Sin fecha";
}
