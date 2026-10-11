"use client";

import { ChevronDown, CircleCheck, Clock, PackageX, Search, ShoppingCart, TriangleAlert, Truck, type LucideIcon } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import useSWR from "swr";
import { RoleGate } from "@/components/require-auth";
import { SkeletonLines, SkeletonTable } from "@/components/skeleton";
import { Thumb } from "@/components/thumb";
import { Pill, type Tone } from "@/components/ui";
import { fetcher } from "@/lib/api";
import { num } from "@/lib/format";
import type { Material, MaterialDetail, PendingRequirement } from "@/lib/types";

const KIND_LABEL: Record<Material["kind"], string> = {
  fabric: "Tela",
  button: "Botón",
  zipper: "Cierre",
  collar_cuff: "Cuello y puño",
  other: "Otro",
};
const UNIT_LABEL: Record<Material["unit"], string> = { m: "m", kg: "kg", unit: "u." };
// Fallback while the API does not send status_display.
const REQ_STATUS: Record<string, string> = { pending: "Pendiente", covered: "Cubierto con stock", ordered: "Pedido" };

const qty = (v: string | number | null | undefined) => (num(v) ?? 0).toLocaleString("es-PE", { maximumFractionDigits: 2 }).replace(/^-/, "−");

type StatusKey = "to_order" | "awaiting_approval" | "incoming" | "out" | "low" | "ok";
interface Status {
  key: StatusKey;
  tone: Tone;
  icon: LucideIcon;
  label: string;
  rank: number; // sort group
}

// One state per material, always icon + text (never color alone), evaluated in
// this order: to order, in transit, awaiting the Gerente's approval, out of
// stock, low (less than 10 % free), OK.
function statusOf(m: Material, toOrder: number): Status {
  const available = num(m.available) ?? 0;
  const unit = UNIT_LABEL[m.unit];
  if (toOrder > 0) return { key: "to_order", tone: "danger", icon: ShoppingCart, label: `Por pedir · ${qty(toOrder)} ${unit}`, rank: 0 };
  const incoming = m.incoming ?? [];
  if (available <= 0) {
    const live = incoming.filter((po) => po.status !== "suggested");
    if (live.length) return { key: "incoming", tone: "info", icon: Truck, label: `En camino · ${live.length === 1 ? live[0].code : `${live.length} pedidos`}`, rank: 1 };
    if (incoming.length)
      return { key: "awaiting_approval", tone: "warning", icon: Clock, label: `Por aprobar · ${incoming.length === 1 ? incoming[0].code : `${incoming.length} pedidos`}`, rank: 1 };
    return { key: "out", tone: "neutral", icon: PackageX, label: "Agotado", rank: 2 };
  }
  if (available < (num(m.stock) ?? 0) * 0.1) return { key: "low", tone: "warning", icon: TriangleAlert, label: "Bajo", rank: 2 };
  return { key: "ok", tone: "success", icon: CircleCheck, label: "OK", rank: 3 };
}

function StatusPill({ status }: { status: Status }) {
  const Icon = status.icon;
  return (
    <Pill tone={status.tone}>
      <Icon size={13} className="mr-1 shrink-0" aria-hidden />
      {status.label}
    </Pill>
  );
}

const pendingHref = (m: Material) => `/purchase-orders/pending?material=${m.id}`;

export default function InventoryPage() {
  return (
    <RoleGate roles={["manager", "production"]}>
      <Inventory />
    </RoleGate>
  );
}

