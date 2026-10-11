"use client";

import { CheckCircle2, Clock, Info, MessageCircleReply } from "lucide-react";
import { useEffect, useState } from "react";
import { ApiError, apiFetch } from "@/lib/api";
import { isOpenRequest, requestedBy } from "@/lib/follow-up";
import { formatDayTime } from "@/lib/format";
import type { FollowUpResult, PurchaseOrderDetail } from "@/lib/types";
import { Button } from "./ui";

// Reactive follow-up (ADR 0027 §6): Comercial, Producción or the Gerente ask
// the agent to check in with a supplier now. The buttons live in the page
// headers; this panel confirms, calls the API and shows the outcome.

export interface FollowUpTarget {
  supplier: string;
  code: string;
  awaiting?: boolean;
}

const time = new Intl.DateTimeFormat("es-PE", { timeZone: "America/Lima", hour: "2-digit", minute: "2-digit", hourCycle: "h23" });
const hhmm = (iso: string | null | undefined) => (iso ? time.format(new Date(iso)) : "");

function listTargets(targets: FollowUpTarget[]): string {
  const parts = targets.map((t) => (targets.length > 1 ? `${t.supplier} (${t.code})` : `${t.supplier} por ${t.code}`));
  return parts.length > 1 ? `${parts.slice(0, -1).join(", ")} y ${parts.at(-1)}` : parts[0];
}

// The dry run's detail minus its first sentence ("Le escribiría a A y B."),
// which the confirmation already says with the codes.
function previewNotes(detail: string | undefined): string {
  return (detail ?? "").replace(/^Le escribiría a .*?\.(\s+(?=A )|$)/s, "").trim();
}

type Outcome = { tone: "success" | "info"; text: string };

// The API answers 202 with one row per open purchase order and `detail`
// saying it in words (who gets a message now, at 07:00, never, or was already
// asked). Rows that hang on an earlier question come back `already_asked`.
function outcomeOf(res: FollowUpResult | null): Outcome {
  const rows = res?.requests ?? [];
  const asking = rows.filter((r) => r.status === "pending");
  const tone = asking.length ? "success" : "info";
  if (res?.detail) return { tone, text: res.detail };
  const at = rows.map((r) => r.asked_at).filter(Boolean).sort()[0];
  return asking.length
    ? { tone, text: "Listo: el agente le escribe ahora. Te avisamos en el asistente cuando conteste." }
    : { tone, text: `Ya se le preguntó${at ? ` a las ${hhmm(at)}` : ""}; te avisamos en el asistente cuando conteste.` };
}

