"use client";

import { RotateCcw } from "lucide-react";
import { useState } from "react";
import useSWR from "swr";
import { RoleGate } from "@/components/require-auth";
import { StyleMarkdown } from "@/components/style-markdown";
import { Button, Card, Pill, SectionTitle, type Tone } from "@/components/ui";
import { apiFetch, fetcher } from "@/lib/api";
import { formatDayTime } from "@/lib/format";
import type { StyleVersion, StyleVersionDetail } from "@/lib/types";

const SOURCE_TONE: Record<StyleVersion["source"], Tone> = {
  onboarding: "info",
  daily: "success",
  template: "neutral",
  manual: "warning",
  rollback: "warning",
};

export default function StylePage() {
  return (
    <RoleGate roles={["manager"]}>
      <StyleHistory />
    </RoleGate>
  );
}

// The style learns every night (ADR 0019): history with its changelog and a way back.
function StyleHistory() {
  const { data: versions, mutate } = useSWR<StyleVersion[]>("/api/style/versions/", fetcher, { refreshInterval: 10_000 });
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const currentId = versions?.[0]?.id;
  const shownId = selectedId ?? currentId;
  const { data: detail } = useSWR<StyleVersionDetail>(shownId ? `/api/style/versions/${shownId}/` : null, fetcher);
  const [confirming, setConfirming] = useState(false);
  const [busy, setBusy] = useState(false);

  async function restore() {
    if (!shownId) return;
    setBusy(true);
    try {
      await apiFetch(`/api/style/versions/${shownId}/restore/`, { method: "POST" });
      setConfirming(false);
      setSelectedId(null);
      await mutate();
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Estilo del Gerente</h1>
        <p className="mt-1 text-sm text-muted">
          Cómo escribe el agente por WhatsApp en nombre del Gerente. Aprende solo cada madrugada con los mensajes nuevos.
        </p>
      </div>

      {!versions && <div className="h-40 animate-pulse rounded-xl bg-line" />}
      {versions && !versions.length && (
        <p className="text-sm text-muted">Todavía no hay estilo. Créalo en el paso Estilo del onboarding.</p>
      )}

      {versions && versions.length > 0 && (
        <div className="grid items-start gap-4 lg:grid-cols-[22rem_1fr]">
          <Card>
            <SectionTitle count={versions.length}>Versiones</SectionTitle>
            <ol className="space-y-2">
              {versions.map((version) => (
                <li key={version.id}>
                  <button
                    type="button"
                    onClick={() => {
                      setSelectedId(version.id);
                      setConfirming(false);
                    }}
                    className={`w-full rounded-lg p-3 text-left text-sm ring-1 ${version.id === shownId ? "bg-canvas ring-ink/30" : "ring-line hover:bg-canvas"}`}
                  >
                    <span className="flex flex-wrap items-center gap-2">
                      <Pill tone={SOURCE_TONE[version.source]}>{version.source_display}</Pill>
                      {version.id === currentId && <Pill tone="success">Vigente</Pill>}
                      <span className="ml-auto text-xs text-muted">{formatDayTime(version.created_at)}</span>
                    </span>
                    {version.changelog && <span className="mt-1.5 block text-muted">{version.changelog}</span>}
                  </button>
                </li>
              ))}
            </ol>
          </Card>

          <Card>
            {detail ? (
              <>
                <div className="mb-4 flex flex-wrap items-center gap-2">
                  <h2 className="font-semibold">Versión del {formatDayTime(detail.created_at)}</h2>
                  {detail.id === currentId ? (
                    <Pill tone="success">Vigente</Pill>
                  ) : (
                    !confirming && (
                      <Button className="ml-auto" onClick={() => setConfirming(true)}>
                        <RotateCcw size={16} /> Volver a esta versión
                      </Button>
                    )
                  )}
                </div>
                {confirming && (
                  <div className="mb-4 flex flex-wrap items-center gap-2 rounded-lg bg-warning-soft px-3 py-2 text-sm text-warning">
                    El agente vuelve a escribir como en esta versión desde su próximo mensaje.
                    <Button kind="dark" className="py-1" disabled={busy} onClick={restore}>
                      Volver
                    </Button>
                    <Button className="py-1" onClick={() => setConfirming(false)}>
                      Cancelar
                    </Button>
                  </div>
                )}
                <StyleMarkdown source={detail.style_md} />
              </>
            ) : (
              <div className="h-40 animate-pulse rounded-lg bg-line" />
            )}
          </Card>
        </div>
      )}
    </div>
  );
}
