"use client";

import { CheckCircle2 } from "lucide-react";
import { useSyncExternalStore } from "react";
import { WhatsApp } from "./icons";

// The moment a message really leaves by WhatsApp (Oscar, 11/10): a toast that
// says "Enviando por WhatsApp…" with the glyph in motion for 1.2 s, then
// "Enviado a {proveedor}". Callers hand over the request; the recipients come
// back with it (none or a failure: the toast just goes away). One host in the
// Shell renders them; reduced motion keeps the toast and drops the animation.

interface Toast {
  id: number;
  phase: "sending" | "sent";
  to: string;
}

const MIN_SENDING_MS = 1200;
const SENT_MS = 4000;

let toasts: Toast[] = [];
let nextId = 1;
const listeners = new Set<() => void>();

function emit(next: Toast[]) {
  toasts = next;
  listeners.forEach((l) => l());
}
const subscribe = (l: () => void) => {
  listeners.add(l);
  return () => listeners.delete(l);
};
const snapshot = () => toasts;
const EMPTY: Toast[] = [];
const serverSnapshot = () => EMPTY;

export function joinNames(names: string[]): string {
  const unique = [...new Set(names.filter(Boolean))];
  return unique.length > 1 ? `${unique.slice(0, -1).join(", ")} y ${unique.at(-1)}` : (unique[0] ?? "");
}

// `request` resolves to the names the agent writes to; empty or rejected
// means nothing went out.
export function whatsappSending(request: Promise<string[] | null | undefined>): void {
  const id = nextId++;
  emit([...toasts, { id, phase: "sending", to: "" }]);
  const started = Date.now();
  const remove = () => emit(toasts.filter((t) => t.id !== id));
  request
    .then((names) => {
      const to = joinNames(names ?? []);
      const wait = Math.max(0, MIN_SENDING_MS - (Date.now() - started));
      setTimeout(() => {
        if (!to) return remove();
        emit(toasts.map((t) => (t.id === id ? { ...t, phase: "sent", to } : t)));
        setTimeout(remove, SENT_MS);
      }, wait);
    })
    .catch(remove);
}

export function WhatsAppToastHost() {
  const list = useSyncExternalStore(subscribe, snapshot, serverSnapshot);
  if (!list.length) return null;
  return (
    <div className="pointer-events-none fixed inset-x-4 bottom-20 z-50 flex flex-col items-center gap-2 md:bottom-6" role="status" aria-live="polite">
      {list.map((t) => (
        <div
          key={t.id}
          className={`magic-in flex items-center gap-2 rounded-full px-4 py-2 text-sm font-medium shadow-lg ring-1 ${
            t.phase === "sent" ? "bg-success-soft text-success ring-success/30" : "bg-surface text-ink ring-line"
          }`}
        >
          {t.phase === "sent" ? (
            <CheckCircle2 size={18} className="shrink-0" aria-hidden />
          ) : (
            <span className="relative flex size-5 shrink-0 items-center justify-center">
              <span className="wa-ring absolute inset-0 rounded-full bg-success/30" aria-hidden />
              <WhatsApp size={18} className="wa-send relative text-success" aria-hidden />
            </span>
          )}
          {t.phase === "sent" ? `Enviado a ${t.to}` : "Enviando por WhatsApp…"}
        </div>
      ))}
    </div>
  );
}
