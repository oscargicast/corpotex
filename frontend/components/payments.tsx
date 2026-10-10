"use client";

import { useState } from "react";
import { apiFetch } from "@/lib/api";
import { daysBetween, formatDay, formatMoney } from "@/lib/format";
import type { Currency, Payment } from "@/lib/types";
import { Button, Pill } from "./ui";

const METHODS = [
  { value: "yape", label: "Yape" },
  { value: "transfer", label: "Transferencia" },
  { value: "cash", label: "Efectivo" },
];

// 50 % advance and 50 % balance (Corpotex pays almost everything by Yape).
export function Payments({
  payments,
  currency,
  today,
  canPay,
  onChange,
}: {
  payments: Payment[];
  currency: Currency;
  today: string;
  canPay: boolean;
  onChange: () => void;
}) {
  if (!payments.length) return <p className="text-sm text-muted">Los pagos se crean cuando el proveedor confirma.</p>;
  return (
    <ul className="space-y-2">
      {payments.map((payment) => (
        <PaymentRow key={payment.id} payment={payment} currency={currency} today={today} canPay={canPay} onChange={onChange} />
      ))}
    </ul>
  );
}

function PaymentRow({
  payment,
  currency,
  today,
  canPay,
  onChange,
}: {
  payment: Payment;
  currency: Currency;
  today: string;
  canPay: boolean;
  onChange: () => void;
}) {
  const [open, setOpen] = useState(false);
  const [method, setMethod] = useState("yape");
  const [receipt, setReceipt] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const overdue = payment.status === "pending" && payment.due_on ? daysBetween(payment.due_on, today) : 0;

  async function pay() {
    setBusy(true);
    const form = new FormData();
    form.set("method", method);
    if (receipt) form.set("receipt", receipt);
    try {
      await apiFetch(`/api/payments/${payment.id}/pay/`, { method: "POST", body: form });
      setOpen(false);
      onChange();
    } finally {
      setBusy(false);
    }
  }

  return (
    <li className="rounded-lg p-3 ring-1 ring-line">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <p className="font-medium">
            {payment.kind_display} · <span className="tabular-nums">{formatMoney(payment.amount, currency)}</span>
          </p>
          <p className="text-xs text-muted">
            {payment.status === "paid"
              ? `Pagado ${formatDay(payment.paid_at)}${payment.method ? ` por ${METHODS.find((m) => m.value === payment.method)?.label ?? payment.method}` : ""}`
              : payment.due_on
                ? `Vence ${formatDay(payment.due_on)}`
                : "Vence con la última entrega"}
          </p>
        </div>
        <div className="flex items-center gap-2">
          {payment.status === "paid" ? (
            <Pill tone="success">Pagado</Pill>
          ) : overdue > 0 ? (
            <Pill tone="danger">
              Vencido hace {overdue} {overdue === 1 ? "día" : "días"}
            </Pill>
          ) : (
            <Pill>Pendiente</Pill>
          )}
          {canPay && payment.status === "pending" && !open && (
            <Button kind="dark" className="py-1" onClick={() => setOpen(true)}>
              Marcar pagado
            </Button>
          )}
        </div>
      </div>
      {open && (
        <div className="mt-3 flex flex-wrap items-end gap-2 border-t border-line pt-3">
          <label className="text-sm">
            <span className="block text-xs text-muted">Método</span>
            <select value={method} onChange={(e) => setMethod(e.target.value)} className="mt-1 rounded-md px-2 py-1.5 ring-1 ring-line">
              {METHODS.map((m) => (
                <option key={m.value} value={m.value}>
                  {m.label}
                </option>
              ))}
            </select>
          </label>
          <label className="min-w-0 flex-1 text-sm">
            <span className="block text-xs text-muted">Comprobante (opcional)</span>
            <input type="file" accept="image/*,application/pdf" onChange={(e) => setReceipt(e.target.files?.[0] ?? null)} className="mt-1 w-full text-xs" />
          </label>
          <Button kind="primary" disabled={busy} onClick={pay}>
            Confirmar pago
          </Button>
          <Button onClick={() => setOpen(false)}>Cancelar</Button>
        </div>
      )}
    </li>
  );
}
