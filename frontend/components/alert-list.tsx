"use client";

import Link from "next/link";
import { useState } from "react";
import { apiFetch } from "@/lib/api";
import { formatDayTime } from "@/lib/format";
import type { Alert } from "@/lib/types";
import { Button, Pill, SEVERITY_TONE } from "./ui";

const BORDER = { critical: "border-l-danger", warning: "border-l-warning", info: "border-l-accent" } as const;

export function AlertList({
  alerts,
  canAcknowledge,
  onChange,
}: {
  alerts: Alert[];
  canAcknowledge: boolean;
  onChange: () => void;
}) {
  const [busy, setBusy] = useState<number | null>(null);

  async function acknowledge(id: number) {
    setBusy(id);
    try {
      await apiFetch(`/api/alerts/${id}/acknowledge/`, { method: "POST" });
      onChange();
    } finally {
      setBusy(null);
    }
  }

  if (!alerts.length) return <p className="text-sm text-muted">Sin alertas abiertas.</p>;

  return (
    <ul className="space-y-2">
      {alerts.map((alert) => (
        <li key={alert.id} className={`rounded-lg border-l-4 bg-surface p-3 ring-1 ring-line ${BORDER[alert.severity]}`}>
          <div className="flex flex-wrap items-center gap-2">
            <Pill tone={SEVERITY_TONE[alert.severity]}>{alert.kind_display}</Pill>
            <span className="text-xs text-muted">{formatDayTime(alert.detected_at)}</span>
          </div>
          <p className="mt-1.5 text-sm">{alert.text}</p>
          <div className="mt-2 flex flex-wrap items-center gap-3 text-sm">
            {alert.order && (
              <Link href={`/orders/${alert.order.id}`} className="font-medium text-accent hover:underline">
                Ver orden {alert.order.code}
              </Link>
            )}
            {alert.purchase_order && (
              <Link href={`/purchase-orders/${alert.purchase_order.id}`} className="font-medium text-accent hover:underline">
                Ver pedido {alert.purchase_order.code}
              </Link>
            )}
            {canAcknowledge && (
              <Button className="ml-auto py-1" onClick={() => acknowledge(alert.id)} disabled={busy === alert.id}>
                Reconocer
              </Button>
            )}
          </div>
        </li>
      ))}
    </ul>
  );
}
