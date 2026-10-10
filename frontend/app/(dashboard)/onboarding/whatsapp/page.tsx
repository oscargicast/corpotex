"use client";

import { useEffect, useState } from "react";
import useSWR from "swr";
import { Button, Card, Pill, SectionTitle } from "@/components/ui";
import { ApiError, apiFetch, fetcher } from "@/lib/api";
import { formatDayTime } from "@/lib/format";
import type { WhatsAppState } from "@/lib/types";

const STATE: Record<string, { label: string; tone: "success" | "warning" | "danger" }> = {
  open: { label: "Conectado", tone: "success" },
  connecting: { label: "Conectando…", tone: "warning" },
  close: { label: "Desconectado", tone: "danger" },
};

const SETTING_LABELS: Record<string, string> = {
  groupsIgnore: "Ignorar grupos",
  rejectCall: "Rechazar llamadas",
  readMessages: "Marcar como leído",
  syncFullHistory: "Sincronizar historial",
};

function errorText(err: unknown) {
  const body = err instanceof ApiError ? (err.body as { detail?: string } | null) : null;
  return body?.detail ?? "No se pudo hablar con WhatsApp. Inténtalo de nuevo.";
}

// No buttons to disconnect or delete the instance: re-linking needs Oscar's phone.
export default function OnboardingWhatsApp() {
  const { data, mutate } = useSWR<WhatsAppState>("/api/onboarding/whatsapp/", fetcher, { refreshInterval: 3000 });
  const [qr, setQr] = useState<string | null>(null);
  const [showQr, setShowQr] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const open = data?.state === "open";

  // Baileys rotates the QR about every 20 s: ask again while it is on screen.
  useEffect(() => {
    if (!showQr || open) return;
    let alive = true;
    async function load() {
      try {
        const { qr_base64 } = await apiFetch<{ qr_base64: string | null }>("/api/onboarding/whatsapp/qr/", { method: "POST" });
        if (alive) setQr(qr_base64);
      } catch (err) {
        if (alive) setError(errorText(err));
      }
    }
    load();
    const id = setInterval(load, 20_000);
    return () => {
      alive = false;
      clearInterval(id);
    };
  }, [showQr, open]);

  async function configureWebhook() {
    setBusy(true);
    setError(null);
    try {
      mutate(await apiFetch<WhatsAppState>("/api/onboarding/whatsapp/webhook/", { method: "POST" }), { revalidate: false });
    } catch (err) {
      setError(errorText(err));
    } finally {
      setBusy(false);
    }
  }

  if (!data) return <div className="h-40 animate-pulse rounded-xl bg-line" />;
  const state = STATE[data.state] ?? { label: data.state, tone: "warning" as const };

  return (
    <div className="grid max-w-4xl items-start gap-4 lg:grid-cols-2">
      <Card>
        <SectionTitle>Instancia de WhatsApp</SectionTitle>
        <div className="flex flex-wrap items-center gap-2">
          <Pill tone={state.tone}>{state.label}</Pill>
          {data.offline && <Pill>Configurado fuera de línea</Pill>}
        </div>
        {data.done_at && <p className="mt-2 text-sm text-muted">Paso hecho el {formatDayTime(data.done_at)}.</p>}
        {!open && !data.offline && (
          <div className="mt-4">
            {!showQr ? (
              <Button kind="primary" onClick={() => setShowQr(true)}>
                Mostrar QR
              </Button>
            ) : qr ? (
              <>
                <img src={qr} alt="Código QR para vincular WhatsApp" className="size-64 rounded-lg ring-1 ring-line" />
                <p className="mt-2 text-sm text-muted">En el celular: WhatsApp → Dispositivos vinculados → Vincular un dispositivo.</p>
              </>
            ) : (
              <p className="text-sm text-muted">Pidiendo el QR…</p>
            )}
          </div>
        )}
      </Card>

      <Card>
        <SectionTitle>Webhook</SectionTitle>
        {data.webhook ? (
          <dl className="space-y-2 text-sm">
            <div>
              <dt className="text-xs text-muted">URL</dt>
              <dd className="break-all font-mono text-xs">{data.webhook.url}</dd>
            </div>
            <div>
              <dt className="text-xs text-muted">Eventos</dt>
              <dd>{data.webhook.events.join(", ")}</dd>
            </div>
            <div>
              <dt className="text-xs text-muted">Fotos en el mensaje (base64)</dt>
              <dd>{data.webhook.base64 ? "Sí" : "No"}</dd>
            </div>
          </dl>
        ) : (
          <p className="text-sm text-muted">Sin configurar.</p>
        )}
        {data.settings && (
          <ul className="mt-3 space-y-1 text-sm">
            {Object.entries(data.settings).map(([key, value]) => (
              <li key={key} className="flex justify-between gap-2">
                <span className="text-muted">{SETTING_LABELS[key] ?? key}</span>
                <span>{value === true ? "Sí" : value === false ? "No" : String(value)}</span>
              </li>
            ))}
          </ul>
        )}
        <Button kind="dark" className="mt-4" disabled={busy} onClick={configureWebhook}>
          {data.webhook ? "Volver a configurar" : "Configurar webhook"}
        </Button>
        {error && (
          <p className="mt-2 text-sm text-danger" role="alert">
            {error}
          </p>
        )}
      </Card>
    </div>
  );
}
