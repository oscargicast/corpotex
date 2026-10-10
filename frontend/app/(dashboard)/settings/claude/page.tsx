"use client";

import { useSearchParams } from "next/navigation";
import { Suspense } from "react";
import { ClaudeConnect } from "@/components/claude-connect";
import { RoleGate } from "@/components/require-auth";

export default function ClaudeSettingsPage() {
  return (
    <RoleGate roles={["manager"]}>
      <section className="max-w-2xl">
        <h1 className="text-2xl font-bold tracking-tight">Conexión con Claude</h1>
        <p className="mt-1 text-sm text-muted">
          Una sola cuenta para todos los agentes: WhatsApp, el asistente de cada rol y el estilo del Gerente.
        </p>
        <div className="mt-6">
          <Suspense>
            <WithReconnectParam />
          </Suspense>
        </div>
      </section>
    </RoleGate>
  );
}

function WithReconnectParam() {
  const reconnect = useSearchParams().get("reconnect") === "1";
  return <ClaudeConnect reconnect={reconnect} />;
}
