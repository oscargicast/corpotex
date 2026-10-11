"use client";

import {
  ArrowRight,
  Bell,
  Bot,
  Check,
  CalendarClock,
  ChevronDown,
  Hourglass,
  type LucideIcon,
  MessageCircleReply,
  MessageSquareWarning,
  PenLine,
  PhoneOff,
  Scale,
  ShoppingCart,
  TriangleAlert,
  Unplug,
  Wallet,
  WifiOff,
} from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { apiFetch } from "@/lib/api";
import { formatDayTime } from "@/lib/format";
import type { Alert } from "@/lib/types";
import { Button, buttonClass } from "./ui";

// One line per alert (Oscar, 11/10): icon by kind, short title, the code and
// the one figure that matters, and the action; the full text on click.

const ICON: Record<string, LucideIcon> = {
  order_in_danger: TriangleAlert,
  delay: CalendarClock,
  stalled_purchase_order: Hourglass,
  no_response: MessageSquareWarning,
  payment_due: Wallet,
  instance_down: WifiOff,
  no_channel: PhoneOff,
  turn_failed: Bot,
  style_refresh_failed: PenLine,
  decision_pending: Scale,
  claude_disconnected: Unplug,
  purchase_suggested: ShoppingCart,
  follow_up_answered: MessageCircleReply,
};
const TONE = { critical: "text-danger", warning: "text-warning", info: "text-accent" } as const;
const BORDER = { critical: "border-l-danger", warning: "border-l-warning", info: "border-l-accent" } as const;

// The figure worth a glance, taken from the text: money, then days, then units.
function keyFigure(alert: Alert): string | null {
  const text = alert.text ?? "";
  const money = /(S\/|USD|US\$)\s?[\d.,]+/.exec(text)?.[0];
  const days = /(\d+)\s*d[ií]a/.exec(text)?.[1];
  const units = /(\d[\d.,]*)\s*(u\.|unidades)/.exec(text)?.[1];
  const parts = [
    money,
    days && `${alert.kind === "order_in_danger" || alert.kind === "delay" ? "+" : ""}${days} ${days === "1" ? "día" : "días"}`,
    !money && !days && units && `${units} u.`,
  ].filter(Boolean);
  return parts.length ? parts.join(" · ") : null;
}

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
  const [open, setOpen] = useState<number | null>(null);

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
      {alerts.map((alert) => {
        const Icon = ICON[alert.kind] ?? Bell;
        const code = alert.purchase_order?.code ?? alert.order?.code;
        const figure = keyFigure(alert);
        const expanded = open === alert.id;
        const target = alert.purchase_order
          ? { href: `/purchase-orders/${alert.purchase_order.id}`, label: "Ver pedido" }
          : alert.order
            ? { href: `/orders/${alert.order.id}`, label: "Ver orden" }
            : null;
        return (
          <li key={alert.id} className={`rounded-lg border-l-4 bg-surface ring-1 ring-line ${BORDER[alert.severity]}`}>
            <div className="flex flex-wrap items-center gap-x-2 gap-y-1 px-3 py-2">
              <button
                type="button"
                onClick={() => setOpen(expanded ? null : alert.id)}
                aria-expanded={expanded}
                className="flex min-h-11 min-w-0 basis-full items-center gap-2 rounded-md text-left text-sm sm:min-h-9 sm:flex-1 sm:basis-0"
              >
                <Icon size={16} className={`shrink-0 ${TONE[alert.severity]}`} aria-hidden />
                {/* The title always fits whole (Oscar, 11/10); the figure is what gives way. */}
                <span className="shrink-0 whitespace-nowrap font-semibold">{alert.kind_display}</span>
                {code && <span className="shrink-0 font-medium tabular-nums text-accent">{code}</span>}
                {figure && <span className={`min-w-0 truncate font-semibold tabular-nums ${TONE[alert.severity]}`}>{figure}</span>}
                <ChevronDown size={14} className={`ml-auto shrink-0 text-muted transition-transform duration-150 motion-reduce:transition-none ${expanded ? "rotate-180" : ""}`} aria-hidden />
                <span className="sr-only">{expanded ? "Ocultar detalle" : "Ver detalle"}</span>
              </button>
              {target && (
                <Link href={target.href} className={`${buttonClass("secondary", "sm")} ml-auto sm:ml-0`}>
                  <ArrowRight size={14} aria-hidden /> {target.label}
                </Link>
              )}
              {/* Icon only, the one exception to icon-and-text (Oscar, 11/10): a
                  square the height of "Ver orden", named for the tooltip and the reader. */}
              {canAcknowledge && (
                <Button size="sm" className={`w-11 px-0 sm:w-8 ${target ? "" : "ml-auto sm:ml-0"}`} aria-label="Reconocer" title="Reconocer" onClick={() => acknowledge(alert.id)} busy={busy === alert.id}>
                  {busy !== alert.id && <Check size={16} aria-hidden />}
                </Button>
              )}
            </div>
            {expanded && (
              <div className="magic-in border-t border-line px-3 py-2 text-sm">
                <p>{alert.text}</p>
                <p className="mt-1 flex flex-wrap gap-x-3 text-xs text-muted">
                  <span>{formatDayTime(alert.detected_at)}</span>
                  {alert.purchase_order?.supplier_name && <span>{alert.purchase_order.supplier_name}</span>}
                  {alert.order && alert.purchase_order && (
                    <Link href={`/orders/${alert.order.id}`} className="text-accent hover:underline">
                      Orden {alert.order.code}
                    </Link>
                  )}
                </p>
              </div>
            )}
          </li>
        );
      })}
    </ul>
  );
}
