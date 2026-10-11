"use client";

import { ExternalLink, Pause, Play, Plus } from "lucide-react";
import Link from "next/link";
import { useRef, useState } from "react";
import useSWR from "swr";
import { WhatsApp } from "@/components/icons";
import { RoleGate } from "@/components/require-auth";
import { Button, CARD_HOVER, Pill } from "@/components/ui";
import { apiFetch, fetcher } from "@/lib/api";
import type { AgentSettings, SupplierDetail, SupplierListItem } from "@/lib/types";
import { formatNum, formatScore, num } from "@/lib/format";
import { SkeletonCards } from "@/components/skeleton";
import { SupplierForm } from "@/components/supplier-form";

export default function SuppliersPage() {
  return (
    <RoleGate roles={["manager"]}>
      <Suppliers />
    </RoleGate>
  );
}

function Suppliers() {
  const [tab, setTab] = useState<"active" | "review">("active");
  const dialog = useRef<HTMLDialogElement>(null);
  const [opened, setOpened] = useState(0);
  const { data: active, mutate: mutateActive } = useSWR<SupplierListItem[]>("/api/suppliers/", fetcher, { refreshInterval: 5000 });
  const { data: review, mutate: mutateReview } = useSWR<SupplierListItem[]>("/api/suppliers/?status=pending_review", fetcher);
  const { data: agent, mutate: mutateAgent } = useSWR<AgentSettings>("/api/settings/agent/", fetcher, { refreshInterval: 10000, shouldRetryOnError: false });
  const [filter, setFilter] = useState<FilterKey>("all");
  const [confirmAgent, setConfirmAgent] = useState(false);
  const [agentBusy, setAgentBusy] = useState(false);
  const [toggling, setToggling] = useState<number | null>(null);
  const globalPaused = !!agent?.paused;

  // The in-house plant leaves the list: its load is a Monitor KPI (Oscar, 11/10).
  const list = (active ?? []).filter((s) => !s.is_in_house);
  const shown = list.filter(FILTERS.find((f) => f.key === filter)!.test(globalPaused));

  async function setAgentPaused(paused: boolean) {
    setAgentBusy(true);
    try {
      await mutateAgent(apiFetch<AgentSettings>("/api/settings/agent/", { method: "PATCH", json: { paused } }), { revalidate: false });
      setConfirmAgent(false);
    } finally {
      setAgentBusy(false);
    }
  }

  async function toggleSupplier(supplier: SupplierListItem) {
    const next = !supplier.agent_paused;
    setToggling(supplier.id);
    await mutateActive((all) => all?.map((x) => (x.id === supplier.id ? { ...x, agent_paused: next } : x)), { revalidate: false });
    try {
      await apiFetch(`/api/suppliers/${supplier.id}/`, { method: "PATCH", json: { agent_paused: next } });
    } finally {
      setToggling(null);
      mutateActive();
    }
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-2xl font-bold tracking-tight">Proveedores y talleres</h1>
        <div className="flex flex-wrap gap-2">
          {agent && (
            <Button onClick={() => setConfirmAgent(true)} disabled={confirmAgent}>
              {globalPaused ? <Play size={16} aria-hidden /> : <Pause size={16} aria-hidden />}
              {globalPaused ? "Reanudar agente" : "Pausar agente"}
            </Button>
          )}
          <Button
            kind="primary"
            onClick={() => {
              setOpened((n) => n + 1);
              dialog.current?.showModal();
            }}
          >
            <Plus size={16} /> Nuevo proveedor
          </Button>
        </div>
      </div>
      {confirmAgent && (
        <div className="flex flex-wrap items-center gap-2 rounded-lg bg-warning-soft px-3 py-2 text-sm text-warning" role="alert">
          {globalPaused
            ? "El agente vuelve a escribir a los proveedores, salvo los que pausaste uno por uno, y manda el primer mensaje de los pedidos aprobados durante la pausa. ¿Reanudar?"
            : "El agente deja de escribir a todos los proveedores hasta que lo reanudes. ¿Pausar?"}
          <Button kind="dark" busy={agentBusy} onClick={() => setAgentPaused(!globalPaused)}>
            {globalPaused ? "Reanudar agente" : "Pausar agente"}
          </Button>
          <Button disabled={agentBusy} onClick={() => setConfirmAgent(false)}>
            Cancelar
          </Button>
        </div>
      )}
      {globalPaused && !confirmAgent && (
        <p className="flex items-center gap-2 rounded-lg bg-warning-soft px-3 py-2 text-sm font-medium text-warning" role="status">
          <Pause size={16} aria-hidden /> Agente en pausa: no le escribe a ningún proveedor.
        </p>
      )}
      <dialog
        ref={dialog}
        className="m-auto w-[min(40rem,calc(100vw-2rem))] rounded-xl p-0 backdrop:bg-ink/40"
        onClick={(e) => e.target === dialog.current && dialog.current?.close()}
      >
        <div className="max-h-[90dvh] overflow-y-auto p-5">
          <h2 className="mb-1 text-lg font-semibold">Nuevo proveedor</h2>
          <p className="mb-4 text-sm text-muted">El celular entra inactivo; se activa desde el detalle para que el agente pueda escribirle.</p>
          <SupplierForm
            key={opened}
            endpoint="/api/suppliers/"
            submitLabel="Crear proveedor"
            onSaved={() => {
              dialog.current?.close();
              mutateActive();
            }}
            onCancel={() => dialog.current?.close()}
          />
        </div>
      </dialog>
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
          <SkeletonCards count={4} lines={3} />
        ) : (
          <>
            {/* Chips with their counts; a row that scrolls on the phone. */}
            <div className="-mx-4 overflow-x-auto px-4 sm:mx-0 sm:overflow-visible sm:px-0">
              <div className="flex w-max gap-2 sm:w-auto sm:flex-wrap" role="group" aria-label="Filtrar proveedores">
                {FILTERS.map((f) => {
                  const count = list.filter(f.test(globalPaused)).length;
                  const on = filter === f.key;
                  return (
                    <button
                      key={f.key}
                      type="button"
                      aria-pressed={on}
                      onClick={() => setFilter(f.key)}
                      className={`inline-flex min-h-11 shrink-0 items-center gap-1.5 whitespace-nowrap rounded-full px-3 text-sm ring-1 transition-colors duration-150 sm:min-h-9 ${
                        on ? "bg-ink text-white ring-ink" : "bg-surface ring-line hover:bg-canvas"
                      }`}
                    >
                      {f.label}
                      <span className={`rounded-full px-1.5 text-xs tabular-nums ${on ? "bg-white/20" : "bg-canvas text-muted"}`}>{count}</span>
                    </button>
                  );
                })}
              </div>
            </div>
            {shown.length ? (
              <div className="grid gap-3 md:grid-cols-2 2xl:grid-cols-3">
                {shown.map((supplier) => (
                  <SupplierCard key={supplier.id} supplier={supplier} globalPaused={globalPaused} busy={toggling === supplier.id} onToggle={() => toggleSupplier(supplier)} />
                ))}
              </div>
            ) : (
              <p className="text-sm text-muted">Ningún proveedor en este filtro.</p>
            )}
          </>
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
    <button type="button" role="tab" aria-selected={active} onClick={onClick} className={`rounded-md px-3 py-1.5 text-sm transition-colors duration-150 ${active ? "bg-ink text-white" : "hover:bg-canvas"}`}>
      {children}
    </button>
  );
}

