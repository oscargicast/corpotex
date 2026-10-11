"use client";

import { ArrowLeft } from "lucide-react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useState } from "react";
import useSWR from "swr";
import { ChannelPill } from "@/components/channel-pill";
import { Numbers } from "@/components/numbers";
import { PurchaseOrderList } from "@/components/purchase-order-list";
import { RoleGate } from "@/components/require-auth";
import { Button, Card, Pill, SectionTitle } from "@/components/ui";
import { apiFetch, fetcher } from "@/lib/api";
import { formatDay, formatMoney, formatNum, formatScore, num } from "@/lib/format";
import type { SupplierDetail } from "@/lib/types";

export default function SupplierDetailPage() {
  return (
    <RoleGate roles={["manager"]}>
      <Supplier />
    </RoleGate>
  );
}

function Supplier() {
  const { id } = useParams<{ id: string }>();
  const { data: supplier, mutate } = useSWR<SupplierDetail>(`/api/suppliers/${id}/`, fetcher, { refreshInterval: 5000 });
  if (!supplier) return <div className="h-40 animate-pulse rounded-xl bg-line" />;

  return (
    <div className="space-y-5">
      <Link href="/suppliers" className="inline-flex items-center gap-1 text-sm text-muted hover:text-ink">
        <ArrowLeft size={16} /> Proveedores
      </Link>

      <header>
        <div className="flex flex-wrap items-center gap-2">
          <h1 className="text-2xl font-bold tracking-tight">{supplier.name}</h1>
          <ChannelPill supplier={supplier} />
          {supplier.status !== "active" && <Pill tone="warning">{supplier.status_display}</Pill>}
        </div>
        <p className="mt-1 text-sm text-muted">
          {[supplier.kind_display, supplier.city, supplier.specialties.join(", "), `cobra en ${supplier.currency}`].filter(Boolean).join(" · ")}
        </p>
      </header>

      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <Fact label="Cumplimiento" value={num(supplier.on_time_score) === null ? "—" : `${formatScore(supplier.on_time_score)} %`} />
        <Fact label="Calidad" value={num(supplier.quality_score) === null ? "—" : `${formatNum(supplier.quality_score)} / 5`} />
        <Fact label="Capacidad" value={supplier.weekly_capacity ? `${supplier.weekly_capacity} u./sem.` : "—"} />
        <Fact label="Carga actual" value={supplier.load_pct === null ? "—" : `${supplier.load_pct} %`} />
      </div>

      <div className="grid items-start gap-5 xl:grid-cols-2">
        {!supplier.is_in_house && (
          <Card>
            <SectionTitle count={supplier.numbers.length}>Números de WhatsApp</SectionTitle>
            <Numbers supplierId={supplier.id} numbers={supplier.numbers} onChange={() => mutate()} />
          </Card>
        )}

        <Card>
          <SectionTitle>Pagos</SectionTitle>
          {supplier.payments_summary.length ? (
            <ul className="space-y-1 text-sm tabular-nums">
              {supplier.payments_summary.map((row) => (
                <li key={row.currency} className="flex flex-wrap justify-between gap-2">
                  <span>
                    Depositado <strong>{formatMoney(row.paid, row.currency)}</strong>
                  </span>
                  <span>
                    Saldo <strong>{formatMoney(row.pending, row.currency)}</strong>
                    {row.overdue_count > 0 && (
                      <span className="ml-2">
                        <Pill tone="danger">{row.overdue_count} vencido{row.overdue_count > 1 ? "s" : ""}</Pill>
                      </span>
                    )}
                  </span>
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-sm text-muted">Sin pagos todavía.</p>
          )}
        </Card>

        <Card>
          <SectionTitle count={supplier.rates.length}>Tarifas</SectionTitle>
          {supplier.rates.length ? (
            <ul className="divide-y divide-line text-sm">
              {supplier.rates.map((rate) => (
                <li key={rate.id} className="flex justify-between gap-2 py-2 first:pt-0">
                  <span>
                    {rate.item_name}
                    <span className="block text-xs text-muted">desde {formatDay(rate.valid_from)}</span>
                  </span>
                  <span className="font-semibold tabular-nums">{formatMoney(rate.unit_price, rate.currency)}</span>
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-sm text-muted">Sin tarifas históricas.</p>
          )}
        </Card>

        <Card>
          <SectionTitle count={supplier.ratings.length}>Calificaciones por entrega</SectionTitle>
          {supplier.ratings.length ? (
            <table className="w-full text-sm">
              <thead className="text-left text-xs text-muted">
                <tr>
                  <th className="pb-1 font-medium">Pedido</th>
                  <th className="pb-1 text-right font-medium">Retraso</th>
                  <th className="pb-1 text-right font-medium">Calidad</th>
                  <th className="pb-1 text-right font-medium">Merma</th>
                  <th className="pb-1 text-right font-medium">Puntaje</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-line tabular-nums">
                {supplier.ratings.map((r) => (
                  <tr key={r.purchase_order_code}>
                    <td className="py-1.5">{r.purchase_order_code}</td>
                    <td className={`py-1.5 text-right ${r.delay_days > 0 ? "text-danger" : ""}`}>{r.delay_days} d</td>
                    <td className="py-1.5 text-right">{formatNum(r.quality)}</td>
                    <td className="py-1.5 text-right">{formatNum(r.defect_pct)} %</td>
                    <td className="py-1.5 text-right font-semibold">{formatScore(r.score)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : (
            <p className="text-sm text-muted">Se califica solo al cerrar cada pedido.</p>
          )}
        </Card>

        <Notes supplier={supplier} onSaved={() => mutate()} />
      </div>

      <Card>
        <SectionTitle count={supplier.purchase_orders.length}>Pedidos</SectionTitle>
        <PurchaseOrderList items={supplier.purchase_orders} />
      </Card>
    </div>
  );
}

// How the agent treats this supplier (from the style onboarding, editable).
function Notes({ supplier, onSaved }: { supplier: SupplierDetail; onSaved: () => void }) {
  const [notes, setNotes] = useState(supplier.notes);
  const [busy, setBusy] = useState(false);
  const dirty = notes !== supplier.notes;

  async function save() {
    setBusy(true);
    try {
      await apiFetch(`/api/suppliers/${supplier.id}/`, { method: "PATCH", json: { notes } });
      onSaved();
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card>
      <SectionTitle>Notas de trato</SectionTitle>
      <textarea
        value={notes}
        onChange={(e) => setNotes(e.target.value)}
        rows={6}
        placeholder={"Trato: tú o usted\nTono:\nInsistencia:\nHorario:\nOjo:"}
        className="w-full rounded-md p-2 font-mono text-sm ring-1 ring-line"
      />
      <p className="mt-1 text-xs text-muted">El agente las lee antes de escribirle. Seguimiento cada {supplier.follow_up_every_hours} h.</p>
      {dirty && (
        <Button kind="dark" className="mt-2" disabled={busy} onClick={save}>
          Guardar notas
        </Button>
      )}
    </Card>
  );
}

function Fact({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-xl bg-surface p-3 ring-1 ring-line">
      <p className="text-xs text-muted">{label}</p>
      <p className="mt-0.5 font-semibold tabular-nums">{value}</p>
    </div>
  );
}
