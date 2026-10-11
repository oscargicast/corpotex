"use client";

import { Plus, Trash2 } from "lucide-react";
import { useState } from "react";
import useSWR from "swr";
import { ApiError, apiFetch, fetcher } from "@/lib/api";
import type { Material, SupplierDetail } from "@/lib/types";
import { Button } from "./ui";
import { FOLLOW_UP_MODES } from "@/lib/follow-up";

type Kind = "workshop" | "material" | "finished";
type Currency = "PEN" | "USD";

interface Values {
  name: string;
  kind: Kind;
  specialties: string;
  city: string;
  address: string;
  weekly_capacity: string;
  lead_time_days: string;
  follow_up_mode: string; // "" = use the general mode
  currency: Currency;
  phone: string;
  contact_name: string;
  notes: string;
}

// One historical rate: a material or a product, never both (RateInRequest).
interface RateRow {
  key: string;
  material_id: number | null;
  product_id: number | null;
  item_name: string;
  unit_price: string;
  valid_from: string;
}

const EMPTY: Values = {
  name: "",
  kind: "workshop",
  specialties: "",
  city: "Piura",
  address: "",
  weekly_capacity: "",
  lead_time_days: "",
  follow_up_mode: "",
  currency: "PEN",
  phone: "",
  contact_name: "",
  notes: "",
};

const today = () => new Date().toISOString().slice(0, 10);

function fromSupplier(s: SupplierDetail): Values {
  return {
    name: s.name,
    kind: s.kind,
    specialties: s.specialties.join(", "),
    city: s.city,
    address: s.address ?? "",
    weekly_capacity: s.weekly_capacity ? String(s.weekly_capacity) : "",
    lead_time_days: s.lead_time_days ? String(s.lead_time_days) : "",
    follow_up_mode: s.follow_up_mode ?? "",
    currency: s.currency,
    phone: "",
    contact_name: "",
    notes: s.notes ?? "",
  };
}

function ratesFromSupplier(s: SupplierDetail): RateRow[] {
  return s.rates.map((r) => ({
    key: `r${r.id}`,
    material_id: r.material_id ?? null,
    product_id: r.product_id ?? null,
    item_name: r.item_name,
    unit_price: String(r.unit_price),
    valid_from: r.valid_from,
  }));
}

function firstError(err: unknown): string {
  if (err instanceof ApiError) {
    const body = err.body as Record<string, unknown> | null;
    if (body) {
      if (typeof body.detail === "string") return body.detail;
      for (const [field, value] of Object.entries(body)) {
        const text = Array.isArray(value) ? value[0] : value;
        if (typeof text === "string") return field === "non_field_errors" ? text : `${field}: ${text}`;
        if (text && typeof text === "object") return `${field}: ${JSON.stringify(text)}`;
      }
    }
  }
  return "No se pudo guardar. Revisa los datos.";
}

const input = "mt-1 w-full rounded-md bg-surface px-3 py-2.5 text-base ring-1 ring-line sm:text-sm";

// Create (POST, with the first WhatsApp number) or edit (PATCH, every editable
// field plus the full list of rates) a supplier. Used by /suppliers (new and
// edit), the onboarding and the public /supplier-signup.
export function SupplierForm({
  endpoint,
  method = "POST",
  supplier,
  submitLabel,
  onSaved,
  onCancel,
}: {
  endpoint: string;
  method?: "POST" | "PATCH";
  supplier?: SupplierDetail;
  submitLabel: string;
  onSaved: () => void;
  onCancel?: () => void;
}) {
  const editing = method === "PATCH";
  const [form, setForm] = useState<Values>(supplier ? fromSupplier(supplier) : EMPTY);
  const [rates, setRates] = useState<RateRow[]>(supplier ? ratesFromSupplier(supplier) : []);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const set = (key: keyof Values) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement>) =>
    setForm((f) => ({ ...f, [key]: e.target.value }));
  const phoneDigits = form.phone.replace(/\D/g, "");

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!editing && form.phone && phoneDigits.length < 9) {
      setError("Escribe el celular con código de país, por ejemplo 51987654321.");
      return;
    }
    const badRate = rates.find((r) => !(Number(r.unit_price) > 0) || !r.valid_from);
    if (badRate) {
      setError(`Revisa la tarifa de ${badRate.item_name || "la fila nueva"}: precio mayor a 0 y fecha.`);
      return;
    }
    setBusy(true);
    setError(null);
    const body: Record<string, unknown> = {
      name: form.name.trim(),
      kind: form.kind,
      specialties: form.specialties.split(/[;,]/).map((s) => s.trim()).filter(Boolean),
      city: form.city.trim(),
      address: form.address.trim(),
      weekly_capacity: form.weekly_capacity ? Number(form.weekly_capacity) : null,
      lead_time_days: form.lead_time_days ? Number(form.lead_time_days) : null,
      currency: form.currency,
    };
    if (editing) body.follow_up_mode = form.follow_up_mode;
    if (editing) {
      body.notes = form.notes;
      body.rates = rates.map((r) => ({
        material_id: r.material_id,
        product_id: r.product_id,
        unit_price: r.unit_price,
        valid_from: r.valid_from,
      }));
    } else {
      body.phone = phoneDigits;
      if (phoneDigits && form.contact_name.trim()) body.contact_name = form.contact_name.trim();
    }
    try {
      await apiFetch(endpoint, { method, json: body });
      if (!editing) {
        setForm(EMPTY);
        setRates([]);
      }
      onSaved();
    } catch (err) {
      setError(firstError(err));
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
          <option value="material">Proveedor de insumos</option>
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
      {editing && (
        <label className="text-sm sm:col-span-2">
          Dirección <span className="text-muted">(opcional)</span>
          <input value={form.address} onChange={set("address")} className={input} />
        </label>
      )}
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
      {editing ? (
        <label className="text-sm">
          Seguimiento
          <select value={form.follow_up_mode} onChange={set("follow_up_mode")} className={input}>
            <option value="">Usar el general</option>
            {Object.entries(FOLLOW_UP_MODES).map(([value, mode]) => (
              <option key={value} value={value}>
                {mode.label}
              </option>
            ))}
          </select>
        </label>
      ) : (
        <>
          <label className="text-sm">
            Celular de WhatsApp <span className="text-muted">(opcional)</span>
            <input value={form.phone} onChange={set("phone")} inputMode="tel" placeholder="51987654321" className={input} />
          </label>
          {phoneDigits && (
            <label className="text-sm sm:col-span-2">
              Nombre del contacto <span className="text-muted">(opcional)</span>
              <input value={form.contact_name} onChange={set("contact_name")} placeholder="dueño, encargado" className={input} />
            </label>
          )}
          {!phoneDigits && (
            <p className="rounded-md bg-warning-soft px-3 py-2 text-sm text-warning sm:col-span-2">
              Sin celular, el agente no puede escribirle ni se puede extraer el estilo con este proveedor.
            </p>
          )}
        </>
      )}

      {editing && (
        <>
          <label className="text-sm sm:col-span-2">
            Notas de trato <span className="text-muted">(el agente las lee antes de escribirle)</span>
            <textarea value={form.notes} onChange={set("notes")} rows={4} placeholder={"Trato: tú o usted\nTono:\nInsistencia:\nHorario:\nOjo:"} className={`${input} font-mono text-xs`} />
          </label>
          <RatesEditor rows={rates} currency={form.currency} onChange={setRates} />
        </>
      )}

      {error && (
        <p className="text-sm text-danger sm:col-span-2" role="alert">
          {error}
        </p>
      )}
      <div className="flex flex-wrap gap-2 sm:col-span-2">
        <Button kind="primary" type="submit" busy={busy} className="w-full sm:w-auto">
          {busy ? "Guardando…" : submitLabel}
        </Button>
        {onCancel && (
          <Button type="button" onClick={onCancel} disabled={busy} className="w-full sm:w-auto">
            Cancelar
          </Button>
        )}
      </div>
    </form>
  );
}

