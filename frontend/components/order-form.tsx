"use client";

import { Plus, Trash2 } from "lucide-react";
import { useState } from "react";
import useSWR from "swr";
import { ApiError, apiFetch, fetcher } from "@/lib/api";
import type { Customer, OrderDetail, OrderInput, OrderListItem, Product } from "@/lib/types";
import { Button } from "./ui";

// One garment line: what the customer wants, in their words; the catalog
// product is optional because most orders are made to measure (ADR 0025 C).
interface ItemRow {
  key: string;
  description: string;
  quantity: string;
  product: string; // catalog code, "" = new product
  unit_price: string; // optional sale price per garment
}

const today = () => new Date().toISOString().slice(0, 10);
const input = "mt-1 w-full rounded-md bg-surface px-3 py-2.5 text-base ring-1 ring-line sm:text-sm";
const newRow = (): ItemRow => ({ key: `i${Date.now()}${Math.random().toString(36).slice(2, 6)}`, description: "", quantity: "", product: "", unit_price: "" });
const BRANDS = ["UNICRACK", "NEXO", "Línea Médica Corpotex"];

const FIELD_LABEL: Record<string, string> = {
  customer: "cliente",
  brand: "marca",
  promised_on: "fecha prometida",
  items: "ítem",
  description: "descripción",
  product: "producto",
  quantity: "cantidad",
  unit_price: "precio unitario",
  notes: "notas",
};

// DRF nests item errors: {"items": {"0": {"unit_price": ["Este campo es requerido."]}}}.
function flattenError(value: unknown, path: string[] = []): string | null {
  if (typeof value === "string") {
    const labels = path.map((p) => (/^\d+$/.test(p) ? `${Number(p) + 1}` : (FIELD_LABEL[p] ?? p)));
    return labels.length ? `${labels.join(" ")}: ${value}` : value;
  }
  if (Array.isArray(value)) return value.length ? flattenError(value[0], path) : null;
  if (value && typeof value === "object") {
    for (const [key, inner] of Object.entries(value as Record<string, unknown>)) {
      const found = flattenError(inner, key === "non_field_errors" || key === "detail" ? path : [...path, key]);
      if (found) return found;
    }
  }
  return null;
}

function firstError(err: unknown): string {
  if (err instanceof ApiError) {
    const found = flattenError(err.body);
    if (found) return found;
  }
  return "No se pudo guardar la orden. Revisa los datos.";
}

// What an existing item says, for the edit form: its description, or the
// legacy product + color + customization joined.
function describe(item: OrderDetail["items"][number]): string {
  if (item.description) return item.description;
  return [item.product?.name, item.color, item.customization].filter(Boolean).join(", ");
}

