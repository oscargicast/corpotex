"use client";

import { Camera, CheckCircle2 } from "lucide-react";
import { useParams } from "next/navigation";
import { useState } from "react";
import useSWR from "swr";
import { Thumb } from "@/components/thumb";
import { apiFetch, fetcher } from "@/lib/api";
import { formatDay } from "@/lib/format";

import type { components } from "@/lib/api-types";
import { SkeletonLines } from "@/components/skeleton";
import { Spinner } from "@/components/ui";

type Report = components["schemas"]["PublicReport"];

// Public, mobile-first page for a workshop to report progress (ADR 0024 C).
// No login: the token in the URL identifies the purchase order. No prices, no supplier name.
export default function ReportPage() {
  const { token } = useParams<{ token: string }>();
  const url = `/api/report/${encodeURIComponent(token)}/`;
  const { data, error, mutate } = useSWR<Report>(url, fetcher);
  const [units, setUnits] = useState<string | null>(null);
  const [note, setNote] = useState("");
  const [photo, setPhoto] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const [sent, setSent] = useState(false);
  const [problem, setProblem] = useState<string | null>(null);

  if (error) return <Shell>Este enlace no es válido o venció. Pídele uno nuevo a Corpotex.</Shell>;
  if (!data)
    return (
      <Shell>
        <SkeletonLines lines={3} />
      </Shell>
    );

  const total = Number(data.quantity);
  const value = units ?? String(data.units_done);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    const n = Number(value);
    if (!Number.isInteger(n) || n < 0 || n > total) {
      setProblem(`Escribe un número entre 0 y ${total}.`);
      return;
    }
    setBusy(true);
    setProblem(null);
    const form = new FormData();
    form.set("units_done", String(n));
    form.set("note", note);
    if (photo) form.set("photo", photo);
    try {
      await apiFetch(url, { method: "POST", body: form });
      setSent(true);
      mutate();
    } catch {
      setProblem("No se pudo enviar. Revisa tu conexión e inténtalo de nuevo.");
    } finally {
      setBusy(false);
    }
  }

  if (sent) {
    return (
      <Shell>
        <CheckCircle2 className="mx-auto text-success" size={44} />
        <h1 className="mt-3 text-xl font-bold">Avance registrado</h1>
        <p className="mt-2 text-sm text-muted">
          {value} de {total} listas. Gracias, te confirmamos por WhatsApp.
        </p>
        <button type="button" onClick={() => setSent(false)} className="mt-5 text-sm font-medium text-accent underline">
          Reportar otro avance
        </button>
      </Shell>
    );
  }

  return (
    <main className="mx-auto max-w-md px-4 py-6">
      <p className="text-xl font-black tracking-tight">CORPOTEX</p>
      <section className="mt-5 flex items-center gap-3 rounded-xl bg-surface p-4 ring-1 ring-line">
        <Thumb src={data.product?.image} alt={data.product?.name ?? "Producto"} size={56} />
        <div className="text-sm">
          <p className="font-semibold">{data.product?.name ?? "Pedido"}</p>
          <p className="text-muted">
            Pedido {data.code} · {total} prendas{data.committed_on ? ` · entrega ${formatDay(data.committed_on)}` : ""}
          </p>
        </div>
      </section>

      <form onSubmit={submit} className="mt-5 space-y-4 rounded-xl bg-surface p-4 ring-1 ring-line">
        <label className="block text-sm font-medium">
          ¿Cuántas prendas tienes listas?
          <input
            type="number"
            inputMode="numeric"
            min={0}
            max={total}
            value={value}
            onChange={(e) => setUnits(e.target.value)}
            className="mt-1 w-full rounded-md px-3 py-3 text-2xl font-bold tabular-nums ring-1 ring-line"
          />
          <span className="mt-1 block text-xs font-normal text-muted">Antes: {data.units_done} de {total}</span>
        </label>
        <label className="flex cursor-pointer items-center justify-center gap-2 rounded-md border-2 border-dashed border-line py-4 text-sm font-medium">
          <Camera size={20} />
          {photo ? photo.name : "Tomar una foto del avance"}
          <input type="file" accept="image/*" capture="environment" className="sr-only" onChange={(e) => setPhoto(e.target.files?.[0] ?? null)} />
        </label>
        <label className="block text-sm font-medium">
          Comentario <span className="font-normal text-muted">(opcional)</span>
          <input value={note} onChange={(e) => setNote(e.target.value)} className="mt-1 w-full rounded-md px-3 py-2.5 ring-1 ring-line" />
        </label>
        {problem && (
          <p className="text-sm text-danger" role="alert">
            {problem}
          </p>
        )}
        <button
          type="submit"
          disabled={busy}
          aria-busy={busy || undefined}
          className="inline-flex w-full items-center justify-center gap-2 rounded-md bg-brand py-3 text-base font-semibold text-ink hover:bg-brand-hover disabled:opacity-60"
        >
          {busy && <Spinner />}
          {busy ? "Enviando…" : "Enviar avance"}
        </button>
      </form>
    </main>
  );
}

function Shell({ children }: { children: React.ReactNode }) {
  return (
    <main className="mx-auto max-w-md px-4 py-10 text-center">
      <p className="text-xl font-black tracking-tight">CORPOTEX</p>
      <div className="mt-6 rounded-xl bg-surface p-6 ring-1 ring-line">{children}</div>
    </main>
  );
}
