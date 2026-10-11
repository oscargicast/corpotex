"use client";

import { Send } from "lucide-react";
import { usePathname } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";
import { apiFetch } from "@/lib/api";
import { contextFor } from "@/lib/assistant-context";
import { useBadges } from "@/lib/badges";
import type { AssistantMessage, Role } from "@/lib/types";
import { useUser } from "../require-auth";
import { Skeleton } from "../skeleton";
import { TypingDots } from "../typing-dots";
import { Spinner } from "../ui";
import { MessageBubble } from "./message";
import { playChime, readHidden, writeHidden } from "./notice-prefs";

const SUGGESTIONS: Record<Role, string[]> = {
  manager: ["¿Qué tengo pendiente?", "¿Qué órdenes están en peligro?", "¿Cuánto debo a los talleres?"],
  sales: ["¿Cuándo llega la orden de Caja Piura?", "Registrar una orden", "¿Qué órdenes están en riesgo?"],
  production: ["Fichas técnicas por aprobar", "¿Qué pedidos no avanzan?", "Registrar un avance"],
};

// Confirmation questions end in "(sí/no)" (personalidad's prompt rule).
const CONFIRM = /\(s[ií]\/no\)\s*$/i;

interface Thread {
  typing: boolean;
  messages: AssistantMessage[];
}