type FilterKey = "all" | "workshop" | "material" | "finished" | "no_whatsapp" | "paused";

// Until the API sends whatsapp_ready: not the plant and with an active number.
const whatsappReady = (s: SupplierListItem) => s.whatsapp_ready ?? (!s.is_in_house && s.active_numbers_count > 0);

const FILTERS: { key: FilterKey; label: string; test: (globalPaused: boolean) => (s: SupplierListItem) => boolean }[] = [
  { key: "all", label: "Todos", test: () => () => true },
  { key: "workshop", label: "Talleres", test: () => (s) => s.kind === "workshop" },
  { key: "material", label: "Insumos", test: () => (s) => s.kind === "material" },
  { key: "finished", label: "Producto terminado", test: () => (s) => s.kind === "finished" },
  { key: "no_whatsapp", label: "Sin WhatsApp", test: () => (s) => !whatsappReady(s) },
  { key: "paused", label: "En pausa", test: (globalPaused) => (s) => whatsappReady(s) && (globalPaused || !!s.agent_paused) },
];

const lastDelivery = new Intl.DateTimeFormat("es-PE", { day: "numeric", month: "short", timeZone: "America/Lima" });

// The whole card opens the supplier (a stretched link under the content), so
// Pausar is a real button beside it, never nested in the link.
function SupplierCard({ supplier, globalPaused, busy, onToggle }: { supplier: SupplierListItem; globalPaused: boolean; busy: boolean; onToggle: () => void }) {
  const ready = whatsappReady(supplier);
  const paused = ready && (globalPaused || !!supplier.agent_paused);
  const total = supplier.purchase_orders_count ?? null;
  return (
    <article className={`relative rounded-xl bg-surface p-4 ring-1 ring-line ${CARD_HOVER}`}>
      <Link href={`/suppliers/${supplier.id}`} className="absolute inset-0 rounded-xl" aria-label={`Ver ${supplier.name}`} />
      <div className="pointer-events-none relative">
        <div className="flex items-start justify-between gap-2">
          <div className="min-w-0">
            <p className="truncate font-semibold">{supplier.name}</p>
            <p className="text-xs text-muted">
              {supplier.kind_display} · {supplier.city}
            </p>
          </div>
          {ready ? (
            <span className="pointer-events-auto flex shrink-0 items-center gap-1.5">
              <WhatsApp size={18} className="text-success" aria-label="WhatsApp activo" />
              <Button
                size="sm"
                busy={busy}
                onClick={(e) => {
                  e.preventDefault();
                  e.stopPropagation();
                  onToggle();
                }}
                title={supplier.agent_paused ? "El agente vuelve a escribirle" : "El agente deja de escribirle"}
              >
                {supplier.agent_paused ? <Play size={14} aria-hidden /> : <Pause size={14} aria-hidden />}
                {supplier.agent_paused ? "Reanudar" : "Pausar"}
              </Button>
            </span>
          ) : (
            <span className="flex shrink-0 items-center gap-1 text-xs font-medium text-danger">
              <WhatsApp size={16} className="text-danger" aria-hidden /> Sin WhatsApp
            </span>
          )}
        </div>
        {paused && (
          <p className="mt-2">
            <Pill tone="warning">Agente en pausa</Pill>
          </p>
        )}
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
        <p className="mt-2 text-xs tabular-nums text-muted">
          Pedidos: {supplier.open_purchase_orders} {supplier.open_purchase_orders === 1 ? "abierto" : "abiertos"}
          {total !== null && ` · ${total} en total`}
          {" · "}Última entrega: {supplier.last_delivered_on ? lastDelivery.format(new Date(`${supplier.last_delivered_on}T12:00:00-05:00`)).replace(".", "") : "—"}
        </p>
        {supplier.weekly_capacity && (
          <p className="mt-0.5 text-xs text-muted">
            Capacidad {supplier.weekly_capacity} u./semana · plazo {supplier.lead_time_days} días
          </p>
        )}
      </div>
    </article>
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
        <Button busy={busy} onClick={() => decide("active")}>
          Aprobar
        </Button>
        <Button disabled={busy} onClick={() => decide("inactive")}>
          Descartar
        </Button>
      </div>
    </article>
  );
}
