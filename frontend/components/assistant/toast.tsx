"use client";

import { Sparkles, X } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import type { Badges } from "@/lib/types";

// A short toast when a new notice arrives and the chat is closed (ADR 0020).
// Only messages newer than the first poll of this tab: old unread ones show in the counter.
export function AssistantToast({ badges, chatOpen, onOpen }: { badges: Badges | undefined; chatOpen: boolean; onOpen: () => void }) {
  const seen = useRef<number | null>(null);
  const [toast, setToast] = useState<{ id: number; preview: string } | null>(null);

  useEffect(() => {
    const latest = badges?.latest_unread;
    if (!badges) return;
    if (seen.current === null) {
      seen.current = latest?.id ?? 0;
      return;
    }
    if (latest && latest.id > seen.current) {
      seen.current = latest.id;
      if (!chatOpen) setToast({ id: latest.id, preview: latest.preview });
    }
  }, [badges, chatOpen]);

  useEffect(() => {
    if (!toast) return;
    const id = setTimeout(() => setToast(null), 5000);
    return () => clearTimeout(id);
  }, [toast]);

  if (!toast || chatOpen) return null;
  return (
    <div
      role="status"
      className="fixed inset-x-4 top-16 z-50 flex items-start gap-3 rounded-xl bg-ink p-3 text-sm text-white shadow-xl md:inset-x-auto md:bottom-6 md:right-6 md:top-auto md:w-96"
    >
      <Sparkles size={18} className="mt-0.5 shrink-0 text-brand" />
      <p className="flex-1">{toast.preview}</p>
      <button
        type="button"
        onClick={() => {
          setToast(null);
          onOpen();
        }}
        className="shrink-0 rounded-md bg-white/10 px-2 py-1 font-semibold hover:bg-white/20"
      >
        Abrir
      </button>
      <button type="button" onClick={() => setToast(null)} aria-label="Cerrar aviso" className="shrink-0 p-1 text-white/70 hover:text-white">
        <X size={16} />
      </button>
    </div>
  );
}
