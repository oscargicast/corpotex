"use client";

import { ChevronDown, Search } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import useSWR from "swr";
import { RoleGate } from "@/components/require-auth";
import { Thumb } from "@/components/thumb";
import { Pill, type Tone } from "@/components/ui";
import { fetcher } from "@/lib/api";
import type { Material, MaterialDetail } from "@/lib/types";

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

// "Low" = less than 10 % of the stock is still free.
function level(m: Material): { tone: Tone; label: string } {
  const available = Number(m.available);
  if (available <= 0) return { tone: "danger", label: "Sin stock libre" };
  if (available < Number(m.stock) * 0.1) return { tone: "warning", label: "Bajo" };
  return { tone: "success", label: "OK" };
}

const qty = (v: string | number) => Number(v).toLocaleString("es-PE", { maximumFractionDigits: 2 });

export default function InventoryPage() {
  return (
    <RoleGate roles={["manager", "production"]}>
      <Inventory />
    </RoleGate>
  );
}

function Inventory() {
  const { data, error } = useSWR<Material[]>("/api/materials/", fetcher, { refreshInterval: 5000 });
  const [kind, setKind] = useState("");
  const [query, setQuery] = useState("");
  const [open, setOpen] = useState<number | null>(null);

  const q = query.trim().toLowerCase();
  const rows = (data ?? [])
    .filter((m) => (!kind || m.kind === kind) && (!q || m.sku.toLowerCase().includes(q) || m.name.toLowerCase().includes(q)))
    // Problems first.
    .sort((a, b) => Number(a.available) - Number(b.available));
  const short = (data ?? []).filter((m) => Number(m.available) <= 0).length;

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h1 className="text-2xl font-bold tracking-tight">Inventario</h1>
        {short > 0 && <Pill tone="danger">{short} insumo{short > 1 ? "s" : ""} sin stock libre</Pill>}
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
      </div>

      {error && !data && <p className="text-danger">No se pudo cargar el inventario.</p>}
      {!data && !error && <div className="h-40 animate-pulse rounded-xl bg-line" />}
      {data && !rows.length && <p className="text-sm text-muted">Ningún insumo coincide.</p>}

      {rows.length > 0 && (
        <>
          <ul className="space-y-2 md:hidden">
            {rows.map((m) => (
              <li key={m.id} className="rounded-lg bg-surface ring-1 ring-line">
                <button type="button" onClick={() => setOpen(open === m.id ? null : m.id)} className="flex w-full items-center gap-3 p-3 text-left">
                  <Thumb src={m.image} alt={m.name} />
                  <span className="min-w-0 flex-1">
                    <span className="block truncate font-semibold">{m.name}</span>
                    <span className="block text-xs text-muted">
                      {m.sku} · {m.kind_display ?? KIND_LABEL[m.kind]}
                    </span>
                    <span className="mt-1 block text-xs tabular-nums">
                      stock {qty(m.stock)} · reservado {qty(m.committed)} · <strong>libre {qty(m.available)}</strong> {UNIT_LABEL[m.unit]}
                    </span>
                  </span>
                  <Pill tone={level(m).tone}>{level(m).label}</Pill>
                </button>
                {open === m.id && <Reservations id={m.id} />}
              </li>
            ))}
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
                {rows.map((m) => {
                  const l = level(m);
                  const isOpen = open === m.id;
                  return (
                    <RowGroup key={m.id}>
                      <tr onClick={() => setOpen(isOpen ? null : m.id)} className="cursor-pointer hover:bg-canvas" aria-expanded={isOpen}>
                        <td className="px-4 py-2.5">
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
                        <td className={`px-4 py-2.5 text-right font-semibold tabular-nums ${Number(m.available) <= 0 ? "text-danger" : ""}`}>{qty(m.available)}</td>
                        <td className="px-4 py-2.5">
                          <Pill tone={l.tone}>{l.label}</Pill>
                        </td>
                        <td className="px-2 py-2.5 text-muted">
                          <ChevronDown size={16} className={`transition-transform ${isOpen ? "rotate-180" : ""}`} />
                        </td>
                      </tr>
                      {isOpen && (
                        <tr>
                          <td colSpan={7} className="bg-canvas px-4 py-3">
                            <Reservations id={m.id} />
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

// Orders that reserve this material (and how much of it had to be ordered).
function Reservations({ id }: { id: number }) {
  const { data } = useSWR<MaterialDetail>(`/api/materials/${id}/`, fetcher);
  if (!data) return <p className="p-3 text-sm text-muted">Cargando…</p>;
  if (!data.requirements.length) return <p className="p-3 text-sm text-muted">Ninguna orden abierta lo reserva.</p>;
  return (
    <table className="w-full text-sm">
      <thead className="text-left text-xs text-muted">
        <tr>
          <th className="px-3 pb-1 font-medium">Orden</th>
          <th className="px-3 pb-1 text-right font-medium">Necesita</th>
          <th className="px-3 pb-1 text-right font-medium">De stock</th>
          <th className="px-3 pb-1 text-right font-medium">A pedir</th>
          <th className="px-3 pb-1 font-medium">Estado</th>
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
