"use client";

import { ImagePlus, Maximize2, Minimize2, Paperclip, Send, X } from "lucide-react";
import { useRouter, useSearchParams } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";
import useSWR from "swr";
import { apiFetch, fetcher } from "@/lib/api";
import type { ChatMessage, SimulatorContact } from "@/lib/types";
import { ChatThread } from "../chat-thread";
import { Clock } from "../clock";
import { SimulateOrder } from "../simulate-order";
import { Pill } from "../ui";

const SEEN_KEY = "corpotex.simulator.seen";
const PHRASES_KEY = "corpotex.simulator.phrases";

// Per-viewer conveniences only; the page works without storage.
function load<T>(key: string, fallback: T): T {
  try {
    return JSON.parse(localStorage.getItem(key) ?? "") as T;
  } catch {
    return fallback;
  }
}
function save(key: string, value: unknown) {
  try {
    localStorage.setItem(key, JSON.stringify(value));
  } catch {
    // Storage blocked: nothing to keep.
  }
}

const COLORS = ["bg-accent", "bg-success", "bg-warning", "bg-ink", "bg-danger", "bg-muted"];

// The contact's name is the number's label; the supplier is what the operator looks for.
function displayName(contact: SimulatorContact) {
  return contact.supplier?.name ?? contact.name;
}

function initials(name: string) {
  return name
    .split(/\s+/)
    .filter((w) => w.length > 2)
    .slice(0, 2)
    .map((w) => w[0]?.toUpperCase())
    .join("");
}

