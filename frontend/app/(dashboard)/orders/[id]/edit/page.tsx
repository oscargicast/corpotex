"use client";

import { ArrowLeft } from "lucide-react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import useSWR from "swr";
import { OrderForm } from "@/components/order-form";
import { RoleGate, useUser } from "@/components/require-auth";
import { SkeletonDetail } from "@/components/skeleton";
import { Card } from "@/components/ui";
import { fetcher } from "@/lib/api";
import { canEditOrder } from "@/lib/orders";
import { useResolvedId } from "@/lib/resolve";
import type { OrderDetail } from "@/lib/types";

export default function EditOrderPage() {
  return (
    <RoleGate roles={["manager", "sales"]}>
      <EditOrder />
    </RoleGate>
  );
}

function EditOrder() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const user = useUser();
  const { id, notFound } = useResolvedId("orders", decodeURIComponent(params.id));
  const { data: order } = useSWR<OrderDetail>(id ? `/api/orders/${id}/` : null, fetcher);

  if (notFound) return <p className="text-muted">No existe la orden {decodeURIComponent(params.id)}.</p>;
  if (!order) return <SkeletonDetail />;

  const back = `/orders/${order.id}`;
  return (
    <div className="mx-auto max-w-4xl space-y-4">
      <Link href={back} className="inline-flex items-center gap-1 text-sm text-muted hover:text-ink">
        <ArrowLeft size={16} /> {order.code}
      </Link>
      <h1 className="text-2xl font-bold tracking-tight">Editar {order.code}</h1>
      {canEditOrder(user, order) ? (
        <Card>
          <OrderForm key={order.id} initial={order} onSaved={() => router.push(back)} onCancel={() => router.push(back)} />
        </Card>
      ) : (
        <Card>
          <p className="text-sm text-muted">
            {user.role === "sales"
              ? "Comercial edita sus órdenes hasta que Producción aprueba la ficha técnica; después, solo el Gerente."
              : "Esta orden ya no se puede editar."}
          </p>
        </Card>
      )}
    </div>
  );
}
