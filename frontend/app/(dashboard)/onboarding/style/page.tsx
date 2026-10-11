"use client";

import { CheckCircle2, FileUp, Sparkles } from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";
import useSWR, { type KeyedMutator } from "swr";
import { SkeletonCard } from "@/components/skeleton";
import { StyleMarkdown } from "@/components/style-markdown";
import { Button, Card, Pill, SectionTitle, Spinner, type Tone } from "@/components/ui";
import { ApiError, apiFetch, fetcher } from "@/lib/api";
import { formatDay, formatDayTime } from "@/lib/format";
import type { StyleState, StyleSupplierStatus, SupplierListItem } from "@/lib/types";

const SUPPLIER_STATUS: Record<StyleSupplierStatus, { label: string; tone: Tone }> = {
  pending: { label: "En cola", tone: "neutral" },
  reading: { label: "Leyendo el chat", tone: "info" },
  analyzing: { label: "Analizando", tone: "info" },
  done: { label: "Listo", tone: "success" },
  no_phone: { label: "Sin celular", tone: "warning" },
  no_chat: { label: "Sin mensajes desde la fecha", tone: "warning" },
  not_allowed: { label: "WhatsApp inactivo", tone: "warning" },
  error: { label: "Error", tone: "danger" },
};

const FINISHED: StyleSupplierStatus[] = ["done", "no_phone", "no_chat", "not_allowed", "error"];

// WhatsApp exports name the author after the date: Android "dd/mm/yy, hh:mm - Autor:",
// iOS "[dd/mm/yy, hh:mm:ss] Autor:" (personalidad's parser uses the same patterns).
const ANDROID = /^\d{1,2}\/\d{1,2}\/\d{2,4},? \d{1,2}:\d{2}.*? - ([^:]+):/;
const IOS = /^\[\d{1,2}\/\d{1,2}\/\d{2,4},? \d{1,2}:\d{2}(?::\d{2})?\] ([^:]+):/;

function exportAuthors(text: string): string[] {
  const authors = new Map<string, number>();
  for (const line of text.split(/\r?\n/)) {
    const name = (line.match(ANDROID)?.[1] ?? line.match(IOS)?.[2])?.trim();
    if (name) authors.set(name, (authors.get(name) ?? 0) + 1);
  }
  return [...authors.entries()].sort((a, b) => b[1] - a[1]).map(([name]) => name);
}

function daysAgo(days: number): string {
  // Real date, not the simulated clock: it filters real WhatsApp messages.
  return new Date(Date.now() - days * 86_400_000).toISOString().slice(0, 10);
}

function errorText(err: unknown): string {
  if (err instanceof ApiError) {
    if (err.status === 409) return "Hay una sincronización en curso. Espera a que termine.";
    const body = err.body as { detail?: string; errors?: string[] } | null;
    if (body?.errors?.length) return `${body.detail ?? "El estilo no pasa la validación."} ${body.errors.join(" ")}`;
    if (body?.detail) return body.detail;
  }
  return "No se pudo guardar. Inténtalo de nuevo.";
}

function progress(state: StyleState): { finished: number; total: number; pct: number } {
  const total = state.suppliers.length;
  const finished = state.suppliers.filter((s) => FINISHED.includes(s.status)).length;
  return { finished, total, pct: total ? Math.round((finished / total) * 100) : 0 };
}