// Historical rates per material (and the product rates already registered).
// The list sent replaces the supplier's rates, so removing a row deletes it.
function RatesEditor({ rows, currency, onChange }: { rows: RateRow[]; currency: Currency; onChange: (rows: RateRow[]) => void }) {
  const { data: materials } = useSWR<Material[]>("/api/materials/", fetcher);
  const [picking, setPicking] = useState("");
  const used = new Set(rows.map((r) => r.material_id).filter(Boolean));
  const options = (materials ?? []).filter((m) => !used.has(m.id));

  function update(key: string, patch: Partial<RateRow>) {
    onChange(rows.map((r) => (r.key === key ? { ...r, ...patch } : r)));
  }

  function add() {
    const material = options.find((m) => String(m.id) === picking);
    if (!material) return;
    onChange([...rows, { key: `m${material.id}-${Date.now()}`, material_id: material.id, product_id: null, item_name: `${material.name} (${material.unit})`, unit_price: "", valid_from: today() }]);
    setPicking("");
  }

  return (
    <fieldset className="sm:col-span-2">
      <legend className="text-sm font-medium">Tarifas ({currency})</legend>
      {rows.length > 0 && (
        <ul className="mt-2 divide-y divide-line rounded-md ring-1 ring-line">
          {rows.map((row) => (
            <li key={row.key} className="grid grid-cols-[1fr_6rem_8.5rem_2rem] items-center gap-2 px-2 py-1.5 text-sm">
              <span className="truncate" title={row.item_name}>
                {row.item_name}
              </span>
              <input
                type="number"
                inputMode="decimal"
                min={0}
                step="0.01"
                value={row.unit_price}
                onChange={(e) => update(row.key, { unit_price: e.target.value })}
                aria-label={`Precio de ${row.item_name}`}
                className="w-full rounded-md px-2 py-1 text-right tabular-nums ring-1 ring-line"
              />
              <input
                type="date"
                value={row.valid_from}
                onChange={(e) => update(row.key, { valid_from: e.target.value })}
                aria-label={`Vigente desde, ${row.item_name}`}
                className="w-full rounded-md px-2 py-1 text-xs ring-1 ring-line"
              />
              <button type="button" onClick={() => onChange(rows.filter((r) => r.key !== row.key))} className="rounded-md p-1 text-muted hover:bg-canvas hover:text-danger" aria-label={`Quitar tarifa de ${row.item_name}`}>
                <Trash2 size={16} />
              </button>
            </li>
          ))}
        </ul>
      )}
      <div className="mt-2 flex flex-wrap items-center gap-2">
        <select value={picking} onChange={(e) => setPicking(e.target.value)} aria-label="Insumo para la tarifa nueva" className="min-w-0 flex-1 rounded-md bg-surface px-2 py-1.5 text-sm ring-1 ring-line">
          <option value="">{materials ? "Agregar tarifa de un insumo…" : "Cargando insumos…"}</option>
          {options.map((m) => (
            <option key={m.id} value={m.id}>
              {m.sku} · {m.name}
            </option>
          ))}
        </select>
        <Button type="button" onClick={add} disabled={!picking} className="py-1.5">
          <Plus size={16} /> Agregar
        </Button>
      </div>
      <p className="mt-1 text-xs text-muted">Las tarifas de productos terminados se registran desde el pedido; aquí se corrigen precio y fecha.</p>
    </fieldset>
  );
}