function Inventory() {
  const { data, error } = useSWR<Material[]>("/api/materials/", fetcher, { refreshInterval: 5000 });
  // Until /api/materials/ sends to_order, the "Por pedir" list gives the same number.
  const needsFallback = !!data && data.some((m) => m.to_order === undefined);
  const { data: pending } = useSWR<PendingRequirement[]>(needsFallback ? "/api/requirements/pending/" : null, fetcher, { refreshInterval: 5000 });
  const [kind, setKind] = useState("");
  const [onlyToOrder, setOnlyToOrder] = useState(false);
  const [query, setQuery] = useState("");
  const [open, setOpen] = useState<number | null>(null);

  const pendingByMaterial = new Map((pending ?? []).map((row) => [row.material.id, num(row.total_to_order) ?? 0]));
  const toOrderOf = (m: Material) => (m.to_order !== undefined ? (num(m.to_order) ?? 0) : (pendingByMaterial.get(m.id) ?? 0));
  const all = (data ?? []).map((m) => ({ m, status: statusOf(m, toOrderOf(m)) }));

  const q = query.trim().toLowerCase();
  const rows = all
    .filter(({ m, status }) => (!kind || m.kind === kind) && (!onlyToOrder || status.key === "to_order") && (!q || m.sku.toLowerCase().includes(q) || m.name.toLowerCase().includes(q)))
    // To order first, then awaiting/in transit, out of stock and low, OK last; least available first in each group.
    .sort((a, b) => a.status.rank - b.status.rank || (num(a.m.available) ?? 0) - (num(b.m.available) ?? 0));
  const toOrderCount = all.filter(({ status }) => status.key === "to_order").length;
  const inTransitCount = all.filter(({ m }) => (m.incoming ?? []).some((po) => po.status !== "suggested")).length;

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h1 className="text-2xl font-bold tracking-tight">Inventario</h1>
        <div className="flex flex-wrap items-center gap-2">
          {toOrderCount > 0 && (
            <Link href="/purchase-orders/pending" className="rounded-full hover:opacity-80">
              <Pill tone="danger">
                <ShoppingCart size={13} className="mr-1" aria-hidden />
                {toOrderCount} por pedir
              </Pill>
            </Link>
          )}
          {inTransitCount > 0 && (
            <Pill tone="info">
              <Truck size={13} className="mr-1" aria-hidden />
              {inTransitCount} en camino
            </Pill>
          )}
        </div>
      </div>

      <div className="flex flex-wrap items-center gap-2">
        <label className="relative">
          <Search size={16} className="pointer-events-none absolute left-2.5 top-1/2 -translate-y-1/2 text-muted" />
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="SKU o nombre"
            aria-label="Buscar insumo"
            className="w-56 rounded-md bg-surface py-1.5 pl-8 pr-3 text-sm ring-1 ring-line"
          />
        </label>
        <select value={kind} onChange={(e) => setKind(e.target.value)} aria-label="Tipo" className="rounded-md bg-surface px-2 py-1.5 text-sm ring-1 ring-line">
          <option value="">Todos los tipos</option>
          {Object.entries(KIND_LABEL).map(([value, label]) => (
            <option key={value} value={value}>
              {label}
            </option>
          ))}
        </select>
        <button
          type="button"
          aria-pressed={onlyToOrder}
          onClick={() => setOnlyToOrder((v) => !v)}
          className={`inline-flex items-center gap-1.5 rounded-full px-3 py-1 text-sm ring-1 ${onlyToOrder ? "bg-ink text-white ring-ink" : "bg-surface ring-line hover:bg-canvas"}`}
        >
          <ShoppingCart size={14} aria-hidden /> Solo por pedir
        </button>
      </div>

      {error && !data && <p className="text-danger">No se pudo cargar el inventario.</p>}
      {!data && !error && <SkeletonTable rows={8} cols={6} />}
      {data && !rows.length && <p className="text-sm text-muted">Ningún insumo coincide.</p>}

      {rows.length > 0 && (
        <>
          <ul className="space-y-2 md:hidden">
            {rows.map(({ m, status }) => {
              const short = (num(m.available) ?? 0) <= 0;
              const toOrder = status.key === "to_order";
              return (
                <li key={m.id} className={`rounded-lg bg-surface ring-1 ring-line ${toOrder ? "shadow-[inset_3px_0_0_var(--color-danger)]" : ""}`}>
                  <button type="button" onClick={() => setOpen(open === m.id ? null : m.id)} aria-expanded={open === m.id} className="flex w-full items-start gap-3 p-3 text-left">
                    <Thumb src={m.image} alt={m.name} />
                    <span className="min-w-0 flex-1">
                      <span className="block truncate font-semibold">{m.name}</span>
                      <span className="block text-xs text-muted">
                        {m.sku} · {m.kind_display ?? KIND_LABEL[m.kind]}
                      </span>
                      <span className="mt-1 block text-xs tabular-nums">
                        stock {qty(m.stock)} · reservado {qty(m.committed)} ·{" "}
                        <strong className={short ? "text-danger" : ""}>libre {qty(m.available)}</strong> {UNIT_LABEL[m.unit]}
                      </span>
                      <span className="mt-2 block">
                        <StatusPill status={status} />
                      </span>
                    </span>
                    <ChevronDown size={16} className={`mt-1 shrink-0 text-muted transition-transform ${open === m.id ? "rotate-180" : ""}`} aria-hidden />
                  </button>
                  {/* Outside the row's button: a link cannot live inside it. */}
                  {toOrder && (
                    <div className="px-3 pb-3">
                      <Link
                        href={pendingHref(m)}
                        className="flex h-11 w-full items-center justify-center gap-2 rounded-md bg-brand text-sm font-semibold text-ink hover:bg-brand-hover"
                      >
                        <ShoppingCart size={16} aria-hidden /> Generar pedido
                      </Link>
                    </div>
                  )}
                  {open === m.id && <Details material={m} />}
                </li>
              );
            })}
          </ul>

          <div className="hidden overflow-x-auto rounded-xl bg-surface ring-1 ring-line md:block">
            <table className="w-full text-sm">
              <thead className="border-b border-line text-left text-xs text-muted">
                <tr>
                  <th className="px-4 py-3 font-medium">Insumo</th>
                  <th className="px-4 py-3 font-medium">Tipo</th>
                  <th className="px-4 py-3 text-right font-medium">Stock</th>
                  <th className="px-4 py-3 text-right font-medium">Reservado</th>
                  <th className="px-4 py-3 text-right font-medium">Disponible</th>
                  <th className="px-4 py-3 font-medium">Estado</th>
                  <th className="w-10 px-2 py-3" />
                </tr>
              </thead>
              <tbody className="divide-y divide-line">
                {rows.map(({ m, status }) => {
                  const isOpen = open === m.id;
                  const short = (num(m.available) ?? 0) <= 0;
                  const toOrder = status.key === "to_order";
                  return (
                    <RowGroup key={m.id}>
                      <tr onClick={() => setOpen(isOpen ? null : m.id)} className="cursor-pointer hover:bg-canvas" aria-expanded={isOpen}>
                        <td className={`px-4 py-2.5 ${toOrder ? "shadow-[inset_3px_0_0_var(--color-danger)]" : ""}`}>
                          <span className="flex items-center gap-3">
                            <Thumb src={m.image} alt={m.name} />
                            <span>
                              <span className="block font-semibold">{m.name}</span>
                              <span className="block font-mono text-xs text-muted">{m.sku}</span>
                            </span>
                          </span>
                        </td>
                        <td className="px-4 py-2.5">{m.kind_display ?? KIND_LABEL[m.kind]}</td>
                        <td className="px-4 py-2.5 text-right tabular-nums">
                          {qty(m.stock)} {UNIT_LABEL[m.unit]}
                        </td>
                        <td className="px-4 py-2.5 text-right tabular-nums">{qty(m.committed)}</td>
                        <td className={`px-4 py-2.5 text-right tabular-nums ${short ? "font-bold text-danger" : ""}`}>{qty(m.available)}</td>
                        <td className="px-4 py-2.5">
                          <span className="flex flex-wrap items-center gap-2">
                            <StatusPill status={status} />
                            {toOrder && (
                              <Link
                                href={pendingHref(m)}
                                onClick={(e) => e.stopPropagation()}
                                className="inline-flex items-center gap-1 rounded-md bg-brand px-2.5 py-1 text-xs font-semibold text-ink hover:bg-brand-hover"
                              >
                                Generar pedido
                              </Link>
                            )}
                          </span>
                        </td>
                        <td className="px-2 py-2.5 text-muted">
                          <ChevronDown size={16} className={`transition-transform ${isOpen ? "rotate-180" : ""}`} />
                        </td>
                      </tr>
                      {isOpen && (
                        <tr>
                          <td colSpan={7} className="bg-canvas px-4 py-3">
                            <Details material={m} />
                          </td>
                        </tr>
                      )}
                    </RowGroup>
                  );
                })}
              </tbody>
            </table>
          </div>
        </>
      )}
    </div>
  );
}

