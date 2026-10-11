"use client";

import { useState } from "react";
import { ApiError, apiFetch } from "@/lib/api";
import { Button } from "./ui";

export interface SupplierInput {
  name: string;
  kind: "workshop" | "materials" | "finished";
  specialties: string[];
  city: string;
  weekly_capacity: number | null;
  lead_time_days: number | null;
  currency: "PEN" | "USD";
  phone: string;
}

const EMPTY = { name: "", kind: "workshop", specialties: "", city: "Piura", weekly_capacity: "", lead_time_days: "", currency: "PEN", phone: "" };

const input = "mt-1 w-full rounded-md bg-surface px-3 py-2.5 text-base ring-1 ring-line sm:text-sm";

// Same fields as the CSV import: name, kind, specialties, city, weekly_capacity,
// lead_time_days, currency, phone. Used by onboarding step 2 and /supplier-signup.
export function SupplierForm({
  endpoint,
  submitLabel,
  onCreated,
}: {
  endpoint: string;
  submitLabel: string;
  onCreated: () => void;
}) {
  const [form, setForm] = useState(EMPTY);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const set = (key: keyof typeof EMPTY) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) =>
    setForm((f) => ({ ...f, [key]: e.target.value }));
  const phoneDigits = form.phone.replace(/\D/g, "");

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (form.phone && phoneDigits.length < 9) {
      setError("Escribe el celular con código de país, por ejemplo 51987654321.");
      return;
    }
    setBusy(true);
    setError(null);
    const body: SupplierInput = {
      name: form.name.trim(),
      kind: form.kind as SupplierInput["kind"],
      specialties: form.specialties.split(/[;,]/).map((s) => s.trim()).filter(Boolean),
      city: form.city.trim(),
      weekly_capacity: form.weekly_capacity ? Number(form.weekly_capacity) : null,
      lead_time_days: form.lead_time_days ? Number(form.lead_time_days) : null,
      currency: form.currency as SupplierInput["currency"],
      phone: phoneDigits,
    };
    try {
      await apiFetch(endpoint, { method: "POST", json: body });
      setForm(EMPTY);
      onCreated();
    } catch (err) {
      const detail = err instanceof ApiError ? (err.body as Record<string, string[] | string> | null) : null;
      const first = detail && Object.values(detail)[0];
      setError(Array.isArray(first) ? first[0] : typeof first === "string" ? first : "No se pudo guardar. Revisa los datos.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={submit} className="grid gap-3 sm:grid-cols-2">
      <label className="text-sm sm:col-span-2">
        Nombre del taller o proveedor
        <input required value={form.name} onChange={set("name")} className={input} />
      </label>
      <label className="text-sm">
        Tipo
        <select value={form.kind} onChange={set("kind")} className={input}>
          <option value="workshop">Taller de confección</option>
          <option value="materials">Proveedor de insumos</option>
          <option value="finished">Producto terminado</option>
        </select>
      </label>
      <label className="text-sm">
        Ciudad
        <input value={form.city} onChange={set("city")} className={input} />
      </label>
      <label className="text-sm sm:col-span-2">
        Especialidades <span className="text-muted">(separadas por coma)</span>
        <input value={form.specialties} onChange={set("specialties")} placeholder="polo, buzo, camisa" className={input} />
      </label>
      <label className="text-sm">
        Capacidad por semana <span className="text-muted">(prendas)</span>
        <input type="number" inputMode="numeric" min={0} value={form.weekly_capacity} onChange={set("weekly_capacity")} className={input} />
      </label>
      <label className="text-sm">
        Plazo típico <span className="text-muted">(días)</span>
        <input type="number" inputMode="numeric" min={0} value={form.lead_time_days} onChange={set("lead_time_days")} className={input} />
      </label>
      <label className="text-sm">
        Moneda
        <select value={form.currency} onChange={set("currency")} className={input}>
          <option value="PEN">Soles (PEN)</option>
          <option value="USD">Dólares (USD)</option>
        </select>
      </label>
      <label className="text-sm">
        Celular de WhatsApp <span className="text-muted">(opcional)</span>
        <input value={form.phone} onChange={set("phone")} inputMode="tel" placeholder="51987654321" className={input} />
      </label>
      {!phoneDigits && (
        <p className="rounded-md bg-warning-soft px-3 py-2 text-sm text-warning sm:col-span-2">
          Sin celular, el agente no puede escribirle ni se puede extraer el estilo con este proveedor.
        </p>
      )}
      {error && (
        <p className="text-sm text-danger sm:col-span-2" role="alert">
          {error}
        </p>
      )}
      <div className="sm:col-span-2">
        <Button kind="primary" type="submit" busy={busy} className="w-full sm:w-auto">
          {busy ? "Guardando…" : submitLabel}
        </Button>
      </div>
    </form>
  );
}
