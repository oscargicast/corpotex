"use client";

import Markdown from "react-markdown";
import remarkGfm from "remark-gfm";

type Block = { kind: "md"; text: string } | { kind: "chat"; lines: { who: "P" | "G"; text: string }[] };

const CHAT_LINE = /^\[(P|G)\]\s*(.*)$/;

// Example exchanges come as "[P] …" (supplier) and "[G] …" (Gerente) lines.
// They render as chat bubbles; the rest is plain markdown.
function blocks(source: string): Block[] {
  const out: Block[] = [];
  for (const line of source.split("\n")) {
    const match = line.trim().match(CHAT_LINE);
    const last = out.at(-1);
    if (match) {
      const entry = { who: match[1] as "P" | "G", text: match[2] };
      if (last?.kind === "chat") last.lines.push(entry);
      else out.push({ kind: "chat", lines: [entry] });
    } else if (last?.kind === "md") {
      last.text += `\n${line}`;
    } else {
      out.push({ kind: "md", text: line });
    }
  }
  return out;
}

export function StyleMarkdown({ source, large = false }: { source: string; large?: boolean }) {
  return (
    <div className={`style-md ${large ? "text-base" : "text-sm"}`}>
      {blocks(source).map((block, i) =>
        block.kind === "md" ? (
          <Markdown key={i} remarkPlugins={[remarkGfm]} components={{ img: () => null, a: ({ children }) => <span>{children}</span> }}>
            {block.text}
          </Markdown>
        ) : (
          <div key={i} className="my-3 space-y-1.5 rounded-lg bg-[#efeae2] p-3">
            {block.lines.map((line, j) => (
              <div key={j} className={`flex ${line.who === "G" ? "justify-end" : "justify-start"}`}>
                <p className={`max-w-[85%] rounded-2xl px-3 py-1.5 ${line.who === "G" ? "rounded-br-sm bg-[#d9fdd3]" : "rounded-bl-sm bg-surface"}`}>
                  <span className="block text-[0.7em] font-semibold text-muted">{line.who === "G" ? "Gerente" : "Proveedor"}</span>
                  {line.text}
                </p>
              </div>
            ))}
          </div>
        ),
      )}
    </div>
  );
}
