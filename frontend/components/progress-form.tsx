"use client";

import { Camera } from "lucide-react";
import { useState } from "react";
import { apiFetch } from "@/lib/api";
import { Button } from "./ui";

// Manual progress from the dashboard (source web). Workshops usually report by WhatsApp.
export function ProgressForm({
  purchaseOrderId,
  current,
  total,
  onSaved,
}: {
  purchaseOrderId: number;
  current: number;
  total: number;
  onSaved: () => void;
}) {
  const [units, setUnits] = useState(String(current));
  const [note, setNote] = useState("");
  const [photo, setPhoto] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    const value = Number(units);
    if (!Number.isInteger(value) || value < 0 || value > total) {
      setError(`Escribe un número entre 0 y ${total}.`);
      return;
    }
    setBusy(true);
    setError(null);
    const form = new FormData();
    form.set("units_done", String(value));
    form.set("note", note);
    if (photo) form.set("photo", photo);
    try {
      await apiFetch(`/api/purchase-orders/${purchaseOrderId}/progress/`, { method: "POST", body: form });
      setNote("");
      setPhoto(null);
      onSaved();
    } catch {
      setError("No se pudo guardar el avance.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={submit} className="grid gap-3 sm:grid-cols-[8rem_1fr]">
      <label className="text-sm">
        <span className="block text-xs text-muted">Unidades listas</span>
        <input
          type="number"
          inputMode="numeric"
          min={0}
          max={total}
          value={units}
          onChange={(e) => setUnits(e.target.value)}
          className="mt-1 w-full rounded-md px-2 py-2 tabular-nums ring-1 ring-line"
        />
      </label>
      <label className="text-sm">
        <span className="block text-xs text-muted">Nota</span>
        <input value={note} onChange={(e) => setNote(e.target.value)} className="mt-1 w-full rounded-md px-2 py-2 ring-1 ring-line" />
      </label>
      <label className="flex cursor-pointer items-center gap-2 text-sm sm:col-span-2">
        <Camera size={18} className="text-muted" />
        <span className="text-accent underline">{photo ? photo.name : "Agregar foto"}</span>
        <input type="file" accept="image/*" capture="environment" className="sr-only" onChange={(e) => setPhoto(e.target.files?.[0] ?? null)} />
      </label>
      {error && (
        <p className="text-sm text-danger sm:col-span-2" role="alert">
          {error}
        </p>
      )}
      <div className="sm:col-span-2">
        <Button kind="dark" type="submit" disabled={busy}>
          Registrar avance
        </Button>
      </div>
    </form>
  );
}
