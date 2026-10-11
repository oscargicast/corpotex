"use client";

import { CheckCircle2, Clock, Info, MessageCircleReply } from "lucide-react";
import { useState } from "react";
import { ApiError, apiFetch } from "@/lib/api";
import { formatDayTime } from "@/lib/format";
import { type FollowUpRequestResponse, type PurchaseOrderDetail, ROLE_LABELS, type Role } from "@/lib/types";
import { Button } from "./ui";

// Reactive follow-up (ADR 0027 §6): Comercial, Producción or the Gerente ask
// the agent to check in with a supplier now. The buttons live in the page
// headers; this panel confirms, calls the API and shows the outcome.

export interface FollowUpTarget {
  supplier: string;
  code: string;
  awaiting?: boolean;
}

const time = new Intl.DateTimeFormat("es-PE", { timeZone: "America/Lima", hour: "2-digit", minute: "2-digit" });
const hhmm = (iso: string | null | undefined) => (iso ? time.format(new Date(iso)) : "");

function listTargets(targets: FollowUpTarget[]): string {
  const parts = targets.map((t) => (targets.length > 1 ? `${t.supplier} (${t.code})` : `${t.supplier} por ${t.code}`));
  return parts.length > 1 ? `${parts.slice(0, -1).join(", ")} y ${parts.at(-1)}` : parts[0];
}

type Outcome = { tone: "success" | "info"; text: string };

// The API answers 202 with the requests it created; a request that hung on an
// earlier question comes back "asked" with that question's time.
function outcomeOf(res: FollowUpRequestResponse | null, startedAt: number): Outcome {
  const items = Array.isArray(res) ? res : (res?.requests ?? res?.created ?? []);
  const detail = !Array.isArray(res) && typeof res?.detail === "string" ? res.detail : null;
  const already = items.filter((i) => i.already_asked || (i.status === "asked" && i.asked_at && new Date(i.asked_at).getTime() < startedAt - 5000));
  if (items.length && already.length === items.length) {
    const at = already.map((i) => i.asked_at).filter(Boolean).sort()[0];
    return { tone: "info", text: detail ?? `Ya se le preguntó${at ? ` a las ${hhmm(at)}` : ""}; te avisamos en el asistente cuando conteste.` };
  }
  const waiting = already.map((i) => i.purchase_order?.code).filter(Boolean);
  return {
    tone: "success",
    text: `${detail ?? "Listo: el agente le escribe ahora. Te avisamos en el asistente cuando conteste."}${waiting.length ? ` ${waiting.join(", ")} ya esperaba${waiting.length > 1 ? "n" : ""} respuesta.` : ""}`,
  };
}

