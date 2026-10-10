import { ClaudeConnect } from "@/components/claude-connect";

// Step 0 reuses /settings/claude (ADR 0022).
export default function OnboardingClaude() {
  return (
    <section className="max-w-2xl">
      <p className="mb-4 text-sm text-muted">Una sola cuenta de Claude para todos los agentes: WhatsApp, el asistente de cada rol y el estilo.</p>
      <ClaudeConnect />
    </section>
  );
}