// Create (POST /api/orders/) or edit (PATCH /api/orders/<id>/, items replace
// the list) a customer order: customer with search, brand, items by
// description with quantity, optional base product and price, promised date
// and notes. The server numbers the order.
export function OrderForm({ initial, onSaved, onCancel }: { initial?: OrderDetail; onSaved: (order: OrderListItem) => void; onCancel: () => void }) {
  const { data: customers } = useSWR<Customer[]>("/api/customers/", fetcher);
  const { data: products, error: productsError } = useSWR<Product[]>("/api/products/", fetcher);
  const catalogDown = !!productsError && !products;
  const [customer, setCustomer] = useState(initial?.customer.name ?? "");
  const [customerOpen, setCustomerOpen] = useState(false);
  const [brand, setBrand] = useState(initial?.brand.name ?? "");
  const [promisedOn, setPromisedOn] = useState(initial?.promised_on ?? "");
  const [notes, setNotes] = useState(initial?.notes ?? "");
  const [items, setItems] = useState<ItemRow[]>(
    initial?.items.length
      ? initial.items.map((item) => ({
          key: `e${item.id}`,
          description: describe(item),
          quantity: String(item.quantity),
          product: item.product?.code ?? "",
          unit_price: item.unit_price != null ? String(item.unit_price) : "",
        }))
      : [newRow()],
  );
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const brands = [...new Map((products ?? []).filter((p) => p.brand).map((p) => [p.brand!.name, p.brand!])).values()];
  for (const name of BRANDS) if (!brands.some((b) => b.name === name)) brands.push({ id: 0, name });
  if (brand && !brands.some((b) => b.name === brand)) brands.push({ id: 0, name: brand });
  const productOptions = (products ?? []).filter((p) => !brand || !p.brand || p.brand.name === brand);
  const query = customer.trim().toLowerCase();
  const matches = (customers ?? []).filter((c) => !query || c.name.toLowerCase().includes(query) || (c.ruc ?? "").includes(query)).slice(0, 6);
  const exact = (customers ?? []).some((c) => c.name.toLowerCase() === query);

  function update(key: string, patch: Partial<ItemRow>) {
    setItems((rows) => rows.map((r) => (r.key === key ? { ...r, ...patch } : r)));
  }

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    const rows = items.filter((r) => r.description.trim() || r.quantity || r.product);
    if (!customer.trim()) return setError("Elige o escribe el cliente.");
    if (!brand) return setError("Elige la marca.");
    if (!promisedOn) return setError("Pon la fecha prometida al cliente.");
    if (!rows.length) return setError("Agrega al menos un ítem.");
    const bad = rows.find((r) => !r.description.trim() || !(Number(r.quantity) > 0) || (r.unit_price !== "" && !(Number(r.unit_price) > 0)));
    if (bad) return setError("Cada ítem necesita una descripción y una cantidad mayor a 0 (el precio, si lo pones, mayor a 0).");
    setBusy(true);
    setError(null);
    const body: OrderInput = {
      customer: customer.trim(),
      brand,
      promised_on: promisedOn,
      notes: notes.trim(),
      items: rows.map((r) => ({
        description: r.description.trim(),
        quantity: Number(r.quantity),
        product: r.product || null,
        unit_price: r.unit_price !== "" ? r.unit_price : null,
      })),
    };
    try {
      const order = initial
        ? await apiFetch<OrderListItem>(`/api/orders/${initial.id}/`, { method: "PATCH", json: body })
        : await apiFetch<OrderListItem>("/api/orders/", { method: "POST", json: { ...body, issued_on: today() } });
      onSaved(order);
    } catch (err) {
      setError(firstError(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={submit} className="space-y-5">
      <div className="grid gap-3 sm:grid-cols-2">
        <label className="relative text-sm">
          Cliente
          <input
            value={customer}
            onChange={(e) => {
              setCustomer(e.target.value);
              setCustomerOpen(true);
            }}
            onFocus={() => setCustomerOpen(true)}
            onBlur={() => setTimeout(() => setCustomerOpen(false), 150)}
            placeholder="Busca por nombre o RUC"
            autoComplete="off"
            className={input}
            aria-autocomplete="list"
            aria-expanded={customerOpen}
          />
          {customerOpen && (matches.length > 0 || (query && !exact)) && (
            <ul className="absolute inset-x-0 top-full z-10 mt-1 max-h-56 overflow-y-auto rounded-md bg-surface py-1 shadow-lg ring-1 ring-line" role="listbox">
              {matches.map((c) => (
                <li key={c.id}>
                  <button
                    type="button"
                    role="option"
                    aria-selected={c.name === customer}
                    onMouseDown={(e) => e.preventDefault()}
                    onClick={() => {
                      setCustomer(c.name);
                      setCustomerOpen(false);
                    }}
                    className="flex w-full items-center justify-between gap-2 px-3 py-2 text-left hover:bg-canvas"
                  >
                    <span>{c.name}</span>
                    {c.ruc && <span className="text-xs text-muted tabular-nums">RUC {c.ruc}</span>}
                  </button>
                </li>
              ))}
              {query && !exact && (
                <li className="px-3 py-2 text-xs text-muted">
                  Se crea el cliente <strong>{customer.trim()}</strong> al guardar.
                </li>
              )}
            </ul>
          )}
        </label>
        <label className="text-sm">
          Marca
          <select value={brand} onChange={(e) => setBrand(e.target.value)} className={input}>
            <option value="">Elige la marca</option>
            {brands.map((b) => (
              <option key={b.name} value={b.name}>
                {b.name}
              </option>
            ))}
          </select>
        </label>
        <label className="text-sm">
          Prometida al cliente
          <input type="date" value={promisedOn} min={today()} onChange={(e) => setPromisedOn(e.target.value)} className={input} />
        </label>
        <label className="text-sm">
          Notas <span className="text-muted">(opcional)</span>
          <input value={notes} onChange={(e) => setNotes(e.target.value)} placeholder="Entrega por partes, logo nuevo…" className={input} />
        </label>
      </div>

      <fieldset>
        <legend className="text-sm font-medium">Ítems</legend>
        <p className="mt-1 text-xs text-muted">
          Describe cada prenda como la pide el cliente: modelo, color, cuello, logo y dónde va, tallas. Si existe en el catálogo, elige el producto base; si no,
          Producción desglosa los componentes después.
        </p>
        {catalogDown && <p className="mt-1 text-xs text-warning">El catálogo de productos no está disponible: los ítems entran como producto nuevo.</p>}
        <ul className="mt-2 space-y-2">
          {items.map((row, i) => (
            <li key={row.key} className="space-y-2 rounded-lg p-3 ring-1 ring-line">
              <label className="block text-xs text-muted">
                Descripción
                <textarea
                  value={row.description}
                  onChange={(e) => update(row.key, { description: e.target.value })}
                  rows={2}
                  placeholder="Buzo deportivo rojo, cuello redondo, logo sublimado al pecho y espalda, tallas S-XL"
                  className={`${input} resize-y`}
                  aria-label={`Descripción del ítem ${i + 1}`}
                />
              </label>
              <div className="grid grid-cols-2 gap-2 sm:grid-cols-[6rem_7rem_minmax(0,1fr)_2rem] sm:items-end">
                <label className="text-xs text-muted">
                  Cantidad
                  <input type="number" inputMode="numeric" min={1} value={row.quantity} onChange={(e) => update(row.key, { quantity: e.target.value })} className={input} aria-label={`Cantidad del ítem ${i + 1}`} />
                </label>
                <label className="text-xs text-muted">
                  Precio unit. <span className="font-normal">(opcional)</span>
                  <input
                    type="number"
                    inputMode="decimal"
                    min={0}
                    step="0.01"
                    value={row.unit_price}
                    onChange={(e) => update(row.key, { unit_price: e.target.value })}
                    placeholder="S/"
                    className={`${input} tabular-nums`}
                    aria-label={`Precio unitario del ítem ${i + 1}`}
                  />
                </label>
                <label className="col-span-2 text-xs text-muted sm:col-span-1">
                  Producto base <span className="font-normal">(opcional)</span>
                  <select
                    value={row.product}
                    onChange={(e) => update(row.key, { product: e.target.value })}
                    disabled={catalogDown}
                    className={input}
                    aria-label={`Producto base del ítem ${i + 1}`}
                  >
                    <option value="">{catalogDown ? "Catálogo no disponible" : "Nuevo producto"}</option>
                    {productOptions.map((p) => (
                      <option key={p.id} value={p.code}>
                        {p.name} · {p.code}
                      </option>
                    ))}
                    {row.product && !productOptions.some((p) => p.code === row.product) && <option value={row.product}>{row.product}</option>}
                  </select>
                </label>
                <button
                  type="button"
                  onClick={() => setItems((rows) => (rows.length > 1 ? rows.filter((r) => r.key !== row.key) : [newRow()]))}
                  className="col-start-2 justify-self-end rounded-md p-2 text-muted hover:bg-canvas hover:text-danger sm:col-start-auto"
                  aria-label={`Quitar ítem ${i + 1}`}
                >
                  <Trash2 size={16} />
                </button>
              </div>
            </li>
          ))}
        </ul>
        <Button type="button" className="mt-2" onClick={() => setItems((rows) => [...rows, newRow()])}>
          <Plus size={16} /> Agregar ítem
        </Button>
      </fieldset>

      {error && (
        <p className="text-sm text-danger" role="alert">
          {error}
        </p>
      )}
      <div className="flex flex-wrap gap-2">
        <Button kind="primary" type="submit" busy={busy}>
          {busy ? "Guardando…" : initial ? "Guardar cambios" : "Crear orden"}
        </Button>
        <Button type="button" onClick={onCancel} disabled={busy}>
          Cancelar
        </Button>
      </div>
      {initial && initial.status !== "registered" && (
        <p className="text-xs text-muted">La orden ya está desglosada: al guardar se vuelve a desglosar; los insumos ya pedidos no se tocan.</p>
      )}
    </form>
  );
}
