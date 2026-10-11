"use client";

import { Button, Pill } from "@/components/ui";
import { formatDay } from "@/lib/format";
import type { Dispatch } from "./fleet-types";
import { addDays, dayOf, hhmm } from "./fleet-utils";

interface Props {
  from: string;
  to: string;
  today: string;
  rows: Dispatch[] | undefined;
  onRange: (from: string, to: string) => void;
}

// Entregadas (ADR 0026 §6): a date range with shortcuts and what went out.
export default function DeliveredPanel({ from, to, today, rows, onRange }: Props) {
  const shortcuts: [string, string, string][] = [
    ["Hoy", today, today],
    ["Ayer", addDays(today, -1), addDays(today, -1)],
    ["Últimos 7 días", addDays(today, -6), today],
  ];
  const late = (rows ?? []).filter((r) => !r.on_time).length;
  return (
    <div className="space-y-3">
      <div className="flex flex-wrap gap-2">
        {shortcuts.map(([label, a, b]) => (
          <Button key={label} kind={from === a && to === b ? "dark" : "ghost"} className="min-h-11" onClick={() => onRange(a, b)}>
            {label}
          </Button>
        ))}
      </div>
      <div className="flex flex-wrap items-center gap-2 text-sm">
        <label className="flex items-center gap-1">
          Desde
          <input type="date" value={from} max={to} onChange={(e) => e.target.value && onRange(e.target.value, to)} className="min-h-11 rounded-md bg-surface px-2 ring-1 ring-line" />
        </label>
        <label className="flex items-center gap-1">
          Hasta
          <input type="date" value={to} min={from} onChange={(e) => e.target.value && onRange(from, e.target.value)} className="min-h-11 rounded-md bg-surface px-2 ring-1 ring-line" />
        </label>
      </div>
      {rows && (
        <p className="text-sm text-muted tabular-nums">
          {rows.length} {rows.length === 1 ? "entrega" : "entregas"}
          {late ? ` · ${late} tarde` : rows.length ? " · todas a tiempo" : ""}
        </p>
      )}
      {!rows && <div className="h-24 animate-pulse rounded-xl bg-line" />}
      {rows?.length === 0 && <p className="text-sm text-muted">No hubo entregas en ese rango.</p>}
      <ul className="divide-y divide-line rounded-xl ring-1 ring-line">
        {rows?.map((row) => (
          <li key={row.order.id} className="flex items-start gap-3 px-3 py-2 text-sm">
            <span className="w-14 shrink-0 text-xs text-muted tabular-nums">
              {row.delivered_at ? (
                <>
                  {formatDay(dayOf(row.delivered_at))}
                  <br />
                  {hhmm(row.delivered_at)}
                </>
              ) : (
                "—"
              )}
            </span>
            <div className="min-w-0 flex-1">
              <p className="truncate font-medium">
                {row.order.code} · {row.order.customer_name}
              </p>
              <p className="flex items-center gap-1 text-xs text-muted">
                {row.vehicle ? (
                  <>
                    <span className="size-2 rounded-full" style={{ background: row.vehicle.color }} aria-hidden />
                    {row.vehicle.name}
                  </>
                ) : (
                  "Sin vehículo registrado"
                )}
                <span className="tabular-nums"> · {row.order.units} prendas</span>
              </p>
            </div>
            <Pill tone={row.on_time ? "success" : "danger"}>{row.on_time ? "A tiempo" : "Tarde"}</Pill>
          </li>
        ))}
      </ul>
    </div>
  );
}
