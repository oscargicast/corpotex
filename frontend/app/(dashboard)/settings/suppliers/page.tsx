"use client";

import { ArrowRight } from "lucide-react";
import Link from "next/link";
import useSWR from "swr";
import { ChannelPill } from "@/components/channel-pill";
import { SkeletonLines } from "@/components/skeleton";
import { Card, SectionTitle } from "@/components/ui";
import { fetcher } from "@/lib/api";
import type { SupplierListItem } from "@/lib/types";

// Step 2: who the agent can talk to. Adding, editing and activating numbers
// happens in /suppliers; this step only shows where things stand.
export default function OnboardingSuppliers() {
  const { data } = useSWR<SupplierListItem[]>("/api/suppliers/", fetcher, { refreshInterval: 5000 });
  const list = [...(data ?? [])].sort((a, b) => Number(b.is_in_house) - Number(a.is_in_house));
  const external = list.filter((s) => !s.is_in_house);
  const withChannel = external.filter((s) => s.active_numbers_count > 0).length;
  const withoutChannel = external.length - withChannel;

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
                <p className="text-xs text-muted">{[supplier.kind_display, supplier.city].filter(Boolean).join(" · ")}</p>
              </div>
              <ChannelPill supplier={supplier} />
            </li>
          ))}
        </ul>
      </Card>

      <Card className="flex flex-col gap-4">
        <SectionTitle>Resumen</SectionTitle>
        {data ? (
          <dl className="grid grid-cols-3 gap-3 text-center">
            <Figure value={external.length} label="registrados" />
            <Figure value={withChannel} label="con canal" tone="text-success" />
            <Figure value={withoutChannel} label="sin canal" tone={withoutChannel ? "text-danger" : undefined} />
          </dl>
        ) : (
          <SkeletonLines lines={2} />
        )}
        <Link
          href="/suppliers"
          className="flex items-center justify-center gap-2 rounded-lg bg-brand px-4 py-4 text-base font-semibold text-ink hover:bg-brand-hover"
        >
          Gestionar proveedores <ArrowRight size={18} />
        </Link>
        <p className="text-xs text-muted">
          Agregar un proveedor, editar sus datos y tarifas, y activar sus números de WhatsApp se hace ahí. Los números entran inactivos: sin un número activo el
          agente no puede escribirle.
        </p>
      </Card>
    </div>
  );
}

function Figure({ value, label, tone }: { value: number; label: string; tone?: string }) {
  return (
    <div className="rounded-lg bg-canvas p-3">
      <dd className={`text-2xl font-bold tabular-nums ${tone ?? ""}`}>{value}</dd>
      <dt className="text-xs text-muted">{label}</dt>
    </div>
  );
}
