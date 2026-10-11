"use client";

import { ClipboardPaste, ExternalLink } from "lucide-react";
import { useState } from "react";
import useSWR from "swr";
import { ApiError, apiFetch, fetcher } from "@/lib/api";
import type { ClaudeErrorCode, ClaudeStatus } from "@/lib/types";
import { SkeletonCard } from "./skeleton";
import { Spinner } from "./ui";

const STATUS_URL = "/api/settings/claude/status/";

const ERROR_TEXT: Record<ClaudeErrorCode, string> = {
  invalid_code: "Ese código no funcionó. Vencen rápido: empieza de nuevo y pega el nuevo.",
  missing_state: "Falta una parte del código. Cópialo completo, incluida la parte después del #.",
  unreachable: "No se pudo conectar con Claude. Revisa la conexión e inténtalo de nuevo.",
  key_rejected: "Anthropic rechazó esa key. Revisa que siga activa en tu consola.",
  key_unverifiable: "No se pudo verificar la key. Inténtalo en un momento.",
  key_format: "Las keys de Anthropic empiezan con sk-ant-.",
  not_connected: "Claude no está conectado.",
};

function errorText(err: unknown): string {
  if (err instanceof ApiError) {
    const body = err.body as { error_code?: ClaudeErrorCode; detail?: string } | null;
    if (body?.detail) console.warn("claude connect:", body.detail);
    if (body?.error_code && ERROR_TEXT[body.error_code]) return ERROR_TEXT[body.error_code];
  }
  return "Algo salió mal. Inténtalo de nuevo.";
}

const dateFormat = new Intl.DateTimeFormat("es-PE", { timeZone: "America/Lima", dateStyle: "medium" });

// The API sends these as epoch numbers (seconds or milliseconds).
function toDate(value: number | string): Date {
  if (typeof value === "string") return new Date(value);
  return new Date(value < 1e12 ? value * 1000 : value);
}

// Connect the single Claude account every agent uses (ADR 0022), copied from mano's flow.
export function ClaudeConnect({ reconnect = false }: { reconnect?: boolean }) {
  const { data: status, mutate } = useSWR<ClaudeStatus>(STATUS_URL, fetcher);
  const [flowOpen, setFlowOpen] = useState(reconnect);

  if (!status) return <SkeletonCard lines={2} />;

  const broken = status.expired || !!status.last_error;
  const showFlow = flowOpen || !status.connected || broken;

  return (
    <div className="space-y-4">
      <StatusCard status={status} />

      {status.connected && !showFlow && (
        <button type="button" onClick={() => setFlowOpen(true)} className="text-sm font-medium text-accent underline">
          Reconectar con otra cuenta
        </button>
      )}

      {showFlow && (
        <OAuthFlow
          isReconnect={status.connected || broken || reconnect}
          onConnected={(next) => {
            mutate(next, { revalidate: false });
            setFlowOpen(false);
          }}
        />
      )}

      <ApiKeyForm onConnected={(next) => mutate(next, { revalidate: false })} />

      {status.connected && <Disconnect onDone={(next) => mutate(next, { revalidate: false })} />}
    </div>
  );
}

function StatusCard({ status }: { status: ClaudeStatus }) {
  const broken = status.expired || !!status.last_error;
  let title = "Desconectado";
  let detail = "Los agentes y el asistente no funcionan hasta conectar una cuenta de Claude.";
  let tone = "bg-surface ring-line";

  if (status.connected && !broken) {
    tone = "bg-success-soft ring-success/30";
    if (status.method === "api_key") {
      title = "Conectado con una API key";
      detail = "Cada llamada se cobra en la consola de Anthropic.";
    } else {
      const plan = status.subscription_type ? ` · suscripción ${capitalize(status.subscription_type)}` : "";
      title = `Conectado${plan}`;
      detail = status.refresh_token_expires_at
        ? `La conexión vence el ${dateFormat.format(toDate(status.refresh_token_expires_at))}.`
        : "La conexión está activa.";
    }
  } else if (broken) {
    tone = "bg-danger-soft ring-danger/30";
    title = "La conexión con Claude venció";
    detail = "Reconecta la cuenta para que los agentes vuelvan a responder.";
  }

  return (
    <section className={`rounded-xl p-5 ring-1 ${tone}`}>
      <p className="text-lg font-semibold">{title}</p>
      <p className="mt-1 text-sm text-muted">{detail}</p>
    </section>
  );
}

