"use client";

import { X } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";

// A photo that opens full size in a native <dialog> (top layer). The dialog is
// portaled to <body> so its button and caption never end up nested inside the
// row, link or button that holds the thumbnail (invalid HTML, hydration error).
// It mounts after hydration so server and client render the same markup.
// Closes with Esc, the X or a click outside the image. Clicks never reach the
// row behind: React events still bubble through the portal, hence stopPropagation.
export function ZoomableImage({
  src,
  alt,
  className = "",
  style,
  loading = "lazy",
}: {
  src: string;
  alt: string;
  className?: string;
  style?: React.CSSProperties;
  loading?: "lazy" | "eager";
}) {
  const dialog = useRef<HTMLDialogElement>(null);
  const [mounted, setMounted] = useState(false);

  useEffect(() => setMounted(true), []);

  function open(e: React.SyntheticEvent) {
    e.stopPropagation();
    e.preventDefault();
    dialog.current?.showModal();
  }

  return (
    <>
      <span
        role="button"
        tabIndex={0}
        aria-label={`Ver en grande: ${alt}`}
        onClick={open}
        onKeyDown={(e) => {
          if (e.key === "Enter" || e.key === " ") open(e);
        }}
        className="inline-block cursor-zoom-in"
      >
        <img src={src} alt={alt} loading={loading} className={className} style={style} />
      </span>
      {mounted &&
        createPortal(
          <dialog
            ref={dialog}
            aria-label={alt}
            onClick={(e) => {
              e.stopPropagation();
              if (e.target === dialog.current) dialog.current.close();
            }}
            // Esc closes the dialog natively; keep the key from toggling the row.
            onKeyDown={(e) => e.stopPropagation()}
            className="m-auto max-h-[100dvh] max-w-[100vw] bg-transparent p-0 backdrop:bg-ink/85"
          >
            <button
              type="button"
              onClick={(e) => {
                e.stopPropagation();
                dialog.current?.close();
              }}
              aria-label="Cerrar"
              className="fixed right-3 top-3 rounded-full bg-ink/70 p-2 text-white hover:bg-ink"
            >
              <X size={22} />
            </button>
            {/* Only the image is inside: a click on the dark area hits the dialog itself and closes it. */}
            <img src={src} alt={alt} className="max-h-[92dvh] max-w-[96vw] rounded-lg object-contain" />
            <p className="mt-2 text-center text-sm text-white/80">{alt}</p>
          </dialog>,
          document.body,
        )}
    </>
  );
}
