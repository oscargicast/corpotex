"use client";

import { Check, ClipboardPaste, ExternalLink, KeyRound, Unplug, X } from "lucide-react";
import { useState } from "react";
import useSWR from "swr";
import { ApiError, apiFetch, fetcher } from "@/lib/api";
import type { ClaudeErrorCode, ClaudeStatus } from "@/lib/types";
import { SkeletonCard } from "./skeleton";
import { Button, Spinner } from "./ui";

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

// The API sends these as epoch numbers (seconds or milliseconds).
function toDate(value: number | string): Date {
  if (typeof value === "string") return new Date(value);
  return new Date(value < 1e12 ? value * 1000 : value);
}

// Claude's mark, as mano draws it: strokes in currentColor.
export function ClaudeIcon({ size = 20, className = "" }: { size?: number; className?: string }) {
  return (
    <svg
      viewBox="0 0 24 24"
      width={size}
      height={size}
      aria-hidden="true"
      focusable="false"
      stroke="currentColor"
      fill="none"
      strokeWidth="1.5"
      strokeLinecap="round"
      strokeLinejoin="round"
      className={className}
    >
      <path d="M13 12L18.5 5M7.63965 3L12.5 12L13.6865 3M4.48381 6.71679L11.9872 12M3 12L11.9872 12.473M12.2244 13.177L7 20M4.84194 16.8682L11.2824 12.9758M11.5 21L12.665 13.177M21 14L13.1846 12.668M21 10.5788L13 12.3223M16.779 19.646L12.8876 13.3772M19.3566 18.207L13.313 12.9893" />
    </svg>
  );
}

const shortDate = new Intl.DateTimeFormat("es-PE", { timeZone: "America/Lima", day: "numeric", month: "short" });

// Connect the single Claude account every agent uses (ADR 0022). The flow and
// its texts follow mano's: one big "Continuar con Claude", then two steps.
export function ClaudeConnect({ reconnect = false }: { reconnect?: boolean }) {
  const { data: status, mutate } = useSWR<ClaudeStatus>(STATUS_URL, fetcher);
  const [flowOpen, setFlowOpen] = useState(reconnect);
  const [disconnecting, setDisconnecting] = useState(false);

  if (!status) return <SkeletonCard lines={2} />;

  const broken = status.expired || !!status.last_error;
  const showFlow = flowOpen || !status.connected || broken;
  const update = (next: ClaudeStatus) => mutate(next, { revalidate: false });

  return (
    <div className="space-y-4">
      {(status.connected || broken) && (
        <StatusCard
          status={status}
          onReconnect={showFlow ? undefined : () => setFlowOpen(true)}
          onDisconnect={status.connected && !disconnecting ? () => setDisconnecting(true) : undefined}
        />
      )}

      {disconnecting && (
        <Disconnect
          onDone={(next) => {
            update(next);
            setDisconnecting(false);
          }}
          onCancel={() => setDisconnecting(false)}
        />
      )}

      {showFlow && (
        <ConnectCard
          isReconnect={status.connected || broken || reconnect}
          onConnected={(next) => {
            update(next);
            setFlowOpen(false);
          }}
          onCancel={status.connected && !broken ? () => setFlowOpen(false) : undefined}
        />
      )}
    </div>
  );
}

function StatusCard({ status, onReconnect, onDisconnect }: { status: ClaudeStatus; onReconnect?: () => void; onDisconnect?: () => void }) {
  const broken = status.expired || !!status.last_error;
  let title: string[];
  let detail: string | null = null;
  let tone = "bg-success-soft ring-success/30";
  let iconTone = "bg-surface text-[#d97757]";

  if (broken) {
    tone = "bg-danger-soft ring-danger/30";
    iconTone = "bg-surface text-danger";
    title = ["La conexión con Claude venció"];
    detail = "Reconecta la cuenta para que los agentes vuelvan a responder.";
  } else if (status.method === "api_key") {
    title = ["Conectado", "clave de API"];
    detail = "Cada llamada se cobra en la consola de Anthropic.";
  } else {
    const parts = ["Conectado"];
    if (status.subscription_type) parts.push(capitalize(status.subscription_type));
    if (status.refresh_token_expires_at) parts.push(`vence el ${shortDate.format(toDate(status.refresh_token_expires_at)).replace(/\.$/, "")}`);
    title = parts;
  }

  return (
    <section className={`flex items-start gap-4 rounded-xl p-5 ring-1 ${tone}`}>
      <span className={`flex size-11 shrink-0 items-center justify-center rounded-full ring-1 ring-line ${iconTone}`}>
        <ClaudeIcon size={22} />
      </span>
      <div className="min-w-0 flex-1">
        <p className="text-lg font-semibold">
          {/* "vence el 9 nov" never splits across lines on the phone. */}
          {title.map((part, i) => (
            <span key={part} className={title.length > 1 ? "whitespace-nowrap" : undefined}>
              {i > 0 && " · "}
              {part}
            </span>
          ))}
        </p>
        {detail && <p className="mt-0.5 text-sm text-muted">{detail}</p>}
        {(onReconnect || onDisconnect) && (
          <p className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-sm">
            {onReconnect && (
              <button type="button" onClick={onReconnect} className="font-medium text-accent underline">
                Reconectar con otra cuenta
              </button>
            )}
            {onDisconnect && (
              <button type="button" onClick={onDisconnect} className="font-medium text-danger underline">
                Desconectar
              </button>
            )}
          </p>
        )}
      </div>
    </section>
  );
}

