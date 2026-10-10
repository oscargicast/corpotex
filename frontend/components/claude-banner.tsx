"use client";

import Link from "next/link";
import type { Badges } from "@/lib/types";
import { useUser } from "./require-auth";

const WARN_BEFORE_MS = 3 * 24 * 3600 * 1000;

// Claude connection state (ADR 0022), from the badges poll.
export function ClaudeBanner({ badges }: { badges: Badges | undefined }) {
  const user = useUser();
  if (!badges) return null;

  if (user.role !== "manager") {
    if (badges.claude_ok) return null;
    return (
      <p className="bg-line px-4 py-2 text-sm text-ink" role="status">
        El asistente no está disponible; avisa al Gerente.
      </p>
    );
  }

  if (badges.claude_expired || badges.claude_last_error) {
    return (
      <p className="flex flex-wrap items-center gap-x-3 bg-danger px-4 py-2 text-sm text-white" role="alert">
        La conexión con Claude venció.
        <Link href="/settings/claude?reconnect=1" className="font-semibold underline">
          Reconectar
        </Link>
      </p>
    );
  }

  const expiresAt = badges.claude_refresh_expires_at ? new Date(badges.claude_refresh_expires_at).getTime() : null;
  if (expiresAt && expiresAt - Date.now() < WARN_BEFORE_MS) {
    const days = Math.max(0, Math.ceil((expiresAt - Date.now()) / (24 * 3600 * 1000)));
    return (
      <p className="flex flex-wrap items-center gap-x-3 bg-warning-soft px-4 py-2 text-sm text-warning" role="status">
        La conexión con Claude vence {days === 0 ? "hoy" : `en ${days} ${days === 1 ? "día" : "días"}`}.
        <Link href="/settings/claude?reconnect=1" className="font-semibold underline">
          Reconectar ahora
        </Link>
      </p>
    );
  }
  return null;
}