export function FollowUpPanel({ endpoint, targets, onClose, onDone }: { endpoint: string; targets: FollowUpTarget[]; onClose: () => void; onDone: () => void }) {
  const [busy, setBusy] = useState(false);
  const [outcome, setOutcome] = useState<Outcome | null>(null);
  const [error, setError] = useState<string | null>(null);
  const toAsk = targets.filter((t) => !t.awaiting);
  const waiting = targets.filter((t) => t.awaiting);

  async function send() {
    setBusy(true);
    setError(null);
    const startedAt = Date.now();
    try {
      const res = await apiFetch<FollowUpRequestResponse>(endpoint, { method: "POST", json: {} });
      setOutcome(outcomeOf(res, startedAt));
      onDone();
    } catch (err) {
      const detail = err instanceof ApiError ? (err.body as { detail?: string } | null)?.detail : null;
      setError(detail ?? "No se pudo pedir el avance. Inténtalo de nuevo.");
    } finally {
      setBusy(false);
    }
  }

  if (outcome) {
    const Icon = outcome.tone === "info" ? Info : CheckCircle2;
    return (
      <div className={`flex flex-wrap items-center gap-2 rounded-lg px-3 py-2 text-sm ${outcome.tone === "info" ? "bg-accent/10 text-accent" : "bg-success-soft text-success"}`} role="status">
        <Icon size={16} className="shrink-0" aria-hidden />
        <span className="flex-1">{outcome.text}</span>
        <button type="button" onClick={onClose} className="text-xs underline">
          Cerrar
        </button>
      </div>
    );
  }

  return (
    <div className="rounded-lg bg-warning-soft px-3 py-2 text-sm text-warning">
      <p>
        {toAsk.length ? (
          <>
            Se {toAsk.length > 1 ? "les" : "le"} escribirá a <strong>{listTargets(toAsk)}</strong>. ¿Confirmas?
          </>
        ) : (
          <>Todos los pedidos ya están esperando respuesta: no se les vuelve a escribir. ¿Quieres que te avisen cuando contesten?</>
        )}
      </p>
      {waiting.length > 0 && toAsk.length > 0 && (
        <p className="mt-1 text-xs">
          {waiting.map((t) => t.code).join(", ")} ya {waiting.length > 1 ? "están" : "está"} esperando respuesta: no se {waiting.length > 1 ? "les" : "le"} vuelve a escribir.
        </p>
      )}
      <div className="mt-2 flex flex-wrap gap-2">
        <Button kind="dark" className="py-1" busy={busy} onClick={send}>
          {toAsk.length ? "Pedir avance" : "Avisarme"}
        </Button>
        <Button className="py-1" disabled={busy} onClick={onClose}>
          Cancelar
        </Button>
      </div>
      {error && (
        <p className="mt-1 text-danger" role="alert">
          {error}
        </p>
      )}
    </div>
  );
}

// Waiting state on the purchase order: who asked and when, then the answer
// (the first progress report after the question).
export function FollowUpStatus({ po }: { po: PurchaseOrderDetail }) {
  const pending = po.pending_follow_up;
  const last = po.last_follow_up;
  const askedAt = pending?.asked_at ?? last?.at ?? null;
  const total = Number(po.total_units);
  const answer = askedAt
    ? [...po.progress_reports].filter((r) => r.reported_at > askedAt).sort((a, b) => a.reported_at.localeCompare(b.reported_at))[0]
    : undefined;

  const lines: { icon: typeof Clock; text: string; tone: string }[] = [];
  if (pending && pending.status !== "answered" && pending.status !== "skipped") {
    const who = ROLE_LABELS[pending.requested_by_role as Role] ?? pending.requested_by_role;
    const asked = pending.status === "asked" && pending.asked_at ? ` · se le preguntó a las ${hhmm(pending.asked_at)}` : " · el agente le escribe en un momento";
    lines.push({ icon: Clock, tone: "text-warning", text: `Avance pedido por ${who} a las ${hhmm(pending.requested_at)}${asked} · esperando respuesta` });
  } else if (last?.awaiting_reply) {
    const kind = last.kind === "reminder" ? "Recordatorio" : last.kind === "requested" ? "Pedido de avance" : "Seguimiento";
    lines.push({ icon: Clock, tone: "text-warning", text: `${kind} del agente a las ${hhmm(last.at)} · esperando respuesta` });
  }
  if (answer) {
    lines.push({ icon: MessageCircleReply, tone: "text-success", text: `Respondió a las ${hhmm(answer.reported_at)}: ${answer.units_done} de ${total}` });
  } else if (!lines.length && last) {
    lines.push({ icon: MessageCircleReply, tone: "text-muted", text: `Último seguimiento ${formatDayTime(last.at)}` });
  }
  if (!lines.length) return null;

  return (
    <ul className="mt-4 space-y-1 border-t border-line pt-3 text-sm">
      {lines.map(({ icon: Icon, text, tone }) => (
        <li key={text} className={`flex items-start gap-2 ${tone}`}>
          <Icon size={16} className="mt-0.5 shrink-0" aria-hidden />
          <span>{text}</span>
        </li>
      ))}
    </ul>
  );
}