function ConnectCard({ isReconnect, onConnected, onCancel }: { isReconnect: boolean; onConnected: (s: ClaudeStatus) => void; onCancel?: () => void }) {
  const [started, setStarted] = useState(false);
  const [authUrl, setAuthUrl] = useState<string | null>(null);
  const [code, setCode] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [withKey, setWithKey] = useState(false);

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
  // Thin bar on top: choose, sign in and authorize, paste, connect.
  const progress = !started ? 12 : busy ? 92 : code.trim() ? 75 : 45;

  function restart() {
    setStarted(false);
    setCode("");
    setError(null);
  }

  return (
    <section className="overflow-hidden rounded-xl bg-surface ring-1 ring-line">
      <div className="h-1 bg-canvas" aria-hidden>
        <div className="h-full rounded-r-full bg-brand transition-[width] duration-500" style={{ width: `${progress}%` }} />
      </div>
      <div className="p-5 sm:p-6">
        {!started ? (
          <>
            <h2 className="text-lg font-semibold">Corpotex piensa con tu suscripción de Claude</h2>
            <ul className="mt-3 space-y-2 text-sm">
              {["Usa tu suscripción Claude Pro o Max.", "Una sola cuenta para WhatsApp, el asistente de cada rol y el estilo del Gerente."].map((line) => (
                <li key={line} className="flex items-start gap-2">
                  <Check size={16} className="mt-0.5 shrink-0 text-success" aria-hidden />
                  {line}
                </li>
              ))}
            </ul>
            <button
              type="button"
              onClick={start}
              disabled={busy}
              aria-busy={busy || undefined}
              className="mt-5 flex h-12 w-full items-center justify-center gap-2.5 rounded-lg bg-brand px-6 text-base font-semibold text-ink transition-colors hover:bg-brand-hover disabled:opacity-60 sm:w-auto sm:min-w-72"
            >
              {busy ? <Spinner /> : <ClaudeIcon />}
              {busy ? "Abriendo Claude…" : isReconnect ? "Conectar con Claude" : "Continuar con Claude"}
            </button>
            {error && (
              <p className="mt-2 text-sm text-danger" role="alert">
                {error}
              </p>
            )}
            <p className="mt-4 flex flex-wrap gap-x-4 gap-y-1 text-sm">
              <button type="button" onClick={() => setWithKey((v) => !v)} aria-expanded={withKey} className="text-muted underline hover:text-ink">
                Usar una clave de API (no recomendado)
              </button>
              {onCancel && (
                <button type="button" onClick={onCancel} className="text-muted underline hover:text-ink">
                  Cancelar
                </button>
              )}
            </p>
            {withKey && <ApiKeyForm onConnected={onConnected} />}
          </>
        ) : (
          <>
            <ol className="space-y-6">
              <Step number={1} done title="Inicia sesión en Claude y autoriza">
                <ul className="mt-1 space-y-0.5 text-sm text-muted">
                  <li>Inicia sesión en Claude.</li>
                  <li>Toca Authorize.</li>
                  <li>Copia el código y vuelve a Corpotex.</li>
                </ul>
                {authUrl && (
                  <a href={authUrl} target="_blank" rel="noreferrer" className="mt-2 inline-flex items-center gap-1 text-sm font-medium text-accent underline">
                    Abrir Claude otra vez <ExternalLink size={14} aria-hidden />
                  </a>
                )}
              </Step>
              <Step number={2} title="Pega el código de Claude">
                <form onSubmit={submit} className="mt-2">
                  <div className="flex gap-2">
                    <input
                      id="claude-code"
                      value={code}
                      onChange={(e) => {
                        setCode(e.target.value);
                        setError(null);
                      }}
                      placeholder="Pega tu código de autorización"
                      aria-label="Código de autorización de Claude"
                      autoComplete="one-time-code"
                      spellCheck={false}
                      autoFocus
                      className="h-12 min-w-0 flex-1 rounded-lg border border-line bg-surface px-3 font-mono text-sm"
                    />
                    {canPaste && (
                      <button
                        type="button"
                        onClick={paste}
                        aria-label="Pegar el código del portapapeles"
                        className="flex h-12 items-center gap-1.5 rounded-lg border border-line px-3 text-sm hover:bg-canvas"
                      >
                        <ClipboardPaste size={16} aria-hidden />
                        <span className="hidden sm:inline">Pegar</span>
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
                    disabled={busy || !code.trim()}
                    aria-busy={busy || undefined}
                    className="mt-3 flex h-12 w-full items-center justify-center gap-2 rounded-lg bg-brand px-6 text-base font-semibold text-ink hover:bg-brand-hover disabled:opacity-50 sm:w-auto sm:min-w-56"
                  >
                    {busy && <Spinner />}
                    {busy ? "Conectando…" : "Conectar"}
                  </button>
                </form>
              </Step>
            </ol>
            <button type="button" onClick={restart} className="mt-5 text-sm text-muted underline hover:text-ink">
              Empezar de nuevo
            </button>
          </>
        )}
      </div>
    </section>
  );
}

function Step({ number, title, done = false, children }: { number: number; title: string; done?: boolean; children: React.ReactNode }) {
  return (
    <li className="flex gap-3">
      <span
        className={`flex size-7 shrink-0 items-center justify-center rounded-full text-sm font-bold ${done ? "bg-success text-white" : "bg-ink text-white"}`}
        aria-hidden
      >
        {done ? <Check size={15} /> : number}
      </span>
      <div className="min-w-0 flex-1">
        <p className="font-semibold">
          <span className="sr-only">Paso {number}: </span>
          {title}
        </p>
        {children}
      </div>
    </li>
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
    <div className="mt-3 rounded-lg bg-canvas p-4">
      <p className="text-sm font-medium">Conecta con una clave de API</p>
      <p className="mt-1 text-sm text-muted">Reemplaza la conexión con la suscripción. Cada llamada se cobra en la consola de Anthropic.</p>
      <form onSubmit={submit} className="mt-3 flex flex-wrap gap-2">
        <input
          type="password"
          value={key}
          onChange={(e) => setKey(e.target.value)}
          placeholder="sk-ant-…"
          aria-label="Clave de API de Anthropic"
          autoComplete="off"
          className="h-11 min-w-0 flex-1 rounded-md border border-line bg-surface px-3 font-mono text-sm"
        />
        <Button type="submit" disabled={!key} busy={busy}>
          <KeyRound size={16} aria-hidden /> Guardar clave
        </Button>
      </form>
      {error && (
        <p className="mt-2 text-sm text-danger" role="alert">
          {error}
        </p>
      )}
    </div>
  );
}

const CONFIRM_WORD = "desconectar";

function Disconnect({ onDone, onCancel }: { onDone: (s: ClaudeStatus) => void; onCancel: () => void }) {
  const [typed, setTyped] = useState("");
  const [busy, setBusy] = useState(false);

  async function disconnect() {
    setBusy(true);
    try {
      onDone(await apiFetch<ClaudeStatus>("/api/settings/claude/disconnect/", { method: "POST" }));
      setTyped("");
    } finally {
      setBusy(false);
    }
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
        <Button onClick={onCancel} disabled={busy}>
          <X size={16} aria-hidden /> Cancelar
        </Button>
        <Button kind="danger" onClick={disconnect} disabled={typed.trim().toLowerCase() !== CONFIRM_WORD} busy={busy}>
          <Unplug size={16} aria-hidden /> Desconectar
        </Button>
      </div>
    </section>
  );
}

function capitalize(text: string): string {
  return text.charAt(0).toUpperCase() + text.slice(1);
}
