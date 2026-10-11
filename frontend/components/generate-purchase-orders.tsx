"use client";

import { CheckCircle2, X } from "lucide-react";
import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { ApiError, apiFetch } from "@/lib/api";
import type { GeneratedPurchaseOrders } from "@/lib/types";
import { Button } from "./ui";

// Suggested purchase orders from Inventario (ADR 0025 A): "Pedir todo" sends no
// material_ids, a row's "Generar pedido" sends its own. One purchase order per
// material; the Gerente approves the batch in the Monitor.

export function useGenerate(onDone: () => void) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<GeneratedPurchaseOrders | null>(null);

  async function generate(materialIds: number[] | null): Promise<boolean> {
    setBusy(true);
    setError(null);
    try {
      const res = await apiFetch<GeneratedPurchaseOrders>("/api/purchase-orders/generate/", { method: "POST", json: materialIds ? { material_ids: materialIds } : {} });
      setResult(res);
      onDone();
      return true;
    } catch (err) {
      const detail = err instanceof ApiError ? (err.body as { detail?: string } | null)?.detail : null;
      setError(detail ?? "No se pudo generar el pedido. Inténtalo de nuevo.");
      return false;
    } finally {
      setBusy(false);
    }
  }

  return { busy, error, result, generate, clearError: () => setError(null), clearResult: () => setResult(null) };
}

export function GenerateConfirm({
  text,
  note,
  busy,
  error,
  confirmLabel,
  onConfirm,
  onCancel,
}: {
  text: string;
  note?: string | null;
  busy: boolean;
  error: string | null;
  confirmLabel: string;
  onConfirm: () => void;
  onCancel: () => void;
}) {
  return (
    <div className="rounded-lg bg-warning-soft px-3 py-2 text-sm text-warning" onClick={(e) => e.stopPropagation()}>
      <p>{text}</p>
      {note && <p className="mt-1 text-xs">{note}</p>}
      <div className="mt-2 flex flex-wrap gap-2">
        <Button kind="dark" className="py-1" busy={busy} onClick={onConfirm}>
          {confirmLabel}
        </Button>
        <Button className="py-1" disabled={busy} onClick={onCancel}>
          Cancelar
        </Button>
      </div>
      {error && (
        <p className="mt-1 text-danger" role="alert">
          {error}
        </p>
      )}
    </div>
  );
}

// What was created, as a toast: the codes, the Gerente's approval, what was skipped.
export function GeneratedToast({ result, nameOf, onClose }: { result: GeneratedPurchaseOrders; nameOf: (materialId: number) => string; onClose: () => void }) {
  const created = result.created ?? [];
  const skipped = result.skipped ?? [];

  // Stays a while: the codes are the point. Gone after 20 s or on close (the
  // page re-renders on every poll, so the timer follows the result, not onClose).
  const close = useRef(onClose);
  useEffect(() => {
    close.current = onClose;
  });
  useEffect(() => {
    const id = setTimeout(() => close.current(), 20_000);
    return () => clearTimeout(id);
  }, [result]);

  return (
    <div
      role="status"
      className="fixed inset-x-4 bottom-20 z-50 rounded-xl bg-surface p-4 text-sm shadow-xl ring-1 ring-line md:inset-x-auto md:bottom-6 md:left-1/2 md:w-[30rem] md:-translate-x-1/2"
    >
      <div className="flex items-start gap-3">
        <CheckCircle2 size={20} className={`mt-0.5 shrink-0 ${created.length ? "text-success" : "text-muted"}`} aria-hidden />
        <div className="min-w-0 flex-1">
          <p className="font-semibold">
            {created.length === 0 ? "No se generó ningún pedido" : created.length === 1 ? "Pedido sugerido generado" : `${created.length} pedidos sugeridos generados`}
          </p>
          {created.length > 0 && (
            <p className="mt-1">
              {created.map((po, i) => (
                <span key={po.id}>
                  {i > 0 && ", "}
                  <Link href={`/purchase-orders/${po.id}`} className="whitespace-nowrap font-medium text-accent hover:underline">
                    {po.code}
                  </Link>
                  <span className="text-muted"> · {po.supplier.name}</span>
                </span>
              ))}
            </p>
          )}
          {result.decision_id && <p className="mt-1 text-muted">El Gerente aprueba la asignación en el Monitor.</p>}
          {skipped.length > 0 && (
            <ul className="mt-1 text-warning">
              {skipped.map((s) => (
                <li key={s.material_id}>
                  {nameOf(s.material_id)}: {s.reason || "sin requerimientos abiertos"}
                </li>
              ))}
            </ul>
          )}
          {created.length > 0 && (
            <Link href="/purchase-orders" className="mt-2 inline-block font-semibold text-accent hover:underline">
              Ver pedidos
            </Link>
          )}
        </div>
        <button type="button" onClick={onClose} aria-label="Cerrar aviso" className="shrink-0 p-1 text-muted hover:text-ink">
          <X size={16} />
        </button>
      </div>
    </div>
  );
}
