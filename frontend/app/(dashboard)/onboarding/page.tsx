"use client";

import Link from "next/link";
import { Card } from "@/components/ui";
import { useOnboarding } from "@/lib/onboarding";

const ABOUT: Record<string, string> = {
  claude: "La cuenta que usan todos los agentes.",
  whatsapp: "El número desde el que el agente escribe a los proveedores.",
  suppliers: "Talleres y proveedores de insumos, con su celular.",
  style: "Cómo escribe el Gerente, sacado de sus chats.",
};

export default function OnboardingIndex() {
  const steps = useOnboarding();
  const next = steps.find((s) => s.done === false);
  return (
    <Card>
      {next ? (
        <p className="text-sm">
          Siguiente paso:{" "}
          <Link href={`/onboarding/${next.slug}`} className="font-semibold text-accent hover:underline">
            {next.label}
          </Link>
          . {ABOUT[next.slug]}
        </p>
      ) : steps.every((s) => s.done) ? (
        <p className="text-sm font-medium text-success">Todo listo: los cuatro pasos están hechos.</p>
      ) : (
        <p className="text-sm text-muted">Revisando el estado de cada paso…</p>
      )}
    </Card>
  );
}
