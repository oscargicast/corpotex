import { Check, X } from "lucide-react";
import { formatDayTime } from "@/lib/format";
import type { StatusHistoryEntry } from "@/lib/types";

type Flow = "order" | "purchase_order";

interface Step {
  status: string;
  label: string;
  next: string; // what happens from here, shown on the current step
}

// Happy paths. Exits (cancelled, declined_by_supplier, cancelled_by_supplier) are
// not steps: they paint red the step where the flow left the path.
const FLOWS: Record<Flow, Step[]> = {
  order: [
    { status: "registered", label: "Registrada", next: "la IA arma la ficha técnica contra el inventario" },
    { status: "broken_down", label: "Con ficha técnica", next: "Producción revisa y aprueba la ficha técnica" },
    { status: "confirmed", label: "Confirmada", next: "el Gerente aprueba los pedidos a proveedores" },
    { status: "sourcing", label: "En abastecimiento", next: "llegan los insumos y los talleres confirman" },
    { status: "in_production", label: "En producción", next: "corte, confección y acabado" },
    { status: "ready", label: "Lista", next: "entrega al cliente" },
    { status: "delivered", label: "Entregada", next: "" },
  ],
  purchase_order: [
    { status: "suggested", label: "Sugerido", next: "el Gerente aprueba o cambia el proveedor" },
    { status: "approved", label: "Aprobado", next: "el agente le escribe al proveedor" },
    { status: "negotiating", label: "En negociación", next: "el agente acuerda precio y fecha con el proveedor" },
    { status: "confirmed", label: "Confirmado", next: "pago del adelanto y arranque" },
    { status: "in_progress", label: "En proceso", next: "el proveedor reporta avances hasta entregar" },
    { status: "delivered", label: "Entregado", next: "" },
  ],
};

const EXIT_LABEL: Record<string, string> = {
  cancelled: "Cancelado",
  declined_by_supplier: "Rechazado por el proveedor",
  cancelled_by_supplier: "Cancelado por el proveedor",
};

// Where an exit lands when the history does not say.
const EXIT_FALLBACK: Record<string, string> = {
  cancelled: "",
  declined_by_supplier: "negotiating",
  cancelled_by_supplier: "in_progress",
};

// Spanish label of a purchase-order status, for refs that send only `status`.
export function purchaseOrderStatusLabel(status: string): string {
  return FLOWS.purchase_order.find((step) => step.status === status)?.label ?? EXIT_LABEL[status] ?? status;
}

const ACTOR: Record<string, string> = { system: "sistema", agent: "agente", user: "usuario", manager: "Gerente" };

export function StatusTimeline({
  flow,
  status,
  history = [],
  statusDisplay,
}: {
  flow: Flow;
  status: string;
  history?: StatusHistoryEntry[];
  statusDisplay?: string;
}) {
  let steps = FLOWS[flow];
  const byStatus = new Map(history.map((h) => [h.status, h]));
  const exit = EXIT_LABEL[status] ? status : null;

  // In-house workshop: approved goes straight to confirmed, so negotiating is not a step.
  if (flow === "purchase_order" && !byStatus.has("negotiating") && status !== "negotiating") {
    const idx = steps.findIndex((s) => s.status === "confirmed");
    const passedConfirmed = byStatus.has("confirmed") || steps.findIndex((s) => s.status === status) >= idx;
    if (passedConfirmed) steps = steps.filter((s) => s.status !== "negotiating");
  }

  // The step the flow is on, or where it left the path.
  let currentIndex = steps.findIndex((s) => s.status === status);
  if (exit) {
    const lastOnPath = [...history].reverse().find((h) => steps.some((s) => s.status === h.status))?.status ?? EXIT_FALLBACK[exit];
    currentIndex = Math.max(0, steps.findIndex((s) => s.status === lastOnPath));
  }
  if (currentIndex < 0) currentIndex = 0;
  const exitEntry = exit ? byStatus.get(exit) : undefined;
  const finished = status === "delivered";

  return (
    <ol className="flex flex-col gap-0 md:flex-row md:items-start" aria-label="Estados">
      {steps.map((step, i) => {
        const entry = byStatus.get(step.status);
        const isCurrent = i === currentIndex;
        const done = i < currentIndex || (isCurrent && finished);
        const failed = isCurrent && !!exit;
        const future = i > currentIndex;
        const dot = failed
          ? "bg-danger text-white ring-danger"
          : done
            ? "bg-success text-white ring-success"
            : isCurrent
              ? "bg-ink text-white ring-ink"
              : "bg-surface text-muted ring-line";
        const line = i < currentIndex ? "bg-success" : "bg-line";
        return (
          <li key={step.status} className="relative flex gap-3 md:flex-1 md:flex-col md:gap-2">
            {/* Connector to the next step: vertical on phones, horizontal from md. */}
            {i < steps.length - 1 && (
              <span aria-hidden className={`absolute left-[13px] top-7 h-[calc(100%-1.75rem)] w-0.5 md:left-[calc(50%+14px)] md:top-[13px] md:h-0.5 md:w-[calc(100%-28px)] ${line}`} />
            )}
            <span className={`relative z-10 flex size-7 shrink-0 items-center justify-center rounded-full text-xs font-bold ring-2 md:mx-auto ${dot}`}>
              {failed ? <X size={14} /> : done ? <Check size={14} /> : i + 1}
            </span>
            <div className={`min-w-0 pb-4 md:pb-0 md:text-center ${future ? "text-muted" : ""}`}>
              <p className={`text-sm ${isCurrent ? "font-semibold" : "font-medium"}`}>
                {/* The order's broken_down reads "Con ficha técnica" (ADR 0029), whatever the history says. */}
                {failed ? (exitEntry?.status_display ?? statusDisplay ?? EXIT_LABEL[exit!]) : flow === "order" && step.status === "broken_down" ? step.label : (entry?.status_display ?? step.label)}
              </p>
              {failed && (
                <p className="text-xs text-danger">
                  Salió en «{step.label}»{exitEntry?.note ? `: ${exitEntry.note}` : ""}
                </p>
              )}
              {entry && !failed && (
                <p className="text-xs text-muted">
                  {formatDayTime(entry.at)}
                  {entry.actor ? ` · ${ACTOR[entry.actor] ?? entry.actor}` : ""}
                </p>
              )}
              {failed && exitEntry && <p className="text-xs text-muted">{formatDayTime(exitEntry.at)}{exitEntry.actor ? ` · ${ACTOR[exitEntry.actor] ?? exitEntry.actor}` : ""}</p>}
              {isCurrent && !exit && !finished && step.next && <p className="mt-0.5 text-xs text-accent">Siguiente: {step.next}</p>}
              {entry?.note && !failed && <p className="text-xs text-muted">{entry.note}</p>}
            </div>
          </li>
        );
      })}
    </ol>
  );
}
