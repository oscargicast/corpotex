"use client";

import { ExternalLink } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import useSWR from "swr";
import { ChannelPill } from "@/components/channel-pill";
import { RoleGate } from "@/components/require-auth";
import { Button, Pill } from "@/components/ui";
import { apiFetch, fetcher } from "@/lib/api";
import type { SupplierDetail, SupplierListItem } from "@/lib/types";
import { formatNum, formatScore, num } from "@/lib/format";

export default function SuppliersPage() {
  return (
    <RoleGate roles={["manager"]}>
      <Suppliers />
    </RoleGate>
  );
}

function Suppliers() {
  const [tab, setTab] = useState<"active" | "review">("active");
  const { data: active, mutate: mutateActive } = useSWR<SupplierListItem[]>("/api/suppliers/", fetcher, { refreshInterval: 5000 });
  const { data: review, mutate: mutateReview } = useSWR<SupplierListItem[]>("/api/suppliers/?status=pending_review", fetcher);
  // The in-house plant goes first.
  const list = [...(active ?? [])].sort((a, b) => Number(b.is_in_house) - Number(a.is_in_house));

  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-bold tracking-tight">Proveedores y talleres</h1>
      <div className="flex rounded-lg bg-surface p-1 ring-1 ring-line w-fit" role="tablist">
        <TabButton active={tab === "active"} onClick={() => setTab("active")}>
          Activos
        </TabButton>
        <TabButton active={tab === "review"} onClick={() => setTab("review")}>
          Por revisar {review?.length ? <span className="ml-1 rounded-full bg-danger px-1.5 text-xs text-white">{review.length}</span> : null}
        </TabButton>
      </div>

      {tab === "active" ? (
        !active ? (
          <div className="h-40 animate-pulse rounded-xl bg-line" />
        ) : (
          <div className="grid gap-3 md:grid-cols-2 2xl:grid-cols-3">
            {list.map((supplier) => (
              <SupplierCard key={supplier.id} supplier={supplier} />
            ))}
          </div>
        )
      ) : (
        <Review
          items={review ?? []}
          onChange={() => {
            mutateReview();
            mutateActive();
          }}
        />
      )}
    </div>
  );
}

function TabButton({ active, onClick, children }: { active: boolean; onClick: () => void; children: React.ReactNode }) {
  return (
    <button type="button" role="tab" aria-selected={active} onClick={onClick} className={`rounded-md px-3 py-1.5 text-sm ${active ? "bg-ink text-white" : ""}`}>
      {children}
    </button>
  );
}

function SupplierCard({ supplier }: { supplier: SupplierListItem }) {
  return (
    <Link href={`/suppliers/${supplier.id}`} className="block rounded-xl bg-surface p-4 ring-1 ring-line hover:ring-ink/30">
      <div className="flex items-start justify-between gap-2">
        <div>
          <p className="font-semibold">{supplier.name}</p>
          <p className="text-xs text-muted">
            {supplier.kind_display} · {supplier.city}
          </p>
        </div>
        <ChannelPill supplier={supplier} />
      </div>
      <p className="mt-2 flex flex-wrap gap-1">
        {supplier.specialties.map((s) => (
          <span key={s} className="rounded bg-canvas px-1.5 text-xs">
            {s}
          </span>
        ))}
      </p>
      <dl className="mt-3 grid grid-cols-3 gap-2 text-xs">
        <Stat label="Cumplimiento" value={num(supplier.on_time_score) === null ? "—" : `${formatScore(supplier.on_time_score)} %`} />
        <Stat label="Calidad" value={num(supplier.quality_score) === null ? "—" : `${formatNum(supplier.quality_score)} / 5`} />
        <Stat
          label="Carga"
          value={supplier.load_pct === null ? "—" : `${supplier.load_pct} %`}
          tone={supplier.load_pct !== null && supplier.load_pct >= 85 ? "text-danger" : undefined}
        />
      </dl>
      {supplier.weekly_capacity && (
        <p className="mt-2 text-xs text-muted">
          Capacidad {supplier.weekly_capacity} u./semana · plazo {supplier.lead_time_days} días · {supplier.open_purchase_orders} pedidos abiertos
        </p>
      )}
    </Link>
  );
}

function Stat({ label, value, tone }: { label: string; value: string; tone?: string }) {
  return (
    <div>
      <dt className="text-muted">{label}</dt>
      <dd className={`font-semibold tabular-nums ${tone ?? ""}`}>{value}</dd>
    </div>
  );
}

// Self-registered and externally suggested suppliers (criterion 7).
function Review({ items, onChange }: { items: SupplierListItem[]; onChange: () => void }) {
  if (!items.length) return <p className="text-sm text-muted">No hay proveedores por revisar.</p>;
  return (
    <div className="grid items-start gap-3 md:grid-cols-2">
      {items.map((supplier) => (
        <ReviewCard key={supplier.id} supplier={supplier} onChange={onChange} />
      ))}
    </div>
  );
}

function ReviewCard({ supplier, onChange }: { supplier: SupplierListItem; onChange: () => void }) {
  const { data: detail } = useSWR<SupplierDetail>(supplier.source === "external" ? `/api/suppliers/${supplier.id}/` : null, fetcher);
  const [busy, setBusy] = useState(false);

  async function decide(status: "active" | "inactive") {
    setBusy(true);
    try {
      await apiFetch(`/api/suppliers/${supplier.id}/`, { method: "PATCH", json: { status } });
      onChange();
    } finally {
      setBusy(false);
    }
  }

  const source = detail?.source_detail;
  // The URL comes from a web search: only http(s) becomes a link.
  let host = "";
  let safeUrl = "";
  try {
    const url = source ? new URL(source.url) : null;
    if (url && (url.protocol === "https:" || url.protocol === "http:")) {
      host = url.hostname;
      safeUrl = url.href;
    }
  } catch {
    // Not a URL: show the excerpt without a link.
  }

  return (
    <article className="rounded-xl bg-surface p-4 ring-1 ring-line">
      <div className="flex items-start justify-between gap-2">
        <div>
          <p className="font-semibold">{supplier.name}</p>
          <p className="text-xs text-muted">
            {supplier.kind_display} · {supplier.city} · {supplier.specialties.join(", ")}
          </p>
        </div>
        <Pill tone={supplier.source === "external" ? "info" : "warning"}>{supplier.source_display}</Pill>
      </div>
      {source && (
        <blockquote className="mt-3 border-l-2 border-line pl-3 text-sm text-muted">
          {source.excerpt}
          {safeUrl && (
            // Open outside the dashboard, without the opener.
            <a href={safeUrl} target="_blank" rel="noopener noreferrer" className="mt-1 flex items-center gap-1 text-xs text-accent hover:underline">
              {host} <ExternalLink size={12} />
            </a>
          )}
        </blockquote>
      )}
      <div className="mt-3 flex gap-2">
        <Button kind="dark" disabled={busy} onClick={() => decide("active")}>
          Aprobar
        </Button>
        <Button disabled={busy} onClick={() => decide("inactive")}>
          Descartar
        </Button>
      </div>
    </article>
  );
}
