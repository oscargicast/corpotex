"use client";

import useSWR from "swr";
import { fetcher } from "./api";
import type { ClaudeStatus, StyleState, SupplierListItem, WhatsAppState } from "./types";

export interface OnboardingStep {
  slug: "claude" | "whatsapp" | "suppliers" | "style";
  href: string; // suppliers live in the main menu, the rest under Configuración
  label: string;
  done: boolean | undefined; // undefined while loading
}

// "Done" comes from each step's own state; there is no onboarding endpoint.
export function useOnboarding(enabled = true): OnboardingStep[] {
  const opts = { refreshInterval: 5000 };
  const { data: claude } = useSWR<ClaudeStatus>(enabled ? "/api/settings/claude/status/" : null, fetcher, opts);
  const { data: whatsapp } = useSWR<WhatsAppState>(enabled ? "/api/onboarding/whatsapp/" : null, fetcher, opts);
  const { data: suppliers } = useSWR<SupplierListItem[]>(enabled ? "/api/suppliers/" : null, fetcher, opts);
  const { data: style } = useSWR<StyleState>(enabled ? "/api/onboarding/style/" : null, fetcher, opts);

  return [
    { slug: "claude", href: "/settings/claude", label: "Claude", done: claude && claude.connected && !claude.expired },
    {
      slug: "whatsapp",
      href: "/settings/whatsapp",
      label: "WhatsApp",
      done: whatsapp && (!!whatsapp.done_at || whatsapp.offline || (whatsapp.state === "open" && !!whatsapp.webhook)),
    },
    { slug: "suppliers", href: "/suppliers", label: "Proveedores", done: suppliers && suppliers.some((s) => !s.is_in_house) },
    { slug: "style", href: "/settings/style", label: "Estilo", done: style && !!style.approved_at },
  ];
}
