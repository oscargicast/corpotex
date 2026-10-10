"use client";

import { AlertTriangle, CheckCircle2, XCircle } from "lucide-react";
import Link from "next/link";
import Markdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { CODE_PATTERN, hrefForCode } from "@/lib/codes";
import { formatDayTime } from "@/lib/format";
import type { AssistantAction, AssistantMessage, LinkKind } from "@/lib/types";
import { Pill, SEVERITY_TONE } from "../ui";

// The assistant names orders and purchase orders by code, never by URL:
// codes become links here, outside inline code spans.
// Only the routes codes link to; anything else in the model's text stays plain.
const INTERNAL_HREF = /^\/(?:(?:orders|purchase-orders|suppliers)\/[A-Za-z0-9-]+)?$/;

function linkCodes(text: string): string {
  return text
    .split(/(`[^`]*`)/)
    .map((part) => (part.startsWith("`") ? part : part.replace(CODE_PATTERN, (code) => `[${code}](${hrefForCode(code)})`)))
    .join("");
}

export function MessageBubble({ message }: { message: AssistantMessage }) {
  if (message.action) return <ActionCard action={message.action} text={message.text} />;
  const mine = message.role === "user";
  return (
    <div className={`flex ${mine ? "justify-end" : "justify-start"}`}>
      <div
        className={`max-w-[90%] rounded-2xl px-3 py-2 text-sm ${
          mine ? "rounded-br-sm bg-ink text-white" : "rounded-bl-sm bg-surface ring-1 ring-line"
        }`}
      >
        {mine ? (
          <p className="whitespace-pre-wrap">{message.text}</p>
        ) : (
          <div className="assistant-md">
            <Markdown
              remarkPlugins={[remarkGfm]}
              components={{
                // No headings or raw HTML in a bubble (agreed with personalidad).
                h1: "strong",
                h2: "strong",
                h3: "strong",
                img: () => null,
                a: ({ href = "", children }) =>
                  INTERNAL_HREF.test(href) ? (
                    <Link href={href} className="whitespace-nowrap font-medium text-accent underline">
                      {children}
                    </Link>
                  ) : (
                    <span>{children}</span>
                  ),
                table: ({ children }) => (
                  <div className="my-1 overflow-x-auto">
                    <table className="text-xs">{children}</table>
                  </div>
                ),
              }}
            >
              {linkCodes(message.text)}
            </Markdown>
          </div>
        )}
        <p className={`mt-0.5 text-right text-[10px] ${mine ? "text-white/60" : "text-muted"}`}>{formatDayTime(message.created_at)}</p>
      </div>
    </div>
  );
}

const LINK: Record<LinkKind, { label: string; href: (id: number) => string }> = {
  order: { label: "Ver orden", href: (id) => `/orders/${id}` },
  purchase_order: { label: "Ver pedido", href: (id) => `/purchase-orders/${id}` },
  decision: { label: "Ver en el Monitor", href: () => "/" },
  supplier: { label: "Ver proveedor", href: (id) => `/suppliers/${id}` },
};

function ActionCard({ action, text }: { action: AssistantAction; text: string }) {
  if (action.kind === "alert") {
    return (
      <article className="rounded-xl border-l-4 border-l-warning bg-surface p-3 text-sm ring-1 ring-line">
        <p className="flex items-center gap-1.5 font-semibold">
          <AlertTriangle size={16} className="text-warning" /> Aviso
        </p>
        {text && <p className="mt-1">{text}</p>}
        <ul className="mt-2 space-y-2">
          {action.alerts.map((alert) => (
            <li key={alert.id} className="flex flex-wrap items-center gap-2">
              <Pill tone={SEVERITY_TONE[alert.severity]}>{alert.kind_display}</Pill>
              {alert.order && (
                <Link href={`/orders/${alert.order.id}`} className="font-medium text-accent hover:underline">
                  Ver orden {alert.order.code}
                </Link>
              )}
              {alert.purchase_order && (
                <Link href={`/purchase-orders/${alert.purchase_order.id}`} className="font-medium text-accent hover:underline">
                  Ver pedido {alert.purchase_order.code}
                </Link>
              )}
            </li>
          ))}
        </ul>
      </article>
    );
  }

  const done = action.status === "done";
  return (
    <article className={`rounded-xl p-3 text-sm ring-1 ${done ? "bg-success-soft ring-success/30" : "bg-danger-soft ring-danger/30"}`}>
      <p className="flex items-center gap-1.5 font-semibold">
        {done ? <CheckCircle2 size={16} className="text-success" /> : <XCircle size={16} className="text-danger" />}
        {action.title}
      </p>
      {action.summary && <p className="mt-1">{action.summary}</p>}
      {action.links.length > 0 && (
        <p className="mt-2 flex flex-wrap gap-x-3">
          {action.links.map((link) => (
            <Link key={`${link.kind}-${link.id}`} href={LINK[link.kind].href(link.id)} className="font-medium text-accent hover:underline">
              {LINK[link.kind].label}
              {link.code ? ` ${link.code}` : ""}
            </Link>
          ))}
        </p>
      )}
    </article>
  );
}
