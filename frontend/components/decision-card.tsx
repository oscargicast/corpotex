"use client";

import Link from "next/link";
import { useRef, useState } from "react";
import { ApiError, apiFetch } from "@/lib/api";
import { formatDay, formatMoney, formatScore } from "@/lib/format";
import { DECISION_KIND, candidateSupplier, type DecisionAction, type DecisionLike, type ProposalItem } from "@/lib/types";
import { RedistributionBody } from "./redistribution-card";
import { Button, CRITERIA_LABELS, Pill, ScoreBar } from "./ui";

interface ResolveBody {
  action: DecisionAction;
  supplier_id?: number;
  purchase_order_id?: number;
}

export function DecisionCard({ decision, onResolved }: { decision: DecisionLike; onResolved: () => void }) {
  const [busy, setBusy] = useState(false);
  const [action, setAction] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
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
      onResolved();
    } catch (err) {
      setError(err instanceof ApiError && err.status === 409 ? "Esta decisión ya se resolvió." : "No se pudo guardar. Inténtalo de nuevo.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <article className="rounded-lg bg-surface p-4 ring-1 ring-line">
      <div className="flex flex-wrap items-center gap-2">
        <Pill tone="warning">{decision.kind_display ?? DECISION_KIND[decision.kind] ?? decision.kind}</Pill>
        {(decision.orders ?? []).map((order) => (
          <Link key={order.id} href={`/orders/${order.id}`} className="text-xs font-medium text-accent hover:underline">
            {order.code} · {order.customer_name}
          </Link>
        ))}
      </div>
      <p className="mt-2 text-sm">{decision.summary}</p>

      {decision.detail.cancelled ? (
        <RedistributionBody decision={decision} withCancelLine={false} />
      ) : (
        proposal.length > 0 && (
        <ul className="mt-3 space-y-1 text-sm">
          {proposal.map((item, i) => (
            <li key={i} className="flex flex-wrap justify-between gap-x-3 rounded-md bg-canvas px-3 py-1.5">
              <span>
                <strong>{item.supplier.name}</strong> · {Number(item.quantity)} u.
              </span>
              <span className="tabular-nums text-muted">{formatMoney(item.unit_price, item.currency)} c/u</span>
            </li>
          ))}
        </ul>
        )
      )}
      {after && !decision.detail.cancelled && (
        <p className="mt-2 text-xs text-muted">
          {/* A price decision carries only the new total; assignments also move the date. */}
          {[after.estimated_on && `Nueva fecha estimada ${formatDay(after.estimated_on)}`, after.total_amount && `total ${formatMoney(after.total_amount, after.currency ?? proposal[0]?.currency)}`]
            .filter(Boolean)
            .join(" · ")}
        </p>
      )}

      {error && (
        <p className="mt-2 text-sm text-danger" role="alert">
          {error}
        </p>
      )}
      <div className="mt-3 flex flex-wrap gap-2">
        <Button kind="primary" disabled={busy} busy={busy && action === "approve"} onClick={() => resolve({ action: "approve" })}>
          Aprobar
        </Button>
        <Button disabled={busy} busy={busy && action === "reject"} onClick={() => resolve({ action: "reject" })}>
          Rechazar
        </Button>
        {proposal.some((item) => (item.candidates?.length ?? 0) > 1) && (
          <Button disabled={busy} onClick={() => dialog.current?.showModal()}>
            Cambiar proveedor
          </Button>
        )}
      </div>

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
            <li key={supplier.id} className="rounded-lg p-3 ring-1 ring-line">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <p className="font-semibold">
                  {supplier.name} <span className="font-normal text-muted">· {formatScore(candidate.score)} pts</span>
                </p>
                <span className="text-sm tabular-nums text-muted">
                  {formatMoney(candidate.unit_price, item.currency)} c/u · carga {candidate.load_pct} %
                </span>
              </div>
              <div className="mt-2 space-y-1">
                {Object.entries(candidate.scores).map(([key, value]) => (
                  <ScoreBar key={key} label={CRITERIA_LABELS[key] ?? key} value={value} />
                ))}
              </div>
              <p className="mt-2 text-xs text-muted">{candidate.rationale}</p>
              {current ? (
                <p className="mt-2 text-xs font-medium">Elegido ahora</p>
              ) : (
                <Button kind="dark" className="mt-2" busy={busy} onClick={() => onPick(item, supplier.id)}>
                  Elegir {supplier.name}
                </Button>
              )}
            </li>
          );
        })}
      </ul>
      <div className="mt-4 text-right">
        <Button onClick={onClose}>Cerrar</Button>
      </div>
    </div>
  );
}