// The Gerente sees one status line and one button. The full controls (date,
// .txt import, base profile, progress per supplier, editor) open with a triple
// click on the title and close with another: a hidden zone, no visual hint.
export default function OnboardingStyle() {
  const { data: state, mutate } = useSWR<StyleState>("/api/onboarding/style/", fetcher, { refreshInterval: 3000 });
  const [advanced, setAdvanced] = useState(false);
  const [busy, setBusy] = useState<"sync" | "approve" | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function post(path: string, body: Record<string, unknown> | undefined, kind: "sync" | "approve") {
    setBusy(kind);
    setError(null);
    try {
      mutate(await apiFetch<StyleState>(path, { method: "POST", json: body }), { revalidate: true });
    } catch (err) {
      setError(errorText(err));
    } finally {
      setBusy(null);
    }
  }

  if (!state) return <SkeletonCard lines={3} />;

  const extracting = state.status === "extracting";
  const hasDraft = !!state.style_md && state.status !== "approved" && !extracting;
  // Sync reads from the last sync, or the last 30 days the first time.
  const since = state.since ?? daysAgo(30);

  return (
    <div className="space-y-4">
      <Card>
        <h2
          className="select-none text-base font-semibold"
          onClick={(e) => {
            if (e.detail === 3) setAdvanced((open) => !open);
          }}
        >
          Estilo del Gerente
        </h2>

        <div className="mt-3 flex flex-wrap items-center gap-3">
          <StatusLine state={state} hasDraft={hasDraft} />
          <div className="ml-auto flex flex-wrap gap-2">
            {hasDraft && (
              <Button kind="primary" busy={busy === "approve"} disabled={busy !== null} onClick={() => post("/api/onboarding/style/approve/", undefined, "approve")}>
                Aprobar
              </Button>
            )}
            <Button
              kind={hasDraft ? "ghost" : "dark"}
              busy={busy === "sync" || extracting}
              disabled={busy !== null}
              onClick={() => post("/api/onboarding/style/extract/", { since }, "sync")}
            >
              {extracting ? "Sincronizando…" : "Sincronizar estilo"}
            </Button>
          </div>
        </div>

        {extracting && <ExtractionBar state={state} />}

        {state.status === "error" && (
          <p className="mt-3 text-sm text-danger" role="alert">
            {state.error || "La sincronización falló. Inténtalo de nuevo."}
          </p>
        )}
        {error && (
          <p className="mt-3 text-sm text-danger" role="alert">
            {error}
          </p>
        )}
        <p className="mt-3 text-xs text-muted">
          Sincronizar lee los chats de WhatsApp con los proveedores que tienen celular activo desde {state.since ? `la última sincronización (${formatDay(state.since)})` : "los últimos 30 días"},
          anonimiza nombres y teléfonos de terceros y deja un estilo nuevo listo para aprobar.
        </p>
      </Card>

      {advanced && <Advanced state={state} mutate={mutate} onClose={() => setAdvanced(false)} />}
    </div>
  );
}

function StatusLine({ state, hasDraft }: { state: StyleState; hasDraft: boolean }) {
  if (state.status === "extracting") {
    return (
      <p className="flex items-center gap-2 text-sm font-medium">
        <Spinner className="text-accent" /> Leyendo tus chats…
      </p>
    );
  }
  if (hasDraft) {
    return (
      <p className="flex items-center gap-2 text-sm font-medium">
        <Sparkles size={18} className="text-brand" /> Nuevo estilo listo
      </p>
    );
  }
  if (state.status === "approved" && state.approved_at) {
    return (
      <p className="flex items-center gap-2 text-sm font-medium">
        <CheckCircle2 size={18} className="text-success" /> Estilo aprobado el {formatDayTime(state.approved_at)}
      </p>
    );
  }
  return <p className="text-sm font-medium text-muted">Sin estilo</p>;
}

function ExtractionBar({ state }: { state: StyleState }) {
  const { finished, total, pct } = progress(state);
  const merging = state.step === "merging";
  return (
    <div className="mt-3">
      <div className="flex items-center justify-between text-xs text-muted tabular-nums">
        <span>{merging ? "Armando el estilo con todos los chats…" : `${finished} de ${total} proveedores`}</span>
        {!merging && <span>{pct} %</span>}
      </div>
      <div className="mt-1.5 h-1.5 overflow-hidden rounded-full bg-canvas" role="progressbar" aria-valuenow={merging ? undefined : pct} aria-valuemin={0} aria-valuemax={100}>
        {merging ? (
          <div className="h-full w-1/3 animate-[indeterminate_1.4s_ease-in-out_infinite] rounded-full bg-accent" />
        ) : (
          <div className="h-full rounded-full bg-accent transition-[width] duration-500" style={{ width: `${Math.max(4, pct)}%` }} />
        )}
      </div>
    </div>
  );
}

