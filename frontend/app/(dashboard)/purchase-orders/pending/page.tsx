"use client";

import { ArrowLeft, CheckCircle2, ShoppingCart } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import useSWR from "swr";
import { RoleGate, useUser } from "@/components/require-auth";
import { SkeletonTable } from "@/components/skeleton";
import { Thumb } from "@/components/thumb";
import { Button, Card, Pill } from "@/components/ui";
import { ApiError, apiFetch, fetcher } from "@/lib/api";
import { daysBetween, formatDay, formatMoney, num } from "@/lib/format";
import type { GeneratedPurchaseOrder, GeneratedPurchaseOrders, PendingRequirement } from "@/lib/types";

const PENDING_URL = "/api/requirements/pending/";
const UNIT_LABEL: Record<string, string> = { unit: "u.", units: "u.", kg: "kg", m: "m", roll: "rollo", cone: "cono" };
const unitLabel = (unit: string) => UNIT_LABEL[unit] ?? unit;

export default function PendingPage() {
  return (
    <RoleGate roles={["manager", "production"]}>
      <Pending />
    </RoleGate>
  );
}

// Open material requirements of every open order, grouped by material (ADR
// 0025 A): one purchase order per material, with all the orders that need it.
// Producción and the Gerente generate; only the Gerente sees prices.
function Pending() {
  const user = useUser();
  const isManager = user.role === "manager";
  const { data, error, mutate } = useSWR<PendingRequirement[]>(PENDING_URL, fetcher, { refreshInterval: 5000 });
  // Supplier picked with "Cambiar", per material; the suggestion otherwise.
  const [overrides, setOverrides] = useState<Record<number, number>>({});
  const [busy, setBusy] = useState<number | "all" | null>(null);
  const [confirmAll, setConfirmAll] = useState(false);
  const [problem, setProblem] = useState<string | null>(null);
  const [generated, setGenerated] = useState<GeneratedPurchaseOrder[]>([]);
  const [decisionId, setDecisionId] = useState<number | null>(null);
  const [skipped, setSkipped] = useState<GeneratedPurchaseOrders["skipped"]>([]);
  const today = new Date().toISOString().slice(0, 10);

  async function generate(materialIds: number[] | null) {
    setBusy(materialIds ? materialIds[0] : "all");
    setProblem(null);
    const ids = materialIds ?? (data ?? []).map((row) => row.material.id);
    const supplier_overrides = Object.fromEntries(Object.entries(overrides).filter(([id]) => ids.includes(Number(id))));
    try {
      const result = await apiFetch<GeneratedPurchaseOrders>("/api/purchase-orders/generate/", {
        method: "POST",
        json: { ...(materialIds && { material_ids: materialIds }), ...(Object.keys(supplier_overrides).length && { supplier_overrides }) },
      });
      setGenerated((current) => [...(result.created ?? result.purchase_orders ?? []), ...current]);
      setDecisionId(result.decision_id ?? null);
      setSkipped(result.skipped ?? []);
      setConfirmAll(false);
      mutate();
    } catch (err) {
      const detail = err instanceof ApiError ? (err.body as { detail?: string } | null)?.detail : null;
      setProblem(detail ?? "No se pudo generar el pedido. Inténtalo de nuevo.");
    } finally {
      setBusy(null);
    }
  }

  const rows = data ?? [];
  const total = rows.reduce((sum, row) => sum + (num(row.total_to_order) ?? 0), 0);

  return (
    <div className="space-y-4">
      <Link href="/purchase-orders" className="inline-flex items-center gap-1 text-sm text-muted hover:text-ink">
        <ArrowLeft size={16} /> Pedidos
      </Link>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="flex items-center gap-2 text-2xl font-bold tracking-tight">
            <ShoppingCart size={24} /> Por pedir
          </h1>
          <p className="mt-1 text-sm text-muted">
            Insumos que piden las órdenes abiertas, juntados por material: un pedido por insumo con todas las órdenes que lo necesitan.
          </p>
        </div>
        {rows.length > 1 && !confirmAll && (
          <Button kind="primary" disabled={busy !== null} onClick={() => setConfirmAll(true)}>
            Generar todos ({rows.length})
          </Button>
        )}
      </div>

      {confirmAll && (
        <div className="flex flex-wrap items-center gap-2 rounded-lg bg-warning-soft px-3 py-2 text-sm text-warning">
          Se generan {rows.length} pedidos, uno por insumo ({Math.round(total)} unidades en total), con el proveedor sugerido o el que cambiaste. El Gerente los
          aprueba en el Monitor.
          <Button kind="dark" className="py-1" busy={busy === "all"} onClick={() => generate(null)}>
            Generar {rows.length} pedidos
          </Button>
          <Button className="py-1" disabled={busy !== null} onClick={() => setConfirmAll(false)}>
            Cancelar
          </Button>
        </div>
      )}

      {generated.length > 0 && (
        <div className="rounded-lg bg-success-soft px-3 py-2 text-sm text-success" role="status">
          <p className="flex items-center gap-1.5 font-semibold">
            <CheckCircle2 size={16} /> {generated.length === 1 ? "Pedido generado" : `${generated.length} pedidos generados`}
          </p>
          {decisionId && (
            <p className="mt-1">
              El Gerente aprueba la asignación en el{" "}
              <Link href="/" className="font-medium underline">
                Monitor
              </Link>
              .
            </p>
          )}
          <ul className="mt-1 space-y-0.5">
            {generated.map((po) => (
              <li key={po.id}>
                <Link href={`/purchase-orders/${po.id}`} className="font-medium underline">
                  {po.code}
                </Link>{" "}
                {po.material?.name || po.items?.[0]?.name ? ` · ${po.material?.name ?? po.items?.[0]?.name}` : ""} · {po.supplier.name}
                {po.orders.length > 0 && ` · para ${po.orders.map((o) => o.code).join(", ")}`}
              </li>
            ))}
          </ul>
        </div>
      )}

      {skipped.length > 0 && (
        <ul className="rounded-lg bg-warning-soft px-3 py-2 text-sm text-warning" role="alert">
          {skipped.map((s, i) => {
            const id = typeof s === "number" ? s : s.material_id;
            const name = rows.find((r) => r.material.id === id)?.material.name ?? (typeof s === "number" ? null : s.material) ?? `Material ${id ?? i + 1}`;
            const reason = typeof s === "number" ? "sin requerimientos abiertos" : (s.reason ?? "sin requerimientos abiertos");
            return (
              <li key={`${id ?? i}`}>
                {name}: {reason}
              </li>
            );
          })}
        </ul>
      )}

      {problem && (
        <p className="text-sm text-danger" role="alert">
          {problem}
        </p>
      )}

      {error && !data && <p className="text-danger">No se pudo cargar la lista.</p>}
      {!data && !error && <SkeletonTable rows={4} cols={isManager ? 6 : 5} />}
      {data && !rows.length && (
        <Card>
          <p className="text-sm text-muted">No hay insumos por pedir. Los requerimientos aparecen aquí al confirmar el desglose de una orden.</p>
        </Card>
      )}

      {rows.length > 0 && (
        <>
          {/* Table from md up, cards below. */}
          <Card className="hidden md:block">
            <table className="w-full text-sm">
              <thead className="text-left text-xs text-muted">
                <tr>
                  <th className="pb-2 pr-3 font-medium">Insumo</th>
                  <th className="whitespace-nowrap pb-2 pr-6 text-right font-medium">Por pedir</th>
                  <th className="pb-2 pr-3 font-medium">Órdenes</th>
                  <th className="pb-2 pr-3 font-medium">Proveedor</th>
                  {isManager && <th className="whitespace-nowrap pb-2 pr-3 text-right font-medium">Precio ref.</th>}
                  <th className="pb-2" />
                </tr>
              </thead>
              <tbody className="divide-y divide-line align-top">
                {rows.map((row) => (
                  <tr key={row.material.id}>
                    <td className="py-3 pr-3">
                      <div className="flex items-center gap-3">
                        <Thumb src={row.material.image} alt={row.material.name} size={40} />
                        <div>
                          <p className="font-medium">{row.material.name}</p>
                          <p className="text-xs text-muted">{row.material.sku}</p>
                        </div>
                      </div>
                    </td>
                    <td className="whitespace-nowrap py-3 pr-6 text-right tabular-nums">
                      <span className="font-semibold">{num(row.total_to_order)}</span> <span className="text-xs text-muted">{unitLabel(row.material.unit)}</span>
                      {row.due_on && <DueOn date={row.due_on} today={today} />}
                    </td>
                    <td className="py-3 pr-3">
                      <OrderChips row={row} />
                    </td>
                    <td className="py-3 pr-3">
                      <SupplierPicker row={row} value={overrides[row.material.id]} onChange={(id) => setOverrides((o) => ({ ...o, [row.material.id]: id }))} />
                    </td>
                    {isManager && (
                      <td className="py-3 pr-3 text-right tabular-nums">
                        <ReferencePrice row={row} supplierId={overrides[row.material.id]} />
                      </td>
                    )}
                    <td className="py-3 text-right">
                      <Button kind="dark" className="whitespace-nowrap py-1.5" busy={busy === row.material.id} disabled={busy !== null} onClick={() => generate([row.material.id])}>
                        Generar pedido
                      </Button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </Card>

          <ul className="space-y-3 md:hidden">
            {rows.map((row) => (
              <li key={row.material.id}>
                <Card>
                  <div className="flex items-center gap-3">
                    <Thumb src={row.material.image} alt={row.material.name} size={44} />
                    <div className="min-w-0 flex-1">
                      <p className="font-medium">{row.material.name}</p>
                      <p className="text-xs text-muted">{row.material.sku}</p>
                    </div>
                    <p className="text-right tabular-nums">
                      <span className="text-lg font-semibold">{num(row.total_to_order)}</span> <span className="text-xs text-muted">{unitLabel(row.material.unit)}</span>
                      {row.due_on && <DueOn date={row.due_on} today={today} />}
                    </p>
                  </div>
                  <div className="mt-3">
                    <OrderChips row={row} />
                  </div>
                  <div className="mt-3 flex flex-wrap items-center justify-between gap-2 text-sm">
                    <SupplierPicker row={row} value={overrides[row.material.id]} onChange={(id) => setOverrides((o) => ({ ...o, [row.material.id]: id }))} />
                    {isManager && (
                      <span className="tabular-nums">
                        <ReferencePrice row={row} supplierId={overrides[row.material.id]} />
                      </span>
                    )}
                  </div>
                  <Button kind="dark" className="mt-3 w-full" busy={busy === row.material.id} disabled={busy !== null} onClick={() => generate([row.material.id])}>
                    Generar pedido
                  </Button>
                </Card>
              </li>
            ))}
          </ul>
        </>
      )}
    </div>
  );
}

// The earliest date an order needs it; red inside a week.
function DueOn({ date, today }: { date: string; today: string }) {
  const days = daysBetween(today, date);
  return <span className={`block text-xs ${days <= 7 ? "text-danger" : "text-muted"}`}>para el {formatDay(date)}</span>;
}

function OrderChips({ row }: { row: PendingRequirement }) {
  return (
    <ul className="flex flex-wrap gap-1.5">
      {row.orders.map((order) => (
        <li key={order.id}>
          <Link href={`/orders/${order.id}`} className="inline-flex items-center gap-1 rounded-md bg-canvas px-2 py-1 text-xs hover:ring-1 hover:ring-line" title={order.customer_name}>
            <span className="font-medium text-accent">{order.code}</span>
            <span className="tabular-nums">{num(order.qty)}</span>
            {order.due_on && <span className="text-muted">· {formatDay(order.due_on)}</span>}
          </Link>
        </li>
      ))}
    </ul>
  );
}

// The matching's suggestion, with "Cambiar" among the candidates it ranked.
function SupplierPicker({ row, value, onChange }: { row: PendingRequirement; value: number | undefined; onChange: (id: number) => void }) {
  const [open, setOpen] = useState(false);
  const candidates = row.candidates ?? [];
  const chosenId = value ?? row.suggested_supplier?.id;
  const chosen = candidates.find((c) => c.supplier.id === chosenId)?.supplier ?? row.suggested_supplier;

  if (!chosen) return <span className="text-sm text-muted">Sin proveedor sugerido</span>;
  if (open && candidates.length > 1) {
    return (
      <select
        autoFocus
        value={chosenId}
        onChange={(e) => {
          onChange(Number(e.target.value));
          setOpen(false);
        }}
        onBlur={() => setOpen(false)}
        aria-label={`Proveedor para ${row.material.name}`}
        className="rounded-md bg-surface px-2 py-1 text-sm ring-1 ring-line"
      >
        {candidates.map((c) => (
          <option key={c.supplier.id} value={c.supplier.id}>
            {c.supplier.name}
            {c.score !== null && c.score !== undefined ? ` · ${Math.round((num(c.score) ?? 0) * 100)} pts` : ""}
          </option>
        ))}
      </select>
    );
  }
  return (
    <span className="inline-flex flex-wrap items-center gap-2 text-sm">
      <span className="font-medium">{chosen.name}</span>
      {value !== undefined && value !== row.suggested_supplier?.id && <Pill tone="warning">cambiado</Pill>}
      {candidates.length > 1 && (
        <button type="button" onClick={() => setOpen(true)} className="text-xs font-medium text-accent hover:underline">
          Cambiar
        </button>
      )}
    </span>
  );
}

// Reference price of the chosen supplier (the matching's rate), Gerente only.
function ReferencePrice({ row, supplierId }: { row: PendingRequirement; supplierId: number | undefined }) {
  const candidate = row.candidates?.find((c) => c.supplier.id === (supplierId ?? row.suggested_supplier?.id));
  const price =
    candidate?.unit_price != null
      ? { unit_price: candidate.unit_price, currency: candidate.currency ?? row.currency ?? "PEN" }
      : row.reference_price != null
        ? { unit_price: row.reference_price, currency: row.currency ?? "PEN" }
        : null;
  if (!price) return <span className="text-muted">—</span>;
  const unit = num(price.unit_price) ?? 0;
  const total = unit * (num(row.total_to_order) ?? 0);
  return (
    <span>
      {formatMoney(price.unit_price, price.currency)} <span className="text-xs text-muted">/ {unitLabel(row.material.unit)}</span>
      <span className="block text-xs text-muted">≈ {formatMoney(total, price.currency)}</span>
    </span>
  );
}
