"use client";

import { ArrowLeft } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { MagicOrderForm } from "@/components/magic-order-form";
import { RoleGate } from "@/components/require-auth";

// Orden mágica (ADR 0028): Comercial and the Gerente write each item as the
// customer says it; the items are recognized while typing and the order is
// born broken down. Editing keeps the plain form (orders/[id]/edit).
export default function NewOrderPage() {
  const router = useRouter();
  return (
    <RoleGate roles={["manager", "sales"]}>
      <div className="mx-auto max-w-6xl space-y-4">
        <Link href="/orders" className="inline-flex min-h-11 items-center gap-1 text-sm text-muted hover:text-ink sm:min-h-0">
          <ArrowLeft size={16} aria-hidden /> Órdenes
        </Link>
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Nueva orden</h1>
          <p className="mt-1 text-sm text-muted">Escribe lo que pide el cliente. Cada prenda se reconoce sola y la orden se guarda ya desglosada contra inventario.</p>
        </div>
        <MagicOrderForm onSaved={(order) => router.push(`/orders/${order.id}`)} onCancel={() => router.push("/orders")} />
      </div>
    </RoleGate>
  );
}
