"use client";

import { useEffect, useRef, useState } from "react";

// Generated text (the agent's summaries, alert texts): two lines, then "ver más".
export function ClampedText({ text, className = "" }: { text: string; className?: string }) {
  const ref = useRef<HTMLParagraphElement | null>(null);
  const [open, setOpen] = useState(false);
  const [overflows, setOverflows] = useState(false);
  useEffect(() => {
    const el = ref.current;
    if (el && !open) setOverflows(el.scrollHeight > el.clientHeight + 1);
  }, [text, open]);
  return (
    <div className={className}>
      <p ref={ref} className={open ? "" : "line-clamp-2"}>
        {text}
      </p>
      {(overflows || open) && (
        <button type="button" onClick={() => setOpen((v) => !v)} className="mt-0.5 text-xs font-medium text-accent hover:underline">
          {open ? "ver menos" : "ver más"}
        </button>
      )}
    </div>
  );
}