export function Simulator() {
  const router = useRouter();
  const params = useSearchParams();
  const present = params.get("present") === "1";
  const { data: contacts } = useSWR<SimulatorContact[]>("/api/simulator/contacts/", fetcher, { refreshInterval: 3000 });
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [seen, setSeen] = useState<Record<number, number>>({});
  const [toast, setToast] = useState<string | null>(null);
  const initialized = useRef(false);
  const toasted = useRef(new Set<number>());

  const selected = contacts?.find((c) => c.allowed_number_id === selectedId) ?? contacts?.[0] ?? null;

  const togglePresent = useCallback(() => {
    router.replace(present ? "/simulator" : "/simulator?present=1");
  }, [present, router]);

  // First load: what is already there counts as seen, so only new messages highlight.
  useEffect(() => {
    if (!contacts || initialized.current) return;
    initialized.current = true;
    const stored = load<Record<number, number>>(SEEN_KEY, {});
    const base = Object.fromEntries(contacts.map((c) => [c.allowed_number_id, stored[c.allowed_number_id] ?? c.last_message?.id ?? 0]));
    setSeen(base);
  }, [contacts]);

  // The agent wrote to a contact that is not open: highlight it and say so.
  useEffect(() => {
    if (!contacts || !initialized.current) return;
    for (const contact of contacts) {
      const last = contact.last_message;
      if (!last || contact.allowed_number_id === selected?.allowed_number_id || last.direction !== "outbound") continue;
      // One toast per message; the highlight stays until the contact is opened.
      if (last.id > (seen[contact.allowed_number_id] ?? 0) && !toasted.current.has(last.id)) {
        toasted.current.add(last.id);
        setToast(displayName(contact));
      }
    }
  }, [contacts, seen, selected?.allowed_number_id]);

  // The open chat is always seen.
  useEffect(() => {
    const lastId = selected?.last_message?.id;
    if (!selected || !lastId || seen[selected.allowed_number_id] === lastId) return;
    setSeen((current) => {
      const next = { ...current, [selected.allowed_number_id]: lastId };
      save(SEEN_KEY, next);
      return next;
    });
  }, [selected, seen]);

  useEffect(() => {
    if (!toast) return;
    const id = setTimeout(() => setToast(null), 5000);
    return () => clearTimeout(id);
  }, [toast]);

  // Shortcuts: 1 to 9 switch contact, P toggles presentation. Not while typing.
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      const target = e.target as HTMLElement;
      if (target.closest("input, textarea, select, [contenteditable]") || e.metaKey || e.ctrlKey || e.altKey) return;
      if (/^[1-9]$/.test(e.key) && contacts?.[Number(e.key) - 1]) setSelectedId(contacts[Number(e.key) - 1].allowed_number_id);
      if (e.key.toLowerCase() === "p") togglePresent();
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [contacts, togglePresent]);

  const unread = (c: SimulatorContact) => !!c.last_message && c.last_message.direction === "outbound" && c.last_message.id > (seen[c.allowed_number_id] ?? 0);

  const body = (
    <div className={`flex min-h-0 flex-1 overflow-hidden rounded-xl bg-surface ring-1 ring-line ${present ? "text-lg" : ""}`}>
      <nav aria-label="Contactos" className={`flex shrink-0 flex-col overflow-y-auto border-r border-line ${present ? "w-80" : "w-24 sm:w-64"}`}>
        {!contacts && <p className="p-4 text-sm text-muted">Cargando…</p>}
        {contacts?.map((contact, i) => {
          const active = contact.allowed_number_id === selected?.allowed_number_id;
          const isNew = unread(contact);
          const name = displayName(contact);
          return (
            <button
              key={contact.allowed_number_id}
              type="button"
              onClick={() => setSelectedId(contact.allowed_number_id)}
              aria-current={active ? "true" : undefined}
              className={`flex items-center gap-3 border-b border-line px-3 py-3 text-left ${active ? "bg-canvas" : isNew ? "bg-warning-soft" : "hover:bg-canvas"}`}
            >
              <span className={`relative flex size-10 shrink-0 items-center justify-center rounded-full text-sm font-bold text-white ${COLORS[i % COLORS.length]}`}>
                {initials(name)}
                {isNew && <span className="absolute -right-0.5 -top-0.5 size-3 rounded-full bg-danger ring-2 ring-surface" />}
              </span>
              <span className="hidden min-w-0 flex-1 sm:block">
                <span className="flex items-center gap-2">
                  <span className="truncate font-semibold">{name}</span>
                  {i < 9 && <kbd className="ml-auto rounded bg-canvas px-1 text-[11px] text-muted">{i + 1}</kbd>}
                </span>
                <span className="mt-0.5 flex items-center gap-1.5 text-xs text-muted">
                  {contact.channel === "whatsapp" && <Pill tone="success">WhatsApp real</Pill>}
                  <span className="truncate">{contact.last_message?.text ?? "Sin mensajes"}</span>
                </span>
              </span>
            </button>
          );
        })}
      </nav>
      {selected ? <Conversation key={selected.allowed_number_id} contact={selected} large={present} /> : <div className="flex-1" />}
    </div>
  );

  const toastNode = toast && (
    <div role="status" className="fixed left-1/2 top-20 z-[60] -translate-x-1/2 rounded-xl bg-ink px-4 py-3 text-white shadow-xl">
      Nuevo mensaje para <strong>{toast}</strong>
    </div>
  );

  if (present) {
    return (
      <div className="fixed inset-0 z-50 flex flex-col gap-3 bg-canvas p-4">
        <div className="flex flex-wrap items-center gap-3 rounded-xl bg-surface px-4 py-2 ring-1 ring-line">
          <span className="text-xl font-black tracking-tight">CORPOTEX · Simulador</span>
          <div className="ml-auto flex flex-wrap items-center gap-3">
            <Clock />
            <SimulateOrder />
            <button type="button" onClick={togglePresent} className="rounded-md p-2 hover:bg-canvas" title="Salir del modo presentación (P)">
              <Minimize2 size={20} />
            </button>
          </div>
        </div>
        {body}
        {toastNode}
      </div>
    );
  }

  return (
    <div className="flex h-[calc(100dvh-3.5rem-6rem)] flex-col gap-3 md:h-[calc(100dvh-3.5rem-3rem)]">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h1 className="text-2xl font-bold tracking-tight">Simulador</h1>
        <button type="button" onClick={togglePresent} className="flex items-center gap-1.5 rounded-md px-3 py-2 text-sm font-medium ring-1 ring-line hover:bg-surface">
          <Maximize2 size={16} /> Modo presentación <kbd className="rounded bg-canvas px-1 text-xs text-muted">P</kbd>
        </button>
      </div>
      {body}
      {toastNode}
    </div>
  );
}

interface DemoPhoto {
  file: string;
  label: string;
}

