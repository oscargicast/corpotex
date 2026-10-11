"use client";

import { ShoppingCart } from "lucide-react";
import Link from "next/link";
import { Suspense } from "react";
import useSWR from "swr";
import { PURCHASE_ORDER_STATUSES, SearchBox, StatusChips, statusOptions, useListParams } from "@/components/list-filters";
import { PurchaseOrderList } from "@/components/purchase-order-list";
import { useUser } from "@/components/require-auth";
import { SkeletonTable } from "@/components/skeleton";
import { Button, buttonClass, Card } from "@/components/ui";
import { fetcher } from "@/lib/api";
import type { PurchaseOrderListItem } from "@/lib/types";

const KINDS = [
  { value: "", label: "Todos" },
  { value: "material", label: "Insumos" },
  { value: "workshop", label: "Talleres" },
  { value: "finished", label: "Terminados" },
];

export default function PurchaseOrdersPage() {
  return (
    <Suspense>
      <PurchaseOrders />
    </Suspense>
  );
}

function PurchaseOrders() {
  const user = useUser();
  const params = useListParams();
  const kind = params.get("kind");
  const waiting = params.get("waiting") === "1";
  const statuses = params.list("status");
  const q = params.get("q");
  // Every filter goes to the API (B6.5): ?kind=&waiting_manager=1&status=a,b&q= (q also
  // matches the orders' codes). The list without status/q feeds the chip counts.
  const base = new URLSearchParams({ ...(kind && { kind }), ...(waiting && { waiting_manager: "1" }) });
  const query = new URLSearchParams(base);
  if (statuses.length) query.set("status", statuses.join(","));
  if (q) query.set("q", q);
  const { data, error } = useSWR<PurchaseOrderListItem[]>(`/api/purchase-orders/${query.size ? `?${query}` : ""}`, fetcher, {
    refreshInterval: 3000,
    keepPreviousData: true,
  });
  const { data: all } = useSWR<PurchaseOrderListItem[]>(`/api/purchase-orders/${base.size ? `?${base}` : ""}`, fetcher, { refreshInterval: 5000 });
  const options = statusOptions(all ?? [], PURCHASE_ORDER_STATUSES);
  const filtered = data ?? [];
  const filtering = !!(kind || waiting || statuses.length || q);

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h1 className="text-2xl font-bold tracking-tight">Pedidos a proveedores y talleres</h1>
        {user.role !== "sales" && (
          <Link href="/inventory?to_order=1" className={buttonClass("ghost")}>
            <ShoppingCart size={16} /> Insumos por pedir
          </Link>
        )}
      </div>
      <div className="flex flex-wrap items-center gap-2">
        <div className="flex rounded-lg bg-surface p-1 ring-1 ring-line" role="tablist">
          {KINDS.map((k) => (
            <button
              key={k.value || "all"}
              type="button"
              role="tab"
              aria-selected={kind === k.value}
              onClick={() => params.set({ kind: k.value })}
              className={`rounded-md px-3 py-1.5 text-sm transition-colors duration-150 ${kind === k.value ? "bg-ink text-white" : "hover:bg-canvas"}`}
            >
              {k.label}
            </button>
          ))}
        </div>
        <label className="flex items-center gap-2 text-sm">
          <input type="checkbox" checked={waiting} onChange={(e) => params.set({ waiting: e.target.checked ? "1" : null })} />
          Solo esperando al Gerente
        </label>
        <SearchBox value={q} onChange={(value) => params.set({ q: value })} placeholder="Buscar por código de pedido u orden" />
      </div>
      {options.length > 0 && <StatusChips options={options} selected={statuses} onChange={(next) => params.set({ status: next })} allLabel="Todos los estados" />}

      {error && !data && <p className="text-danger">No se pudieron cargar los pedidos.</p>}
      {!data && !error && <SkeletonTable rows={7} cols={6} />}
      {data && !filtered.length && (
        <div className="rounded-xl bg-surface p-6 text-center text-sm text-muted ring-1 ring-line">
          {filtering ? (
            <>
              <p>Ningún pedido coincide con {q ? `“${q}”` : "esos filtros"}.</p>
              <Button className="mt-3" onClick={() => params.set({ kind: null, waiting: null, status: null, q: null })}>
                Limpiar filtros
              </Button>
            </>
          ) : (
            <p>Todavía no hay pedidos.</p>
          )}
        </div>
      )}
      {filtered.length > 0 && (
        <Card>
          <PurchaseOrderList items={filtered} />
        </Card>
      )}
    </div>
  );
}
