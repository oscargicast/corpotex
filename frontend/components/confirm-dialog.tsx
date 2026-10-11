"use client";

import { useEffect, useRef } from "react";
import { Button, type ButtonKind } from "./ui";

// One confirmation for every delicate action (Oscar, 11/10): a native dialog
// with a title, one line of consequence, Cancelar and the confirm button in
// the same look and icon as the button that opened it. Mount it to open it;
// Esc, the backdrop and Cancelar call onClose.
export function ConfirmDialog({
  title,
  text,
  note,
  error,
  busy = false,
  confirm,
  cancelLabel = "Cancelar",
  onConfirm,
  onClose,
  children,
}: {
  title: string;
  text: React.ReactNode;
  note?: React.ReactNode;
  error?: string | null;
  busy?: boolean;
  // No confirm: an informative dialog with a single close button.
  confirm?: { label: string; icon: React.ReactNode; kind?: ButtonKind; disabled?: boolean };
  cancelLabel?: string;
  onConfirm?: () => void;
  onClose: () => void;
  children?: React.ReactNode;
}) {
  const dialog = useRef<HTMLDialogElement>(null);

  useEffect(() => {
    const el = dialog.current;
    if (!el || el.open) return;
    el.showModal();
  }, []);

  return (
    <dialog
      ref={dialog}
      aria-labelledby="confirm-title"
      className="magic-in m-auto w-[min(26rem,calc(100vw-2rem))] rounded-xl bg-surface p-0 text-ink shadow-xl backdrop:bg-ink/40"
      onCancel={(e) => {
        e.preventDefault();
        if (!busy) onClose();
      }}
      // Rows and cards that open on click sit behind some of these dialogs.
      onClick={(e) => {
        e.stopPropagation();
        if (e.target === dialog.current && !busy) onClose();
      }}
    >
      <div className="p-5">
        <h2 id="confirm-title" className="text-lg font-semibold">
          {title}
        </h2>
        <p className="mt-2 text-sm">{text}</p>
        {note && <p className="mt-1 text-xs text-muted">{note}</p>}
        {children}
        {error && (
          <p className="mt-2 text-sm text-danger" role="alert">
            {error}
          </p>
        )}
        <div className="mt-4 flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
          <Button disabled={busy} onClick={onClose} autoFocus>
            {cancelLabel}
          </Button>
          {confirm && (
            <Button kind={confirm.kind ?? "secondary"} busy={busy} disabled={confirm.disabled} onClick={onConfirm}>
              {confirm.icon}
              {confirm.label}
            </Button>
          )}
        </div>
      </div>
    </dialog>
  );
}
