"use client";

import { useState } from "react";
import useSWR from "swr";
import { PurchaseOrderList } from "@/components/purchase-order-list";
import { Card } from "@/components/ui";
import { fetcher } from "@/lib/api";
import type { PurchaseOrderListItem } from "@/lib/types";
import { SkeletonTable } from "@/components/skeleton";

const KINDS = [
  { value: "", label: "Todos" },
  { value: "material", label: "Insumos" },
  { value: "workshop", label: "Talleres" },
  { value: "finished", label: "Terminados" },
];

export default function PurchaseOrdersPage() {
  const [kind, setKind] = useState("");
  const [waiting, setWaiting] = useState(false);
  const query = new URLSearchParams({ ...(kind && { kind }), ...(waiting && { waiting_manager: "1" }) }).toString();
  const { data, error } = useSWR<PurchaseOrderListItem[]>(`/api/purchase-orders/${query ? `?${query}` : ""}`, fetcher, {
    refreshInterval: 3000,
  });

  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-bold tracking-tight">Pedidos a proveedores y talleres</h1>
      <div className="flex flex-wrap items-center gap-2">
        <div className="flex rounded-lg bg-surface p-1 ring-1 ring-line" role="tablist">
          {KINDS.map((k) => (
            <button
              key={k.value || "all"}
              type="button"
              role="tab"
              aria-selected={kind === k.value}
              onClick={() => setKind(k.value)}
              className={`rounded-md px-3 py-1.5 text-sm ${kind === k.value ? "bg-ink text-white" : ""}`}
            >
              {k.label}
            </button>
          ))}
        </div>
        <label className="flex items-center gap-2 text-sm">
          <input type="checkbox" checked={waiting} onChange={(e) => setWaiting(e.target.checked)} />
          Solo esperando al Gerente
        </label>
      </div>
      {error && !data && <p className="text-danger">No se pudieron cargar los pedidos.</p>}
      {!data && !error && <SkeletonTable rows={7} cols={6} />}
      {data && (
        <Card>
          <PurchaseOrderList items={data} />
        </Card>
      )}
    </div>
  );
}
