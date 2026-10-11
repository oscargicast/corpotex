"use client";

import Link from "next/link";
import useSWR from "swr";
import { ChannelPill } from "@/components/channel-pill";
import { SupplierForm } from "@/components/supplier-form";
import { Card, SectionTitle } from "@/components/ui";
import { fetcher } from "@/lib/api";
import type { SupplierListItem } from "@/lib/types";
import { SkeletonLines } from "@/components/skeleton";

// Step 2: suppliers and their phones. New numbers start inactive (ADR 0016);
// they are activated from the supplier's detail. CSV import is P1.
export default function OnboardingSuppliers() {
  const { data, mutate } = useSWR<SupplierListItem[]>("/api/suppliers/", fetcher);
  const list = [...(data ?? [])].sort((a, b) => Number(b.is_in_house) - Number(a.is_in_house));

  return (
    <div className="grid items-start gap-4 xl:grid-cols-2">
      <Card>
        <SectionTitle count={list.length}>Proveedores registrados</SectionTitle>
        {!data && <SkeletonLines lines={4} />}
        {data && !list.length && <p className="text-sm text-muted">Todavía no hay proveedores.</p>}
        <ul className="divide-y divide-line">
          {list.map((supplier) => (
            <li key={supplier.id} className="flex flex-wrap items-center justify-between gap-2 py-2.5 first:pt-0">
              <div className="text-sm">
                <Link href={`/suppliers/${supplier.id}`} className="font-medium hover:underline">
                  {supplier.name}
                </Link>
                <p className="text-xs text-muted">
                  {[supplier.kind_display, supplier.city].filter(Boolean).join(" · ")}
                </p>
              </div>
              <ChannelPill supplier={supplier} />
            </li>
          ))}
        </ul>
        <p className="mt-3 text-xs text-muted">Los números entran inactivos: actívalos en el detalle de cada proveedor para que el agente pueda escribirles.</p>
      </Card>

      <Card>
        <SectionTitle>Agregar proveedor</SectionTitle>
        <SupplierForm endpoint="/api/suppliers/" submitLabel="Agregar" onCreated={() => mutate()} />
      </Card>
    </div>
  );
}
