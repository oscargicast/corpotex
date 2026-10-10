import { ArrowRight, Map } from "lucide-react";
import Link from "next/link";
import { daysBetween, formatDay, formatMoney } from "@/lib/format";
import type { Decision, DecisionLike } from "@/lib/types";

// Scene for the jury: a workshop cancels and the rest is split (ADR 0024).
// Orange stays reserved for the primary action.
const SPLIT_COLORS = ["bg-accent", "bg-success", "bg-warning", "bg-ink"];

export function RedistributionCard({ decision }: { decision: Decision }) {
  return (
    <article className="rounded-lg bg-surface p-4 ring-1 ring-line">
      <h3 className="font-semibold">Redistribución{decision.orders[0] ? ` · ${decision.orders[0].code}` : ""}</h3>
      <RedistributionBody decision={decision} />
    </article>
  );
}

// Split bar, before and after, and the route link. Also used inside the pending decision.
export function RedistributionBody({ decision, withCancelLine = true }: { decision: DecisionLike; withCancelLine?: boolean }) {
  const { before, after, proposal = [], cancelled } = decision.detail;
  const total = cancelled?.quantity ?? proposal.reduce((sum, p) => sum + p.quantity, 0);
  const shift = before && after ? daysBetween(before.estimated_on, after.estimated_on) : null;
  const costDelta = before && after ? Number(after.total_amount) - Number(before.total_amount) : null;
  const routeHref =
    before?.route_id && after?.route_id ? `/routes?before=${before.route_id}&after=${after.route_id}` : "/routes";

  return (
    <div>
      {cancelled && withCancelLine && (
        <p className="mt-1 text-sm text-muted">
          {cancelled.supplier_name} canceló {cancelled.code} con {cancelled.units_done} de {cancelled.quantity} hechas.
        </p>
      )}

      {total > 0 && (
        <div className="mt-3">
          <div className="flex h-6 overflow-hidden rounded-md text-[11px] font-semibold text-white">
            {cancelled && cancelled.units_done > 0 && (
              <span className="flex items-center justify-center bg-muted" style={{ width: `${(cancelled.units_done / total) * 100}%` }}>
                {cancelled.units_done}
              </span>
            )}
            {proposal.map((p, i) => (
              <span
                key={i}
                className={`flex items-center justify-center ${SPLIT_COLORS[i % SPLIT_COLORS.length]}`}
                style={{ width: `${(p.quantity / total) * 100}%` }}
              >
                {p.quantity}
              </span>
            ))}
          </div>
          <ul className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted">
            {cancelled && <li>■ {cancelled.supplier_name} (hecho)</li>}
            {proposal.map((p, i) => (
              <li key={i}>
                <span className={`mr-1 inline-block size-2 rounded-sm ${SPLIT_COLORS[i % SPLIT_COLORS.length]}`} />
                {p.supplier.name}
              </li>
            ))}
          </ul>
        </div>
      )}

      {after && (
        <dl className="mt-4 grid grid-cols-2 gap-3 text-sm">
          <Delta
            label="Fecha estimada"
            from={before ? formatDay(before.estimated_on) : null}
            to={formatDay(after.estimated_on)}
            change={shift ? `${shift > 0 ? "+" : ""}${shift} días` : null}
            worse={(shift ?? 0) > 0}
          />
          <Delta
            label="Costo total"
            from={before ? formatMoney(before.total_amount) : null}
            to={formatMoney(after.total_amount)}
            change={costDelta ? `${costDelta > 0 ? "+" : "−"}${formatMoney(Math.abs(costDelta))}` : null}
            worse={(costDelta ?? 0) > 0}
          />
        </dl>
      )}

      <Link href={routeHref} className="mt-4 inline-flex items-center gap-1.5 text-sm font-medium text-accent hover:underline">
        <Map size={16} /> Ver la ruta nueva
      </Link>
    </div>
  );
}

function Delta({
  label,
  from,
  to,
  change,
  worse,
}: {
  label: string;
  from: string | null;
  to: string;
  change: string | null;
  worse: boolean;
}) {
  return (
    <div>
      <dt className="text-xs text-muted">{label}</dt>
      <dd className="mt-0.5 flex flex-wrap items-center gap-1.5 font-semibold tabular-nums">
        {from && (
          <>
            <span className="font-normal text-muted line-through">{from}</span>
            <ArrowRight size={14} className="text-muted" />
          </>
        )}
        {to}
      </dd>
      {change && <dd className={`text-xs ${worse ? "text-danger" : "text-success"}`}>{change}</dd>}
    </div>
  );
}