// React needs a single parent per map item; a fragment with a key does the job.
function RowGroup({ children }: { children: React.ReactNode }) {
  return <>{children}</>;
}

// Expanded row: live purchase orders for the material, then the orders that reserve it.
function Details({ material }: { material: Material }) {
  const incoming = material.incoming ?? [];
  return (
    <div>
      {incoming.length > 0 && (
        <p className="flex flex-wrap items-center gap-x-3 gap-y-1 px-3 pt-3 text-sm">
          <span className="font-medium">Pedidos en curso:</span>
          {incoming.map((po) => (
            <span key={po.id} className="inline-flex items-center gap-1.5">
              <Link href={`/purchase-orders/${po.id}`} className="font-medium text-accent hover:underline">
                {po.code}
              </Link>
              <Pill tone={po.status === "suggested" ? "warning" : "info"}>{po.status_display}</Pill>
              <span className="tabular-nums text-muted">
                {qty(po.qty_pending)} {UNIT_LABEL[material.unit]} pendientes
              </span>
            </span>
          ))}
        </p>
      )}
      <Reservations id={material.id} />
    </div>
  );
}

// Orders that reserve this material (and how much of it had to be ordered).
function Reservations({ id }: { id: number }) {
  const { data } = useSWR<MaterialDetail>(`/api/materials/${id}/`, fetcher);
  if (!data) return <SkeletonLines lines={3} className="p-3" />;
  if (!data.requirements.length) return <p className="p-3 text-sm text-muted">Ninguna orden abierta lo reserva.</p>;
  return (
    <table className="w-full text-sm">
      <thead className="text-left text-xs text-muted">
        <tr>
          <th className="px-3 pb-1 pt-3 font-medium">Orden</th>
          <th className="px-3 pb-1 pt-3 text-right font-medium">Necesita</th>
          <th className="px-3 pb-1 pt-3 text-right font-medium">De stock</th>
          <th className="px-3 pb-1 pt-3 text-right font-medium">A pedir</th>
          <th className="px-3 pb-1 pt-3 font-medium">Estado</th>
        </tr>
      </thead>
      <tbody className="divide-y divide-line">
        {data.requirements.map((r) => (
          <tr key={`${r.order_code}-${r.status}`}>
            <td className="px-3 py-1.5">
              <Link href={`/orders/${r.order_id ?? r.order_code}`} className="font-medium text-accent hover:underline">
                {r.order_code}
              </Link>
            </td>
            <td className="px-3 py-1.5 text-right tabular-nums">{qty(r.qty_needed)}</td>
            <td className="px-3 py-1.5 text-right tabular-nums">{qty(r.qty_from_stock ?? 0)}</td>
            <td className={`px-3 py-1.5 text-right tabular-nums ${Number(r.qty_to_order) > 0 ? "font-semibold" : ""}`}>{qty(r.qty_to_order)}</td>
            <td className="px-3 py-1.5">
              <Pill tone={r.status === "pending" ? "warning" : "neutral"}>{r.status_display ?? REQ_STATUS[r.status] ?? r.status}</Pill>
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
