"use client";

import { ArrowLeft } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { OrderForm } from "@/components/order-form";
import { RoleGate } from "@/components/require-auth";
import { Card } from "@/components/ui";

// Comercial and the Gerente register orders by hand (ADR 0025 B); the sales
// system's API and "Simular orden" keep working as before.
export default function NewOrderPage() {
  const router = useRouter();
  return (
    <RoleGate roles={["manager", "sales"]}>
      <div className="mx-auto max-w-4xl space-y-4">
        <Link href="/orders" className="inline-flex items-center gap-1 text-sm text-muted hover:text-ink">
          <ArrowLeft size={16} /> Órdenes
        </Link>
        <h1 className="text-2xl font-bold tracking-tight">Nueva orden</h1>
        <p className="text-sm text-muted">Llega igual que por la API de Comercial: el sistema la desglosa contra inventario y Producción confirma.</p>
        <Card>
          <OrderForm onSaved={(order) => router.push(`/orders/${order.id}`)} onCancel={() => router.push("/orders")} />
        </Card>
      </div>
    </RoleGate>
  );
}
