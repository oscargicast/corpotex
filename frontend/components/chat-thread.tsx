"use client";

import { ImageIcon } from "lucide-react";
import { useEffect, useRef } from "react";
import { formatDayTime } from "@/lib/format";
import type { ChatMessage } from "@/lib/types";

const AUTHOR: Record<ChatMessage["author"], string> = {
  supplier: "Proveedor",
  agent: "Agente",
  manager: "Gerente",
  system: "Sistema",
};

// WhatsApp-like thread: our side (agent, manager) on the right. Reused by the simulator.
// Scrolls its own box to the newest message, never the page.
export function ChatThread({
  messages,
  typing = false,
  large = false,
  className = "max-h-96",
  perspective = "us",
}: {
  messages: ChatMessage[];
  typing?: boolean;
  large?: boolean;
  className?: string;
  // "supplier" in the simulator: the operator writes as the supplier, so those go right.
  perspective?: "us" | "supplier";
}) {
  const box = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (box.current) box.current.scrollTop = box.current.scrollHeight;
  }, [messages.length, typing]);

  // The empty state keeps the same box, so the composer stays at the bottom.
  if (!messages.length && !typing) {
    return (
      <div className={`flex items-center justify-center rounded-lg bg-[#efeae2] p-3 text-sm text-muted ${className}`}>Todavía no hay mensajes.</div>
    );
  }

  return (
    <div ref={box} className={`space-y-2 overflow-y-auto rounded-lg bg-[#efeae2] p-3 ${large ? "text-lg" : "text-sm"} ${className}`}>
      {messages.map((message) => {
        const ours = perspective === "supplier" ? message.direction === "inbound" : message.direction === "outbound";
        return (
          <div key={message.id} className={`flex ${ours ? "justify-end" : "justify-start"}`}>
            <div className={`max-w-[85%] rounded-2xl px-3 py-2 ${ours ? "rounded-br-sm bg-[#d9fdd3]" : "rounded-bl-sm bg-surface ring-1 ring-line"}`}>
              {message.author !== "supplier" && <p className="text-[0.7em] font-semibold text-muted">{AUTHOR[message.author]}</p>}
              {/* The API sends media without a kind: anything with a file is shown as a photo. */}
              {(message.media_kind === "image" || (message.media && !message.media_kind)) &&
                (message.media ? (
                  // Photos come from /media/ (Django).
                  <img src={message.media} alt="Foto del avance" className="mb-1 max-h-60 rounded-lg" loading="lazy" />
                ) : (
                  <p className="mb-1 flex items-center gap-1 text-xs text-muted">
                    <ImageIcon size={14} /> foto
                  </p>
                ))}
              <p className="whitespace-pre-wrap">{message.text}</p>
              <p className="mt-0.5 text-right text-[10px] text-muted">{formatDayTime(message.sent_at)}</p>
            </div>
          </div>
        );
      })}
      {typing && (
        <div className={`flex ${perspective === "supplier" ? "justify-start" : "justify-end"}`}>
          <p className="rounded-2xl bg-surface px-3 py-2 text-[0.8em] text-muted ring-1 ring-line">Escribiendo…</p>
        </div>
      )}
    </div>
  );
}