function Conversation({ contact, large }: { contact: SimulatorContact; large: boolean }) {
  const { data, mutate } = useSWR<{ typing: boolean; messages: ChatMessage[] }>(
    contact.conversation_id ? `/api/conversations/${contact.conversation_id}/messages/` : null,
    fetcher,
    { refreshInterval: 3000 },
  );
  const { data: photos } = useSWR<DemoPhoto[]>("/demo-photos/manifest.json", (url: string) =>
    fetch(url).then((r) => (r.ok ? r.json() : [])),
  );
  const [text, setText] = useState("");
  const [photo, setPhoto] = useState<File | null>(null);
  const [preview, setPreview] = useState<string | null>(null);
  const [picker, setPicker] = useState(false);
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const name = displayName(contact);
  const [phrases, setPhrases] = useState<string[]>(() => load<Record<number, string[]>>(PHRASES_KEY, {})[contact.allowed_number_id] ?? []);
  const readOnly = contact.channel === "whatsapp";

  function attach(file: File | null) {
    setPhoto(file);
    setPreview(file ? URL.createObjectURL(file) : null);
    setPicker(false);
  }

  async function pickDemo(item: DemoPhoto) {
    const blob = await fetch(`/demo-photos/${item.file}`).then((r) => r.blob());
    attach(new File([blob], item.file, { type: blob.type || "image/jpeg" }));
  }

  function storePhrases(next: string[]) {
    setPhrases(next);
    save(PHRASES_KEY, { ...load<Record<number, string[]>>(PHRASES_KEY, {}), [contact.allowed_number_id]: next });
  }

  async function send(e: React.FormEvent) {
    e.preventDefault();
    if (!text.trim() && !photo) return;
    setSending(true);
    setError(null);
    const form = new FormData();
    form.set("allowed_number_id", String(contact.allowed_number_id));
    form.set("text", text.trim());
    if (photo) form.set("photo", photo);
    try {
      await apiFetch("/api/simulator/messages/", { method: "POST", body: form });
      setText("");
      attach(null);
      mutate();
    } catch {
      setError("No se pudo enviar.");
    } finally {
      setSending(false);
    }
  }

  return (
    <section className="flex min-w-0 flex-1 flex-col">
      <header className="flex items-center gap-2 border-b border-line px-4 py-3">
        <p className="font-semibold">{name}</p>
        {readOnly ? <Pill tone="success">WhatsApp real · solo lectura</Pill> : <Pill tone="info">Simulado</Pill>}
      </header>

      <ChatThread
        messages={data?.messages ?? []}
        typing={data?.typing}
        large={large}
        perspective="supplier"
        className="min-h-0 flex-1 rounded-none"
      />

      {readOnly ? (
        <p className="border-t border-line p-3 text-sm text-muted">Este proveedor escribe desde su celular; aquí se ve su chat real.</p>
      ) : (
        <form onSubmit={send} className="border-t border-line p-3">
          {phrases.length > 0 && (
            <div className="mb-2 flex flex-wrap gap-1.5">
              {phrases.map((phrase, i) => (
                <span key={i} className="flex max-w-full items-center rounded-full bg-canvas text-sm ring-1 ring-line">
                  <button type="button" onClick={() => setText(phrase)} className="truncate px-3 py-1" title={phrase}>
                    {phrase}
                  </button>
                  <button type="button" onClick={() => storePhrases(phrases.filter((_, j) => j !== i))} className="pr-2 text-muted" aria-label="Quitar frase">
                    <X size={12} />
                  </button>
                </span>
              ))}
            </div>
          )}
          {preview && (
            <div className="mb-2 flex items-center gap-2">
              <img src={preview} alt="Foto adjunta" className="size-16 rounded-lg object-cover" />
              <button type="button" onClick={() => attach(null)} className="text-sm text-muted underline">
                Quitar foto
              </button>
            </div>
          )}
          {picker && !!photos?.length && (
            <div className="mb-2 flex gap-2 overflow-x-auto">
              {photos.map((item) => (
                <button key={item.file} type="button" onClick={() => pickDemo(item)} className="shrink-0" title={item.label}>
                  <img src={`/demo-photos/${item.file}`} alt={item.label} className="size-20 rounded-lg object-cover ring-1 ring-line hover:ring-2 hover:ring-accent" />
                </button>
              ))}
            </div>
          )}
          <div className="flex items-end gap-2">
            {!!photos?.length && (
              <button type="button" onClick={() => setPicker((open) => !open)} className="rounded-md p-2.5 ring-1 ring-line hover:bg-canvas" title="Fotos de ejemplo">
                <ImagePlus size={18} />
              </button>
            )}
            <label className="cursor-pointer rounded-md p-2.5 ring-1 ring-line hover:bg-canvas" title="Adjuntar foto">
              <Paperclip size={18} />
              <input type="file" accept="image/*" className="sr-only" onChange={(e) => attach(e.target.files?.[0] ?? null)} />
            </label>
            <textarea
              value={text}
              onChange={(e) => setText(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
                  e.preventDefault();
                  e.currentTarget.form?.requestSubmit();
                }
              }}
              rows={1}
              placeholder={`Escribe como ${name}`}
              aria-label={`Mensaje de ${name}`}
              className="max-h-32 min-h-11 flex-1 resize-none rounded-md px-3 py-2.5 ring-1 ring-line"
            />
            <button type="submit" disabled={sending || (!text.trim() && !photo)} className="rounded-md bg-ink p-3 text-white disabled:opacity-40" aria-label="Enviar">
              <Send size={18} />
            </button>
          </div>
          <div className="mt-1.5 flex items-center justify-between text-xs text-muted">
            <span>{error ?? "Enter envía · Shift+Enter salto de línea"}</span>
            {text.trim() && !phrases.includes(text.trim()) && (
              <button type="button" onClick={() => storePhrases([...phrases, text.trim()])} className="underline">
                Guardar frase
              </button>
            )}
          </div>
        </form>
      )}
    </section>
  );
}
