"use client";

import { Bell, CheckCircle2, Clock, Info, MessageCircleReply, X } from "lucide-react";
import { useEffect, useState } from "react";
import { ApiError, apiFetch } from "@/lib/api";
import { isOpenRequest, requestedBy } from "@/lib/follow-up";
import { formatDayTime } from "@/lib/format";
import type { FollowUpResult, PurchaseOrderDetail } from "@/lib/types";
import { ConfirmDialog } from "./confirm-dialog";
import { WhatsApp } from "./icons";
import type { ButtonKind } from "./ui";

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

// `title` is the label of the button that opened it ("Pedir avance" or
// "Pedir avance a todos") and `kind` its look: the dialog repeats both.
export function FollowUpPanel({
  endpoint,
  targets,
  title = "Pedir avance",
  kind = "primary",
  onClose,
  onDone,
}: {
  endpoint: string;
  targets: FollowUpTarget[];
  title?: string;
  kind?: ButtonKind;
  onClose: () => void;
  onDone: () => void;
}) {
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
        <button type="button" onClick={onClose} className="inline-flex min-h-11 items-center gap-1 text-xs underline sm:min-h-0">
          <X size={12} aria-hidden /> Cerrar
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
  const loading = preview === undefined;
  const asks = loading || toAsk.length > 0;
  // The API's own words (the plant, the 07:00 queue, the earlier question),
  // else what the page knows about who is already waiting.
  const notes =
    previewNotes(preview?.detail) ||
    (!preview && waiting.length > 0 && toAsk.length > 0
      ? `${waiting.map((t) => t.code).join(", ")} ya ${waiting.length > 1 ? "están" : "está"} esperando respuesta: no se ${waiting.length > 1 ? "les" : "le"} vuelve a escribir.`
      : "");

  return (
    <ConfirmDialog
      title={asks ? title : nobody ? "Nadie a quien escribir" : "Avisarme cuando contesten"}
      text={
        loading ? (
          "Revisando a quién escribirle…"
        ) : toAsk.length ? (
          <>
            El agente {toAsk.length > 1 ? "les" : "le"} escribe ahora por WhatsApp a <strong>{listTargets(toAsk)}</strong> para pedir el avance.
          </>
        ) : nobody ? (
          "No hay a quién escribirle: la planta no recibe mensajes y el resto no tiene número activo."
        ) : (
          "Todos ya están esperando respuesta: no se les vuelve a escribir. Te avisamos en el asistente cuando contesten."
        )
      }
      note={notes || undefined}
      busy={busy}
      error={error}
      confirm={
        nobody
          ? undefined
          : asks
            ? { label: title, icon: <WhatsApp size={16} aria-hidden />, kind, disabled: loading }
            : { label: "Avisarme", icon: <Bell size={16} aria-hidden /> }
      }
      cancelLabel={nobody ? "Cerrar" : "Cancelar"}
      onConfirm={send}
      onClose={onClose}
    />
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
