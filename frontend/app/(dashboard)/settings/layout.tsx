"use client";

import { Check, ChevronDown, Clock, Link2, PenLine, Rocket } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState } from "react";
import { RoleGate } from "@/components/require-auth";
import { useOnboarding } from "@/lib/onboarding";

// Configuración (ADR 0027 §4): a submenu (vertical on desktop, scrollable tabs
// on the phone) and, above it, the setup steps as a compact summary that only
// unfolds while a step is missing.
export default function SettingsLayout({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const connections = pathname.startsWith("/settings/claude") || pathname.startsWith("/settings/whatsapp");
  return (
    <RoleGate roles={["manager"]}>
      <h1 className="text-2xl font-bold tracking-tight">Configuración</h1>
      <SetupSummary />
      <div className="mt-5 md:grid md:grid-cols-[13rem_minmax(0,1fr)] md:items-start md:gap-6">
        <SettingsNav pathname={pathname} />
        <div className="mt-4 min-w-0 md:mt-0">
          {connections && <ConnectionTabs pathname={pathname} />}
          {children}
        </div>
      </div>
    </RoleGate>
  );
}

const SECTIONS = [
  { href: "/settings", label: "Seguimiento", icon: Clock, match: (p: string) => p === "/settings" },
  { href: "/settings/style", label: "Estilo", icon: PenLine, match: (p: string) => p.startsWith("/settings/style") },
  { href: "/settings/claude", label: "Conexiones", icon: Link2, match: (p: string) => p.startsWith("/settings/claude") || p.startsWith("/settings/whatsapp") },
];

function SettingsNav({ pathname }: { pathname: string }) {
  return (
    <nav aria-label="Secciones de configuración" className="-mx-4 overflow-x-auto px-4 md:mx-0 md:overflow-visible md:px-0">
      <ul className="flex gap-1 border-b border-line md:flex-col md:border-b-0">
        {SECTIONS.map(({ href, label, icon: Icon, match }) => {
          const active = match(pathname);
          return (
            <li key={href} className="shrink-0">
              <Link
                href={href}
                aria-current={active ? "page" : undefined}
                className={`flex items-center gap-2 whitespace-nowrap px-3 py-2.5 text-sm font-medium md:rounded-md ${
                  active ? "border-b-2 border-ink text-ink md:border-b-0 md:bg-ink md:text-white" : "border-b-2 border-transparent text-muted hover:text-ink md:hover:bg-canvas"
                }`}
              >
                <Icon size={16} aria-hidden />
                {label}
              </Link>
            </li>
          );
        })}
      </ul>
    </nav>
  );
}

function ConnectionTabs({ pathname }: { pathname: string }) {
  const tabs = [
    { href: "/settings/claude", label: "Claude" },
    { href: "/settings/whatsapp", label: "WhatsApp" },
  ];
  return (
    <div className="mb-4 flex w-fit rounded-lg bg-surface p-1 ring-1 ring-line" role="tablist" aria-label="Conexiones">
      {tabs.map((tab) => {
        const active = pathname.startsWith(tab.href);
        return (
          <Link key={tab.href} href={tab.href} role="tab" aria-selected={active} className={`rounded-md px-3 py-1.5 text-sm ${active ? "bg-ink text-white" : "hover:bg-canvas"}`}>
            {tab.label}
          </Link>
        );
      })}
    </div>
  );
}

const ABOUT: Record<string, string> = {
  claude: "La cuenta que usan todos los agentes.",
  whatsapp: "El número desde el que el agente escribe a los proveedores.",
  suppliers: "Talleres y proveedores de insumos, con su celular.",
  style: "Cómo escribe el Gerente, sacado de sus chats.",
};

// "Puesta en marcha 4/4": one line when everything is done; the four steps
// unfold on their own while one is missing (and on demand otherwise).
function SetupSummary() {
  const pathname = usePathname();
  const steps = useOnboarding();
  const [expanded, setExpanded] = useState(false);
  const loading = steps.some((s) => s.done === undefined);
  const done = steps.filter((s) => s.done).length;
  const missing = !loading && done < steps.length;
  const open = missing || expanded;
  const next = steps.find((s) => s.done === false);

  return (
    <section className={`mt-3 rounded-xl ring-1 ${missing ? "bg-warning-soft ring-warning/30" : "bg-surface ring-line"}`}>
      <button
        type="button"
        onClick={() => setExpanded((v) => !v)}
        disabled={missing}
        aria-expanded={open}
        className="flex w-full items-center gap-2 px-4 py-2.5 text-left text-sm disabled:cursor-default"
      >
        {loading ? (
          <span className="text-muted">Revisando la puesta en marcha…</span>
        ) : missing ? (
          <>
            <Rocket size={16} className="shrink-0 text-warning" aria-hidden />
            <span className="font-medium text-warning">
              Puesta en marcha {done}/{steps.length}
            </span>
          </>
        ) : (
          <>
            <span className="flex size-5 shrink-0 items-center justify-center rounded-full bg-success text-white">
              <Check size={12} aria-hidden />
            </span>
            <span className="font-medium">
              Puesta en marcha {done}/{steps.length}
            </span>
            <span className="text-muted">· Claude, WhatsApp, proveedores y estilo listos</span>
            <ChevronDown size={16} className={`ml-auto shrink-0 text-muted transition-transform ${open ? "rotate-180" : ""}`} aria-hidden />
          </>
        )}
      </button>
      {open && !loading && (
        <div className="border-t border-line/70 px-4 pb-3 pt-3">
          <ol className="grid grid-cols-2 gap-2 sm:grid-cols-4">
            {steps.map((step, i) => {
              const active = pathname === step.href;
              return (
                <li key={step.slug}>
                  <Link
                    href={step.href}
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
          {next && (
            <p className="mt-2 text-sm">
              Siguiente paso:{" "}
              <Link href={next.href} className="font-semibold text-accent hover:underline">
                {next.label}
              </Link>
              . {ABOUT[next.slug]}
            </p>
          )}
        </div>
      )}
    </section>
  );
}
