"use client";

import { FilterX, LayoutList, ShoppingCart, Users } from "lucide-react";
import Link from "next/link";
import { Suspense } from "react";
import useSWR from "swr";
import { FilterBar } from "@/components/filter-bar";
import { matchesCode, useListParams } from "@/components/list-filters";
import { PurchaseOrderList } from "@/components/purchase-order-list";
import { useUser } from "@/components/require-auth";
import { SkeletonTable } from "@/components/skeleton";
import { Button, buttonClass, Card } from "@/components/ui";
import { fetcher } from "@/lib/api";
import { formatDay } from "@/lib/format";
import type { PurchaseOrderListItem } from "@/lib/types";

// Chips and search filter the loaded list in the browser (Oscar, 11/10). The
// Gerente also gets the purchase orders waiting for his approval.
type View = "open" | "awaiting" | "approve" | "delivered" | "all";
const CLOSED = ["delivered", "cancelled", "cancelled_by_supplier", "rejected_by_supplier", "declined_by_supplier"];
const TESTS: Record<View, (po: PurchaseOrderListItem) => boolean> = {
  open: (po) => !CLOSED.includes(po.status),
  awaiting: (po) => !!po.awaiting_reply,
  approve: (po) => !!po.waiting_manager,
  delivered: (po) => po.status === "delivered",
  all: () => true,
};
const VIEWS: { key: View; label: string; manager?: boolean }[] = [
  { key: "open", label: "Abiertos" },
  { key: "awaiting", label: "Esperando respuesta" },
  { key: "approve", label: "Por aprobar", manager: true },
  { key: "delivered", label: "Entregados" },
  { key: "all", label: "Todos" },
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
  const views = VIEWS.filter((v) => !v.manager || user.role === "manager");
  const view = (views.some((v) => v.key === params.get("view")) ? params.get("view") : "open") as View;
  const q = params.get("q");
  // Comercial reads a plain list; Producción and the Gerente group by supplier.
  const canGroup = user.role !== "sales";
  const grouped = canGroup && params.get("by") !== "list";
  const { data, error } = useSWR<PurchaseOrderListItem[]>("/api/purchase-orders/", fetcher, { refreshInterval: 3000 });
  const all = data ?? [];
  const filtered = all.filter((po) => TESTS[view](po) && matchesCode(q, po.code, po.supplier.name, ...po.orders.map((o) => o.code)));
  const filtering = view !== "open" || !!q;

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h1 className="text-2xl font-bold tracking-tight">Pedidos a proveedores y talleres</h1>
        {user.role !== "sales" && (
          <Link href="/inventory?to_order=1" className={buttonClass()}>
            <ShoppingCart size={16} aria-hidden /> Insumos por pedir
          </Link>
        )}
      </div>

      <FilterBar
        search={{ value: q, onChange: (value) => params.set({ q: value }), placeholder: "Buscar por código o proveedor" }}
        chips={{
          label: "Pedidos",
          value: view,
          onChange: (next) => params.set({ view: next === "open" ? null : next }),
          options: views.map((v) => ({ key: v.key, label: v.label, count: all.filter(TESTS[v.key]).length })),
        }}
      >
        {canGroup && (
          <div className="flex w-fit rounded-lg bg-surface p-1 ring-1 ring-line" role="group" aria-label="Agrupar">
            <Toggle on={grouped} onClick={() => params.set({ by: null })}>
              <Users size={14} aria-hidden /> Por proveedor
            </Toggle>
            <Toggle on={!grouped} onClick={() => params.set({ by: "list" })}>
              <LayoutList size={14} aria-hidden /> Lista
            </Toggle>
          </div>
        )}
      </FilterBar>

      {error && !data && <p className="text-danger">No se pudieron cargar los pedidos.</p>}
      {!data && !error && <SkeletonTable rows={7} cols={6} />}
      {data && !filtered.length && (
        <div className="rounded-xl bg-surface p-6 text-center text-sm text-muted ring-1 ring-line">
          {filtering ? (
            <>
              <p>Ningún pedido coincide con {q ? `“${q}”` : "ese filtro"}.</p>
              <Button className="mt-3" onClick={() => params.set({ view: null, q: null })}>
                <FilterX size={16} aria-hidden /> Limpiar filtros
              </Button>
            </>
          ) : (
            <p>Todavía no hay pedidos.</p>
          )}
        </div>
      )}
      {filtered.length > 0 &&
        (grouped ? (
          groupBySupplier(filtered).map((group) => (
            <Card key={group.id}>
              <div className="mb-3 flex flex-wrap items-baseline gap-x-3 gap-y-1">
                <h2 className="text-base font-semibold">{group.name}</h2>
                <span className="text-xs text-muted">
                  {group.items.length} {group.items.length === 1 ? "pedido" : "pedidos"} · {group.next ? `próxima fecha ${formatDay(group.next)}` : "sin fecha comprometida"}
                </span>
              </div>
              <PurchaseOrderList items={group.items} grouped />
            </Card>
          ))
        ) : (
          <Card>
            <PurchaseOrderList items={filtered} />
          </Card>
        ))}
    </div>
  );
}

function Toggle({ on, onClick, children }: { on: boolean; onClick: () => void; children: React.ReactNode }) {
  return (
    <button
      type="button"
      aria-pressed={on}
      onClick={onClick}
      className={`inline-flex min-h-11 items-center gap-1.5 rounded-md px-3 text-sm transition-colors duration-150 sm:min-h-8 ${on ? "bg-ink text-white" : "hover:bg-canvas"}`}
    >
      {children}
    </button>
  );
}

// One group per supplier, the nearest committed date first (the plant and
// suppliers with nothing dated go last). `next` is the soonest open date.
function groupBySupplier(items: PurchaseOrderListItem[]) {
  const groups = new Map<number, { id: number; name: string; items: PurchaseOrderListItem[]; next: string | null }>();
  for (const po of items) {
    const group = groups.get(po.supplier.id) ?? { id: po.supplier.id, name: po.supplier.name, items: [], next: null };
    group.items.push(po);
    const due = CLOSED.includes(po.status) ? null : (po.committed_on ?? po.internal_due_on ?? null);
    if (due && (!group.next || due < group.next)) group.next = due;
    groups.set(po.supplier.id, group);
  }
  return [...groups.values()].sort((a, b) => (a.next ?? "9").localeCompare(b.next ?? "9") || a.name.localeCompare(b.name));
}
