"use client";

import { X } from "lucide-react";
import { useRef } from "react";

// A photo that opens full size in a native <dialog> (top layer, so it works
// inside cards, table rows and buttons). Closes with Esc, the X or a click
// outside the image. Clicks never reach the row behind.
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
      <dialog
        ref={dialog}
        aria-label={alt}
        onClick={(e) => {
          e.stopPropagation();
          if (e.target === dialog.current) dialog.current.close();
        }}
        className="m-auto max-h-[100dvh] max-w-[100vw] bg-transparent p-0 backdrop:bg-ink/85"
      >
        <button
          type="button"
          onClick={() => dialog.current?.close()}
          aria-label="Cerrar"
          className="fixed right-3 top-3 rounded-full bg-ink/70 p-2 text-white hover:bg-ink"
        >
          <X size={22} />
        </button>
        {/* Only the image is inside: a click on the dark area hits the dialog itself and closes it. */}
        <img src={src} alt={alt} className="max-h-[92dvh] max-w-[96vw] rounded-lg object-contain" />
        <p className="mt-2 text-center text-sm text-white/80">{alt}</p>
      </dialog>
    </>
  );
}
