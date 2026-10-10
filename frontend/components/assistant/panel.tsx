"use client";

import { Sparkles, X } from "lucide-react";
import { AssistantChat } from "./chat";

// Desktop side panel, over the content so two windows of 960 px still fit.
export function AssistantPanel({ open, onClose }: { open: boolean; onClose: () => void }) {
  return (
    <aside
      aria-label="Asistente"
      aria-hidden={!open}
      className={`fixed inset-y-0 right-0 z-40 hidden w-[min(26rem,100vw)] flex-col border-l border-line bg-canvas shadow-2xl transition-transform md:flex ${
        open ? "translate-x-0" : "pointer-events-none translate-x-full"
      }`}
    >
      <header className="flex h-14 shrink-0 items-center gap-2 border-b border-line bg-surface px-4">
        <Sparkles size={18} />
        <h2 className="font-semibold">Asistente</h2>
        <button type="button" onClick={onClose} className="ml-auto rounded-md p-1.5 hover:bg-canvas" aria-label="Cerrar asistente">
          <X size={18} />
        </button>
      </header>
      {/* Mounted only while open: it polls every 3 s and marks messages as read. */}
      {open && <AssistantChat />}
    </aside>
  );
}
