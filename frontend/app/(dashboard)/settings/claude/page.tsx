"use client";

import { useSearchParams } from "next/navigation";
import { Suspense } from "react";
import { ClaudeConnect } from "@/components/claude-connect";

// Step 0 of Configuración (ADR 0022). ?reconnect=1 (the Claude banner) opens the flow.
export default function ClaudeSettingsPage() {
  return (
    <section className="max-w-2xl">
      <Suspense>
        <WithReconnectParam />
      </Suspense>
    </section>
  );
}

function WithReconnectParam() {
  const reconnect = useSearchParams().get("reconnect") === "1";
  return <ClaudeConnect reconnect={reconnect} />;
}