// Everything the simple view hides: pick the date, extract with confirmation,
// import a .txt export, fall back to the base profile, follow each supplier,
// and edit the draft with a preview.
function Advanced({ state, mutate, onClose }: { state: StyleState; mutate: KeyedMutator<StyleState>; onClose: () => void }) {
  const [since, setSince] = useState(state.since ?? daysAgo(90));
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [confirm, setConfirm] = useState<"extract" | "template" | null>(null);
  const extracting = state.status === "extracting";

  useEffect(() => {
    if (state.since) setSince(state.since);
  }, [state.since]);

  async function run(path: string, init: Parameters<typeof apiFetch>[1]) {
    setBusy(true);
    setError(null);
    try {
      mutate(await apiFetch<StyleState>(path, init), { revalidate: true });
      setConfirm(null);
    } catch (err) {
      setError(errorText(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <Card>
        <div className="flex flex-wrap items-center gap-2">
          <SectionTitle>Controles</SectionTitle>
          <Pill tone={state.status === "approved" ? "success" : state.status === "error" ? "danger" : state.status === "extracting" ? "info" : "neutral"}>
            {state.status_display}
          </Pill>
          <button type="button" onClick={onClose} className="ml-auto text-xs text-muted hover:underline">
            Ocultar
          </button>
        </div>
        <p className="text-sm text-muted">
          Se lee solo el chat de cada proveedor con celular activo, desde la fecha que elijas. Los nombres y teléfonos de terceros salen anonimizados.
        </p>

        <div className="mt-4 flex flex-wrap items-end gap-3">
          <label className="text-sm">
            <span className="block text-xs text-muted">Leer desde</span>
            <input type="date" value={since} max={daysAgo(0)} onChange={(e) => setSince(e.target.value)} className="mt-1 rounded-md px-2 py-1.5 ring-1 ring-line" />
          </label>
          <Button kind="primary" disabled={busy || !since} busy={extracting} onClick={() => setConfirm("extract")}>
            {extracting ? "Extrayendo…" : "Extraer estilo"}
          </Button>
          <ImportTxt since={since} disabled={busy || extracting} onDone={() => mutate()} onError={setError} />
          <Button disabled={busy || extracting} onClick={() => setConfirm("template")}>
            Usar perfil base
          </Button>
        </div>

        {confirm && (
          <div className="mt-3 flex flex-wrap items-center gap-2 rounded-lg bg-warning-soft px-3 py-2 text-sm text-warning">
            Esto reemplaza el borrador actual.
            <Button
              kind="dark"
              className="py-1"
              busy={busy}
              onClick={() =>
                confirm === "extract"
                  ? run("/api/onboarding/style/extract/", { method: "POST", json: { since } })
                  : run("/api/onboarding/style/template/", { method: "POST" })
              }
            >
              {confirm === "extract" ? "Extraer" : "Usar perfil base"}
            </Button>
            <Button className="py-1" onClick={() => setConfirm(null)}>
              Cancelar
            </Button>
          </div>
        )}

        {state.status === "error" && (
          <div className="mt-3 flex flex-wrap items-center gap-2 rounded-lg bg-danger-soft px-3 py-2 text-sm text-danger" role="alert">
            {state.error || "La extracción falló."}
            <Button className="py-1" busy={busy} onClick={() => run("/api/onboarding/style/extract/", { method: "POST", json: { since } })}>
              Reintentar
            </Button>
          </div>
        )}
        {error && (
          <p className="mt-3 text-sm text-danger" role="alert">
            {error}
          </p>
        )}
      </Card>

      {(extracting || state.suppliers.some((s) => s.status !== "pending")) && <Progress state={state} />}

      {!extracting && state.style_md && <Editor state={state} onSaved={() => mutate()} />}
    </>
  );
}

function Progress({ state }: { state: StyleState }) {
  const { finished, total, pct } = progress(state);
  return (
    <Card>
      <SectionTitle>Progreso por proveedor</SectionTitle>
      {state.status === "extracting" && state.step !== "merging" && (
        <div className="mb-3">
          <div className="flex items-center justify-between text-sm">
            <span className="flex items-center gap-2 font-medium">
              <Spinner /> Leyendo los chats…
            </span>
            <span className="text-muted tabular-nums">
              {finished} de {total} · {pct} %
            </span>
          </div>
          <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-canvas" role="progressbar" aria-valuenow={pct} aria-valuemin={0} aria-valuemax={100}>
            <div className="h-full rounded-full bg-accent transition-[width] duration-500" style={{ width: `${Math.max(4, pct)}%` }} />
          </div>
        </div>
      )}
      {state.step === "merging" && (
        <div className="mb-3">
          <p className="text-sm font-medium">Armando el estilo con todos los chats…</p>
          <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-canvas">
            <div className="h-full w-1/3 animate-[indeterminate_1.4s_ease-in-out_infinite] rounded-full bg-accent" />
          </div>
        </div>
      )}
      <ul className="divide-y divide-line text-sm">
        {state.suppliers.map((supplier) => {
          const s = SUPPLIER_STATUS[supplier.status];
          return (
            <li key={supplier.id} className="flex flex-wrap items-center justify-between gap-2 py-2 first:pt-0">
              <span className="font-medium">{supplier.name}</span>
              <span className="flex items-center gap-2">
                {supplier.messages_read !== null && supplier.status !== "pending" && (
                  <span className="text-xs text-muted tabular-nums">{supplier.messages_read} mensajes</span>
                )}
                <Pill tone={s.tone}>{s.label}</Pill>
                {supplier.status === "not_allowed" && (
                  <Link href={`/suppliers/${supplier.id}`} className="text-xs font-medium text-accent hover:underline">
                    Activar
                  </Link>
                )}
                {supplier.status === "no_phone" && (
                  <Link href={`/suppliers/${supplier.id}`} className="text-xs font-medium text-accent hover:underline">
                    Agregar celular
                  </Link>
                )}
              </span>
              {supplier.error && <span className="w-full text-xs text-danger">{supplier.error}</span>}
            </li>
          );
        })}
      </ul>
    </Card>
  );
}

function ImportTxt({
  since,
  disabled,
  onDone,
  onError,
}: {
  since: string;
  disabled: boolean;
  onDone: () => void;
  onError: (message: string | null) => void;
}) {
  const { data: suppliers } = useSWR<SupplierListItem[]>("/api/suppliers/", fetcher);
  const [file, setFile] = useState<File | null>(null);
  const [authors, setAuthors] = useState<string[]>([]);
  const [author, setAuthor] = useState("");
  const [supplierId, setSupplierId] = useState("");
  const [busy, setBusy] = useState(false);

  async function pick(selected: File | null) {
    onError(null);
    if (!selected) return;
    const found = exportAuthors(await selected.text());
    if (!found.length) {
      onError("No reconozco el formato. Exporta el chat desde WhatsApp sin archivos multimedia (.txt).");
      return;
    }
    setFile(selected);
    setAuthors(found);
    setAuthor(found[0]);
  }

  async function upload() {
    if (!file) return;
    setBusy(true);
    const form = new FormData();
    form.set("file", file);
    form.set("manager_author", author);
    form.set("since", since);
    if (supplierId) form.set("supplier_id", supplierId);
    try {
      await apiFetch("/api/onboarding/style/import-txt/", { method: "POST", body: form });
      setFile(null);
      setAuthors([]);
      onDone();
    } catch (err) {
      onError(errorText(err));
    } finally {
      setBusy(false);
    }
  }

  if (!file) {
    return (
      <label className={`inline-flex cursor-pointer items-center gap-1.5 rounded-md px-3 py-2 text-sm font-semibold ring-1 ring-line hover:bg-canvas ${disabled ? "pointer-events-none opacity-50" : ""}`}>
        <FileUp size={16} /> Agregar chat (.txt)
        <input type="file" accept=".txt,text/plain" className="sr-only" disabled={disabled} onChange={(e) => pick(e.target.files?.[0] ?? null)} />
      </label>
    );
  }

  // Adds the chat to the current draft (no confirmation: it does not replace it).
  return (
    <div className="flex w-full flex-wrap items-end gap-2 rounded-lg bg-canvas p-3 text-sm">
      <span className="w-full text-xs text-muted">{file.name}</span>
      <label>
        <span className="block text-xs text-muted">¿Quién es el Gerente en el chat?</span>
        <select value={author} onChange={(e) => setAuthor(e.target.value)} className="mt-1 rounded-md bg-surface px-2 py-1.5 ring-1 ring-line">
          {authors.map((a) => (
            <option key={a}>{a}</option>
          ))}
        </select>
      </label>
      <label>
        <span className="block text-xs text-muted">Proveedor (opcional, para sus notas)</span>
        <select value={supplierId} onChange={(e) => setSupplierId(e.target.value)} className="mt-1 rounded-md bg-surface px-2 py-1.5 ring-1 ring-line">
          <option value="">Ninguno</option>
          {(suppliers ?? []).filter((s) => !s.is_in_house).map((s) => (
            <option key={s.id} value={s.id}>
              {s.name}
            </option>
          ))}
        </select>
      </label>
      <Button kind="dark" busy={busy} disabled={disabled} onClick={upload}>
        Agregar al borrador
      </Button>
      <Button onClick={() => setFile(null)}>Cancelar</Button>
    </div>
  );
}

function Editor({ state, onSaved }: { state: StyleState; onSaved: () => void }) {
  const [text, setText] = useState(state.style_md);
  const [notes, setNotes] = useState(state.notes);
  const [tab, setTab] = useState<"edit" | "preview">("preview");
  const [busy, setBusy] = useState(false);
  const [approving, setApproving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const dirty = text !== state.style_md || notes.some((n, i) => n.notes !== state.notes[i]?.notes);

  // Follow the server while nothing was edited here (a new extraction, an import).
  useEffect(() => {
    if (!dirty) {
      setText(state.style_md);
      setNotes(state.notes);
    }
  }, [state.style_md, state.notes]);

  async function save(approve: boolean) {
    setBusy(true);
    setApproving(approve);
    setError(null);
    try {
      if (dirty) await apiFetch("/api/onboarding/style/", { method: "PUT", json: { style_md: text, notes } });
      if (approve) await apiFetch("/api/onboarding/style/approve/", { method: "POST" });
      onSaved();
    } catch (err) {
      setError(errorText(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <Card>
        <div className="mb-3 flex flex-wrap items-center gap-2">
          <SectionTitle>Borrador</SectionTitle>
          <div className="flex rounded-md bg-canvas p-0.5 text-sm lg:hidden" role="tablist">
            {(["preview", "edit"] as const).map((t) => (
              <button key={t} type="button" role="tab" aria-selected={tab === t} onClick={() => setTab(t)} className={`rounded px-2.5 py-1 ${tab === t ? "bg-surface shadow-sm" : ""}`}>
                {t === "preview" ? "Vista previa" : "Editar"}
              </button>
            ))}
          </div>
          <div className="ml-auto flex gap-2">
            {dirty && (
              <Button busy={busy && !approving} onClick={() => save(false)}>
                Guardar borrador
              </Button>
            )}
            {(dirty || state.status !== "approved") && (
              <Button kind="primary" disabled={busy} busy={busy && approving} onClick={() => save(true)}>
                Aprobar
              </Button>
            )}
          </div>
        </div>
        {error && (
          <p className="mb-3 text-sm text-danger" role="alert">
            {error}
          </p>
        )}
        <div className="grid gap-4 lg:grid-cols-2">
          <textarea
            value={text}
            onChange={(e) => setText(e.target.value)}
            aria-label="Estilo en markdown"
            className={`min-h-[28rem] w-full rounded-lg p-3 font-mono text-sm ring-1 ring-line ${tab === "edit" ? "" : "hidden lg:block"}`}
          />
          <div className={`max-h-[36rem] overflow-y-auto rounded-lg p-3 ring-1 ring-line ${tab === "preview" ? "" : "hidden lg:block"}`}>
            <StyleMarkdown source={text} />
          </div>
        </div>
      </Card>

      {notes.length > 0 && (
        <Card>
          <SectionTitle count={notes.length}>Notas por proveedor</SectionTitle>
          <div className="grid gap-3 md:grid-cols-2">
            {notes.map((note, i) => (
              <label key={note.supplier_id} className="text-sm">
                <span className="font-medium">{note.supplier_name}</span>
                <textarea
                  value={note.notes}
                  onChange={(e) => setNotes((all) => all.map((n, j) => (j === i ? { ...n, notes: e.target.value } : n)))}
                  rows={5}
                  placeholder={"Trato:\nTono:\nInsistencia:\nHorario:\nOjo:"}
                  className="mt-1 w-full rounded-md p-2 font-mono text-xs ring-1 ring-line"
                />
              </label>
            ))}
          </div>
        </Card>
      )}
    </>
  );
}
