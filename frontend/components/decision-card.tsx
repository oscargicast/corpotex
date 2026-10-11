"use client";

import { ArrowLeftRight, Check, CircleCheck, X, XCircle } from "lucide-react";
import Link from "next/link";
import { useRef, useState } from "react";
import { ApiError, apiFetch } from "@/lib/api";
import { formatDay, formatMoney, formatScore, num } from "@/lib/format";
import { DECISION_KIND, candidateSupplier, type DecisionAction, type DecisionLike, type ProposalItem } from "@/lib/types";
import { ClampedText } from "./clamped-text";
import { RedistributionBody } from "./redistribution-card";
import { Radar } from "./radar";
import { ConfirmDialog } from "./confirm-dialog";
import { Button, Pill } from "./ui";

interface ResolveBody {
  action: DecisionAction;
  supplier_id?: number;
  purchase_order_id?: number;
}

export function DecisionCard({ decision, onResolved }: { decision: DecisionLike; onResolved: () => void }) {
  const [busy, setBusy] = useState(false);
  const [action, setAction] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [approving, setApproving] = useState(false);
  const dialog = useRef<HTMLDialogElement>(null);
  const proposal = decision.detail.proposal ?? [];
  const after = decision.detail.after;

  async function resolve(body: ResolveBody) {
    setBusy(true);
    setAction(body.action);
    setError(null);
    try {
      await apiFetch(`/api/manager/decisions/${decision.id}/`, { method: "POST", json: body });
      dialog.current?.close();
      setApproving(false);
      onResolved();
    } catch (err) {
      setError(err instanceof ApiError && err.status === 409 ? "Esta decisión ya se resolvió." : "No se pudo guardar. Inténtalo de nuevo.");
    } finally {
      setBusy(false);
    }
  }

  // Less text (Oscar, 11/10): one line of context, the agent's summary in two
  // lines, the figures big, the proposal folded.
  const units = proposal.reduce((sum, item) => sum + (num(item.quantity) ?? 0), 0);
  const figures = decision.detail.cancelled
    ? []
    : [
        units > 0 && { label: "Unidades", value: `${units.toLocaleString("es-PE")} u.` },
        after?.total_amount && { label: "Total", value: formatMoney(after.total_amount, after.currency ?? proposal[0]?.currency) },
        after?.estimated_on && { label: "Fecha estimada", value: formatDay(after.estimated_on) },
      ].filter((f): f is { label: string; value: string } => !!f);

  return (
    <article className="rounded-lg bg-surface p-4 ring-1 ring-line">
      <div className="flex min-w-0 items-center gap-2">
        <Pill tone="warning">{decision.kind_display ?? DECISION_KIND[decision.kind] ?? decision.kind}</Pill>
        <span className="min-w-0 truncate text-sm">
          {(decision.orders ?? []).map((order, i) => (
            <span key={order.id}>
              {i > 0 && " · "}
              <Link href={`/orders/${order.id}`} className="font-medium text-accent hover:underline">
                {order.code}
              </Link>{" "}
              <span className="text-muted">{order.customer_name}</span>
            </span>
          ))}
        </span>
      </div>
      {decision.summary && <ClampedText text={decision.summary} className="mt-2 text-sm" />}

      {decision.detail.cancelled ? (
        <RedistributionBody decision={decision} withCancelLine={false} />
      ) : (
        <>
          {figures.length > 0 && (
            <dl className={`mt-3 grid gap-2 ${figures.length === 3 ? "grid-cols-3" : figures.length === 2 ? "grid-cols-2" : "grid-cols-1"}`}>
              {figures.map((f) => (
                <div key={f.label} className="rounded-lg bg-canvas px-3 py-2">
                  <dt className="text-xs text-muted">{f.label}</dt>
                  <dd className="text-lg font-bold tabular-nums sm:text-xl">{f.value}</dd>
                </div>
              ))}
            </dl>
          )}
          {proposal.length > 0 && (
            <details className="mt-2 text-sm">
              <summary className="inline-flex min-h-11 items-center text-xs font-medium text-accent sm:min-h-0">
                Ver propuesta ({proposal.length} {proposal.length === 1 ? "proveedor" : "proveedores"})
              </summary>
              <ul className="mt-1 space-y-1">
                {proposal.map((item, i) => (
                  <li key={i} className="flex flex-wrap justify-between gap-x-3 rounded-md bg-canvas px-3 py-1.5">
                    <span>
                      <strong>{item.supplier.name}</strong> · {Number(item.quantity)} u.
                    </span>
                    <span className="tabular-nums text-muted">{formatMoney(item.unit_price, item.currency)} c/u</span>
                  </li>
                ))}
              </ul>
            </details>
          )}
        </>
      )}

      {error && (
        <p className="mt-2 text-sm text-danger" role="alert">
          {error}
        </p>
      )}
      <div className="mt-3 flex flex-wrap gap-2">
        <Button disabled={busy} busy={busy && action === "reject"} onClick={() => resolve({ action: "reject" })}>
          <XCircle size={16} aria-hidden /> Rechazar
        </Button>
        {proposal.some((item) => (item.candidates?.length ?? 0) > 1) && (
          <Button disabled={busy} onClick={() => dialog.current?.showModal()}>
            <ArrowLeftRight size={16} aria-hidden /> Cambiar proveedor
          </Button>
        )}
        <Button kind="primary" disabled={busy} busy={busy && action === "approve"} onClick={() => setApproving(true)}>
          <CircleCheck size={16} aria-hidden /> Aprobar
        </Button>
      </div>

      {approving && (
        <ConfirmDialog
          title={decision.kind_display ?? DECISION_KIND[decision.kind] ?? "Aprobar"}
          text={approveText(decision, proposal)}
          busy={busy}
          error={error}
          confirm={{ label: "Aprobar", icon: <CircleCheck size={16} aria-hidden />, kind: "primary" }}
          onConfirm={() => resolve({ action: "approve" })}
          onClose={() => setApproving(false)}
        />
      )}

      <dialog
        ref={dialog}
        className="m-auto w-[min(40rem,calc(100vw-2rem))] rounded-xl p-0 backdrop:bg-ink/40"
        onClick={(e) => e.target === dialog.current && dialog.current?.close()}
      >
        <ChangeSupplier
          proposal={proposal}
          busy={busy}
          onPick={(item, supplierId) =>
            resolve({
              action: "change_supplier",
              supplier_id: supplierId,
              purchase_order_id: item.purchase_order?.id,
            })
          }
          onClose={() => dialog.current?.close()}
        />
      </dialog>
    </article>
  );
}