export function AssistantChat({ visible = true }: { visible?: boolean }) {
  const user = useUser();
  const pathname = usePathname();
  const badges = useBadges();
  const [messages, setMessages] = useState<AssistantMessage[]>([]);
  const [typing, setTyping] = useState(false);
  const [text, setText] = useState("");
  const [sending, setSending] = useState(false);
  const [loaded, setLoaded] = useState(false);
  const [hidden, setHidden] = useState<Set<number>>(() => new Set());
  const lastId = useRef(0);
  const readUpTo = useRef(0);
  const firstPollDone = useRef(false);
  const visibleRef = useRef(visible);
  const box = useRef<HTMLDivElement>(null);
  const available = badges?.claude_ok ?? true;
  visibleRef.current = visible;

  // Notices hidden in this browser, read after mount (storage does not exist on the server).
  useEffect(() => {
    setHidden(readHidden());
  }, []);

  const poll = useCallback(async () => {
    const thread = await apiFetch<Thread>(`/api/assistant/messages/?after=${lastId.current}`);
    if (thread.messages.length) {
      lastId.current = thread.messages[thread.messages.length - 1].id;
      setMessages((current) => [...current, ...thread.messages.filter((m) => !current.some((c) => c.id === m.id))]);
      // A chime for a notice that arrives while the chat is open; the first poll
      // brings the history (already seen), never a sound.
      const notice = thread.messages.some((m) => m.action?.kind === "alert");
      if (firstPollDone.current && notice && visibleRef.current) playChime();
    }
    firstPollDone.current = true;
    setTyping(thread.typing);
    setLoaded(true);
  }, []);

  // The "x" of a notice only hides it here; the alert stays open in the Monitor.
  function hideNotice(id: number) {
    setHidden((current) => {
      const next = new Set(current).add(id);
      writeHidden(next);
      return next;
    });
  }

  // Poll every 3 s while the chat is on screen (no websockets, ADR 0009).
  useEffect(() => {
    if (!visible) return;
    poll().catch(() => undefined);
    const id = setInterval(() => poll().catch(() => undefined), 3000);
    return () => clearInterval(id);
  }, [visible, poll]);

  // Mark as read what the user can see.
  useEffect(() => {
    const last = messages.at(-1);
    if (!visible || !last || last.id <= readUpTo.current) return;
    readUpTo.current = last.id;
    apiFetch("/api/assistant/messages/read/", { method: "POST", json: { up_to_id: last.id } }).catch(() => undefined);
  }, [visible, messages]);

  useEffect(() => {
    if (box.current) box.current.scrollTop = box.current.scrollHeight;
  }, [messages.length, typing]);

  async function send(value: string) {
    const body = value.trim();
    if (!body || sending) return;
    setSending(true);
    setText("");
    try {
      const created = await apiFetch<AssistantMessage>("/api/assistant/messages/", {
        method: "POST",
        json: { text: body, context: contextFor(pathname) },
      });
      lastId.current = Math.max(lastId.current, created.id);
      setMessages((current) => [...current, created]);
      setTyping(true);
    } catch {
      setText(body);
    } finally {
      setSending(false);
    }
  }

  const last = messages.at(-1);
  const awaitingConfirm = !typing && last?.role === "assistant" && !last.action && CONFIRM.test(last.text);

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div ref={box} className="min-h-0 flex-1 space-y-3 overflow-y-auto p-4" aria-live="polite">
        {!loaded && (
          <div role="status" aria-label="Cargando" className="space-y-3">
            <Skeleton className="h-10 w-3/4 rounded-2xl" />
            <Skeleton className="ml-auto h-10 w-1/2 rounded-2xl" />
            <Skeleton className="h-16 w-4/5 rounded-2xl" />
          </div>
        )}
        {loaded && !messages.length && (
          <div className="pt-6 text-center text-sm text-muted">
            <p>Pregúntame por órdenes, pedidos o alertas.</p>
            <div className="mt-4 flex flex-col items-center gap-2">
              {SUGGESTIONS[user.role].map((s) => (
                <button
                  key={s}
                  type="button"
                  disabled={!available}
                  onClick={() => send(s)}
                  className="rounded-full bg-surface px-3 py-1.5 text-ink ring-1 ring-line hover:bg-canvas disabled:opacity-50"
                >
                  {s}
                </button>
              ))}
            </div>
          </div>
        )}
        {messages
          .filter((message) => !hidden.has(message.id))
          .map((message) => (
            <MessageBubble key={message.id} message={message} onHide={message.action?.kind === "alert" ? () => hideNotice(message.id) : undefined} />
          ))}
        {typing && (
          <div className="flex w-fit items-center gap-2 rounded-2xl rounded-bl-sm bg-surface px-3 py-2 text-sm text-muted ring-1 ring-line">
            <TypingDots label="Pensando" />
            <span>Pensando…</span>
          </div>
        )}
      </div>

      {awaitingConfirm && (
        <div className="flex gap-2 px-4 pb-2">
          <button type="button" onClick={() => send("Sí")} className="flex-1 rounded-md bg-brand py-2 font-semibold text-ink hover:bg-brand-hover">
            Sí
          </button>
          <button type="button" onClick={() => send("No")} className="flex-1 rounded-md py-2 font-semibold ring-1 ring-line hover:bg-canvas">
            No
          </button>
        </div>
      )}

      {available ? (
        <form
          onSubmit={(e) => {
            e.preventDefault();
            send(text);
          }}
          className="flex items-end gap-2 border-t border-line bg-surface p-3"
        >
          <textarea
            value={text}
            onChange={(e) => setText(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
                e.preventDefault();
                send(text);
              }
            }}
            rows={1}
            placeholder="Escribe un mensaje"
            aria-label="Mensaje para el asistente"
            className="max-h-32 min-h-10 flex-1 resize-none rounded-md px-3 py-2 text-sm ring-1 ring-line"
          />
          <button
            type="submit"
            disabled={sending || !text.trim()}
            aria-label={sending ? "Enviando" : "Enviar"}
            aria-busy={sending || undefined}
            className="rounded-md bg-ink p-2.5 text-white disabled:opacity-40"
          >
            {sending ? <Spinner /> : <Send size={16} />}
          </button>
        </form>
      ) : (
        <p className="border-t border-line bg-surface p-3 text-sm text-muted">
          {user.role === "manager" ? "Reconecta Claude en Configuración para usar el asistente." : "El asistente no está disponible; avisa al Gerente."}
        </p>
      )}
    </div>
  );
}