export function FollowUpPanel({ endpoint, targets, onClose, onDone }: { endpoint: string; targets: FollowUpTarget[]; onClose: () => void; onDone: () => void }) {
  const [busy, setBusy] = useState(false);
  const [outcome, setOutcome] = useState<Outcome | null>(null);
  const [error, setError] = useState<string | null>(null);
  // The server's dry run decides who gets a message (the own plant and
  // suppliers without a number don't); undefined while it loads, null when
  // the API can't preview, and then the targets are the fallback.
  const [preview, setPreview] = useState<FollowUpResult | null | undefined>(undefined);

  useEffect(() => {
    let alive = true;
    apiFetch<FollowUpResult>(endpoint, { method: "POST", json: { dry_run: true } })
      .then((res) => alive && setPreview(Array.isArray(res?.requests) ? res : null))
      .catch(() => alive && setPreview(null));
    return () => {
      alive = false;
    };
  }, [endpoint]);

  async function send() {
    setBusy(true);
    setError(null);
    try {
      const res = await apiFetch<FollowUpResult>(endpoint, { method: "POST", json: {} });
      setOutcome(outcomeOf(res));
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

  const rows = preview?.requests;
  const toAsk: FollowUpTarget[] = rows
    ? rows.filter((r) => r.status === "pending").map((r) => ({ supplier: r.supplier_name, code: r.purchase_order.code }))
    : targets.filter((t) => !t.awaiting);
  const waiting: FollowUpTarget[] = rows
    ? rows.filter((r) => r.already_asked).map((r) => ({ supplier: r.supplier_name, code: r.purchase_order.code }))
    : targets.filter((t) => t.awaiting);
  // Only the plant or suppliers without a number: nothing to send.
  const nobody = !!rows && !toAsk.length && !waiting.length;
  const notes = previewNotes(preview?.detail);

  return (
    <div className="rounded-lg bg-warning-soft px-3 py-2 text-sm text-warning" aria-busy={preview === undefined}>
      {preview === undefined ? (
        <p>Revisando a quién escribirle…</p>
      ) : (
        <>
          <p>
            {toAsk.length ? (
              <>
                Se {toAsk.length > 1 ? "les" : "le"} escribirá a <strong>{listTargets(toAsk)}</strong>. ¿Confirmas?
              </>
            ) : nobody ? (
              <>No hay a quién escribirle.</>
            ) : (
              <>Todos ya están esperando respuesta: no se les vuelve a escribir. ¿Quieres que te avisen cuando contesten?</>
            )}
          </p>
          {/* The API's own words: the plant, the 07:00 queue, the earlier question. */}
          {notes && <p className="mt-1 text-xs">{notes}</p>}
          {!preview && waiting.length > 0 && toAsk.length > 0 && (
            <p className="mt-1 text-xs">
              {waiting.map((t) => t.code).join(", ")} ya {waiting.length > 1 ? "están" : "está"} esperando respuesta: no se {waiting.length > 1 ? "les" : "le"} vuelve a escribir.
            </p>
          )}
        </>
      )}
      <div className="mt-2 flex flex-wrap gap-2">
        {!nobody && (
          <Button kind="dark" className="py-1" busy={busy} disabled={preview === undefined} onClick={send}>
            {toAsk.length ? "Pedir avance" : "Avisarme"}
          </Button>
        )}
        <Button className="py-1" disabled={busy} onClick={onClose}>
          {nobody ? "Cerrar" : "Cancelar"}
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
// (the agent's summary, else the first progress report after the question).
export function FollowUpStatus({ po }: { po: PurchaseOrderDetail }) {
  const pending = po.pending_follow_up;
  const last = po.last_follow_up;
  const askedAt = pending?.asked_at ?? last?.at ?? null;
  const total = Number(po.total_units);
  const report = askedAt
    ? [...po.progress_reports].filter((r) => r.reported_at > askedAt).sort((a, b) => a.reported_at.localeCompare(b.reported_at))[0]
    : undefined;

  const lines: { icon: typeof Clock; text: string; tone: string }[] = [];
  if (isOpenRequest(pending)) {
    const asked = pending.status === "asked" && pending.asked_at ? ` · se le preguntó a las ${hhmm(pending.asked_at)}` : " · el agente le escribe en un momento";
    lines.push({ icon: Clock, tone: "text-warning", text: `Avance pedido por ${requestedBy(pending)} a las ${hhmm(pending.requested_at)}${asked} · esperando respuesta` });
  } else if (pending?.status === "answered") {
    lines.push({ icon: Clock, tone: "text-muted", text: `Avance pedido por ${requestedBy(pending)} a las ${hhmm(pending.requested_at)}` });
  } else if (last?.awaiting_reply) {
    const kind = last.kind === "reminder" ? "Recordatorio" : last.kind === "requested" ? "Pedido de avance" : "Seguimiento";
    lines.push({ icon: Clock, tone: "text-warning", text: `${kind} del agente a las ${hhmm(last.at)} · esperando respuesta` });
  }
  if (pending?.status === "answered" && pending.answer_summary) {
    lines.push({ icon: MessageCircleReply, tone: "text-success", text: `Respondió a las ${hhmm(pending.answered_at)}: ${pending.answer_summary}` });
  } else if (report) {
    lines.push({ icon: MessageCircleReply, tone: "text-success", text: `Respondió a las ${hhmm(report.reported_at)}: ${report.units_done} de ${total}` });
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
