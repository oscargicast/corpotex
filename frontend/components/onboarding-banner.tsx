"use client";

import { ListChecks } from "lucide-react";
import Link from "next/link";
import { useOnboarding } from "@/lib/onboarding";
import { useUser } from "./require-auth";

// Shown on the Monitor while an onboarding step is missing (Gerente only).
export function OnboardingBanner() {
  const user = useUser();
  const steps = useOnboarding(user.role === "manager");
  const missing = steps.filter((s) => s.done === false);
  if (user.role !== "manager" || !missing.length) return null;
  const next = missing[0];
  return (
    <Link
      href={`/settings/${next.slug}`}
      className="flex items-center gap-3 rounded-xl bg-warning-soft px-4 py-3 text-sm text-warning ring-1 ring-warning/20 hover:bg-warning-soft/80"
    >
      <ListChecks size={18} className="shrink-0" />
      <span>
        Falta{missing.length > 1 ? "n" : ""} {missing.length} paso{missing.length > 1 ? "s" : ""} de la configuración: {missing.map((s) => s.label).join(", ")}.{" "}
        <span className="font-semibold underline">Continuar con {next.label}</span>
      </span>
    </Link>
  );
}