function OAuthFlow({ isReconnect, onConnected }: { isReconnect: boolean; onConnected: (s: ClaudeStatus) => void }) {
  const [started, setStarted] = useState(false);
  const [authUrl, setAuthUrl] = useState<string | null>(null);
  const [code, setCode] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function start() {
    setError(null);
    // Open the window inside the click, before any await: opened later, mobile
    // browsers and Safari block it as a popup (same as mano).
    const popup = window.open("", "_blank", "popup,width=520,height=760");
    if (popup) popup.opener = null;
    setBusy(true);
    try {
      const { url } = await apiFetch<{ url: string }>("/api/settings/claude/start/", {
        method: "POST",
        json: { is_reconnect: isReconnect },
      });
      setAuthUrl(url);
      if (popup) popup.location.href = url;
      setStarted(true);
    } catch (err) {
      popup?.close();
      setError(errorText(err));
    } finally {
      setBusy(false);
    }
  }

  async function paste() {
    try {
      const text = await navigator.clipboard.readText();
      if (text) setCode(text.trim());
      setError(null);
    } catch {
      // Clipboard denied: the field still accepts a manual paste.
    }
  }

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    const value = code.trim();
    if (!value.includes("#") || value.endsWith("#")) {
      setError(ERROR_TEXT.missing_state);
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const next = await apiFetch<ClaudeStatus>("/api/settings/claude/exchange/", {
        method: "POST",
        json: { code: value, is_reconnect: isReconnect },
      });
      onConnected(next);
    } catch (err) {
      setError(errorText(err));
    } finally {
      setBusy(false);
    }
  }

  const canPaste = typeof navigator !== "undefined" && !!navigator.clipboard?.readText;

  return (
    <section className="rounded-xl bg-surface p-5 ring-1 ring-line">
      <h2 className="font-semibold">{isReconnect ? "Reconectar con Claude" : "Conectar con Claude"}</h2>
      <ol className="mt-3 list-decimal space-y-1 pl-5 text-sm">
        <li>Inicia sesión en Claude.</li>
        <li>Toca Autorizar.</li>
        <li>Copia el código y pégalo aquí.</li>
      </ol>

      <button
        type="button"
        onClick={start}
        disabled={busy}
        aria-busy={(busy && !started) || undefined}
        className="mt-4 inline-flex items-center gap-2 rounded-md bg-brand px-4 py-2.5 font-semibold text-ink hover:bg-brand-hover disabled:opacity-60"
      >
        {busy && !started && <Spinner />}
        {busy && !started ? "Abriendo Claude…" : isReconnect ? "Reconectar con Claude" : "Conectar con Claude"}
      </button>
      {authUrl && (
        <a href={authUrl} target="_blank" rel="noreferrer" className="ml-3 inline-flex items-center gap-1 text-sm text-accent underline">
          Abrir Claude otra vez <ExternalLink size={14} />
        </a>
      )}

      <form onSubmit={submit} className="mt-5">
        <label htmlFor="claude-code" className="block text-sm font-medium">
          Código de autorización
        </label>
        <div className="mt-1 flex gap-2">
          <input
            id="claude-code"
            value={code}
            onChange={(e) => {
              setCode(e.target.value);
              setError(null);
            }}
            disabled={!started}
            placeholder="Pega el código de Claude"
            autoComplete="one-time-code"
            spellCheck={false}
            className="min-w-0 flex-1 rounded-md border border-line px-3 py-2.5 font-mono text-sm disabled:bg-canvas"
          />
          {canPaste && (
            <button
              type="button"
              onClick={paste}
              disabled={!started}
              className="flex items-center gap-1 rounded-md border border-line px-3 text-sm hover:bg-canvas disabled:opacity-50"
            >
              <ClipboardPaste size={16} />
              Pegar
            </button>
          )}
        </div>
        {error && (
          <p className="mt-2 text-sm text-danger" role="alert">
            {error}
          </p>
        )}
        <button
          type="submit"
          disabled={!started || busy || !code.trim()}
          aria-busy={(busy && started) || undefined}
          className="mt-3 inline-flex items-center gap-2 rounded-md bg-ink px-4 py-2 text-sm font-semibold text-white disabled:opacity-40"
        >
          {busy && started && <Spinner />}
          {busy && started ? "Conectando…" : "Conectar"}
        </button>
      </form>
    </section>
  );
}

