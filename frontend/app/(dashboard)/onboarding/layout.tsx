"use client";

import { Check } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { RoleGate } from "@/components/require-auth";
import { useOnboarding } from "@/lib/onboarding";

export default function OnboardingLayout({ children }: { children: React.ReactNode }) {
  return (
    <RoleGate roles={["manager"]}>
      <Stepper />
      {children}
    </RoleGate>
  );
}

function Stepper() {
  const pathname = usePathname();
  const steps = useOnboarding();
  return (
    <div className="mb-5">
      <h1 className="text-2xl font-bold tracking-tight">Onboarding</h1>
      <ol className="mt-3 grid grid-cols-2 gap-2 sm:grid-cols-4">
        {steps.map((step, i) => {
          const active = pathname === `/onboarding/${step.slug}`;
          return (
            <li key={step.slug}>
              <Link
                href={`/onboarding/${step.slug}`}
                aria-current={active ? "step" : undefined}
                className={`flex items-center gap-2 rounded-lg px-3 py-2 text-sm ring-1 ${active ? "bg-ink text-white ring-ink" : "bg-surface ring-line hover:bg-canvas"}`}
              >
                <span
                  className={`flex size-6 shrink-0 items-center justify-center rounded-full text-xs font-bold ${
                    step.done ? "bg-success text-white" : active ? "bg-white text-ink" : "bg-canvas text-muted"
                  }`}
                >
                  {step.done ? <Check size={14} /> : i}
                </span>
                {step.label}
              </Link>
            </li>
          );
        })}
      </ol>
    </div>
  );
}