// What approving does, in one line: who the agent writes to, or what it confirms.
function approveText(decision: DecisionLike, proposal: ProposalItem[]): string {
  const names = [...new Set(proposal.map((item) => item.supplier.name))];
  const list = names.length > 1 ? `${names.slice(0, -1).join(", ")} y ${names.at(-1)}` : names[0];
  if (decision.detail.cancelled) return `Se aprueba la redistribución: el agente le escribe a ${list ?? "los talleres nuevos"} con el primer contacto por WhatsApp.`;
  if (decision.kind === "price") return "Se acepta el precio propuesto y el agente se lo confirma al proveedor por WhatsApp.";
  if (decision.kind === "terms") return "Se aceptan los términos y el agente se los confirma al proveedor por WhatsApp.";
  if (list) return `Se aprueba la asignación a ${list}: el agente manda el primer contacto por WhatsApp a los proveedores externos.`;
  return "Se aprueba la decisión y el agente sigue la conversación con el proveedor.";
}

function ChangeSupplier({
  proposal,
  busy,
  onPick,
  onClose,
}: {
  proposal: ProposalItem[];
  busy: boolean;
  onPick: (item: ProposalItem, supplierId: number) => void;
  onClose: () => void;
}) {
  // With more than one purchase order, pick which one changes first.
  const [index, setIndex] = useState(0);
  const item = proposal[index];
  if (!item) return null;

  return (
    <div className="p-5">
      <h3 className="text-lg font-semibold">Cambiar proveedor</h3>
      {proposal.length > 1 && (
        <div className="mt-3 flex flex-wrap gap-2" role="tablist">
          {proposal.map((p, i) => (
            <button
              key={i}
              type="button"
              role="tab"
              aria-selected={i === index}
              onClick={() => setIndex(i)}
              className={`rounded-md px-3 py-1.5 text-sm ring-1 ${i === index ? "bg-ink text-white ring-ink" : "ring-line"}`}
            >
              {p.purchase_order?.code ?? `Parte ${i + 1}`} · {Number(p.quantity)} u.
            </button>
          ))}
        </div>
      )}
      <p className="mt-3 text-sm text-muted">Ranking del matching para esta parte. El elegido hoy es {item.supplier.name}.</p>
      <ul className="mt-3 max-h-[60vh] space-y-3 overflow-y-auto">
        {(item.candidates ?? []).map((candidate) => {
          const supplier = candidateSupplier(candidate);
          const current = supplier.id === item.supplier.id;
          return (
            <li key={supplier.id} className="flex gap-3 rounded-lg p-3 ring-1 ring-line">
              <Radar values={candidate.scores ?? {}} size={150} className="shrink-0" title={`Criterios de ${supplier.name}`} />
              <div className="min-w-0 flex-1">
                <p className="font-semibold">
                  {supplier.name} <span className="font-normal text-muted">· {formatScore(candidate.score)} pts</span>
                </p>
                <p className="text-sm tabular-nums text-muted">
                  {formatMoney(candidate.unit_price, item.currency)} c/u · carga {candidate.load_pct} %
                </p>
                <p className="mt-2 text-xs text-muted">{candidate.rationale}</p>
                {current ? (
                  <p className="mt-2 text-xs font-medium">Elegido ahora</p>
                ) : (
                  <Button className="mt-2" busy={busy} onClick={() => onPick(item, supplier.id)}>
                    <Check size={16} aria-hidden /> Elegir {supplier.name}
                  </Button>
                )}
              </div>
            </li>
          );
        })}
      </ul>
      <div className="mt-4 text-right">
        <Button onClick={onClose}>
          <X size={16} aria-hidden /> Cerrar
        </Button>
      </div>
    </div>
  );
}