function ApiKeyForm({ onConnected }: { onConnected: (s: ClaudeStatus) => void }) {
  const [key, setKey] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!key.trim().startsWith("sk-ant-")) {
      setError(ERROR_TEXT.key_format);
      return;
    }
    setBusy(true);
    setError(null);
    try {
      onConnected(
        await apiFetch<ClaudeStatus>("/api/settings/claude/set-key/", { method: "POST", json: { api_key: key.trim() } }),
      );
      setKey("");
    } catch (err) {
      setError(errorText(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <details className="rounded-xl bg-surface p-5 ring-1 ring-line">
      <summary className="cursor-pointer text-sm font-medium">Usar una API key</summary>
      <p className="mt-2 text-sm text-muted">Reemplaza la conexión con la suscripción. Cada llamada se cobra en la consola de Anthropic.</p>
      <form onSubmit={submit} className="mt-3 flex flex-wrap gap-2">
        <input
          type="password"
          value={key}
          onChange={(e) => setKey(e.target.value)}
          placeholder="sk-ant-…"
          autoComplete="off"
          className="min-w-0 flex-1 rounded-md border border-line px-3 py-2 font-mono text-sm"
        />
        <button type="submit" disabled={busy || !key} aria-busy={busy || undefined} className="inline-flex items-center gap-2 rounded-md bg-ink px-4 py-2 text-sm font-semibold text-white disabled:opacity-40">
          {busy && <Spinner />}
          Guardar key
        </button>
      </form>
      {error && (
        <p className="mt-2 text-sm text-danger" role="alert">
          {error}
        </p>
      )}
    </details>
  );
}

const CONFIRM_WORD = "desconectar";

function Disconnect({ onDone }: { onDone: (s: ClaudeStatus) => void }) {
  const [open, setOpen] = useState(false);
  const [typed, setTyped] = useState("");
  const [busy, setBusy] = useState(false);

  async function disconnect() {
    setBusy(true);
    try {
      onDone(await apiFetch<ClaudeStatus>("/api/settings/claude/disconnect/", { method: "POST" }));
      setOpen(false);
      setTyped("");
    } finally {
      setBusy(false);
    }
  }

  if (!open) {
    return (
      <button type="button" onClick={() => setOpen(true)} className="text-sm font-medium text-danger underline">
        Desconectar
      </button>
    );
  }
  return (
    <section className="rounded-xl bg-danger-soft p-5 ring-1 ring-danger/30">
      <p className="text-sm">
        Los agentes y el asistente dejan de funcionar hasta volver a conectar. Escribe <strong>{CONFIRM_WORD}</strong> para confirmar.
      </p>
      <div className="mt-3 flex flex-wrap gap-2">
        <input
          value={typed}
          onChange={(e) => setTyped(e.target.value)}
          aria-label={`Escribe ${CONFIRM_WORD}`}
          autoComplete="off"
          className="min-w-0 flex-1 rounded-md border border-line bg-surface px-3 py-2 text-sm"
        />
        <button
          type="button"
          onClick={disconnect}
          disabled={busy || typed.trim().toLowerCase() !== CONFIRM_WORD}
          aria-busy={busy || undefined}
          className="inline-flex items-center gap-2 rounded-md bg-danger px-4 py-2 text-sm font-semibold text-white disabled:opacity-40"
        >
          {busy && <Spinner />}
          Desconectar
        </button>
        <button type="button" onClick={() => setOpen(false)} className="rounded-md px-3 py-2 text-sm">
          Cancelar
        </button>
      </div>
    </section>
  );
}

function capitalize(text: string): string {
  return text.charAt(0).toUpperCase() + text.slice(1);
}
