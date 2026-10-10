"use client";

import { Plus } from "lucide-react";
import { useRouter } from "next/navigation";
import { useRef, useState } from "react";
import examples from "@/mocks/order-examples.json";
import { apiFetch } from "@/lib/api";
import type { Clock, OrderListItem } from "@/lib/types";
import { Button } from "./ui";

// Stand-in for Comercial's system: posts an example order to POST /api/orders/.
// The code is generated once per click, so a retry stays idempotent.
export function SimulateOrder() {
  const router = useRouter();
  const dialog = useRef<HTMLDialogElement>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function send(index: number) {
    setBusy(true);
    setError(null);
    const { promised_on_in_days, ...payload } = examples[index].payload;
    const code = `CP-${Date.now()}`;
    try {
      const clock = await apiFetch<Clock>("/api/clock/");
      const promised = new Date(new Date(clock.now).getTime() + promised_on_in_days * 86_400_000);
      const order = await apiFetch<OrderListItem>("/api/orders/", {
        method: "POST",
        json: { ...payload, code, promised_on: promised.toISOString().slice(0, 10) },
      });
      dialog.current?.close();
      router.push(`/orders/${order.id}`);
    } catch {
      setError("No se pudo registrar la orden. Inténtalo de nuevo.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <Button kind="primary" onClick={() => dialog.current?.showModal()}>
        <Plus size={16} /> Simular orden de Comercial
      </Button>
      <dialog ref={dialog} className="m-auto w-[min(28rem,calc(100vw-2rem))] rounded-xl p-0 backdrop:bg-ink/40">
        <div className="p-5">
          <h2 className="text-lg font-semibold">Simular orden de Comercial</h2>
          <p className="mt-1 text-sm text-muted">Llega por la API como si viniera del sistema de Comercial.</p>
          <ul className="mt-4 space-y-2">
            {examples.map((example, i) => (
              <li key={example.label}>
                <button
                  type="button"
                  disabled={busy}
                  onClick={() => send(i)}
                  className="w-full rounded-lg p-3 text-left text-sm ring-1 ring-line hover:bg-canvas disabled:opacity-50"
                >
                  {example.label}
                </button>
              </li>
            ))}
          </ul>
          {error && (
            <p className="mt-3 text-sm text-danger" role="alert">
              {error}
            </p>
          )}
          <div className="mt-4 text-right">
            <Button onClick={() => dialog.current?.close()}>Cancelar</Button>
          </div>
        </div>
      </dialog>
    </>
  );
}
