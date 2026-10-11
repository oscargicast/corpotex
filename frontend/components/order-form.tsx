"use client";

import { Plus, Trash2 } from "lucide-react";
import { useState } from "react";
import useSWR from "swr";
import { ApiError, apiFetch, fetcher } from "@/lib/api";
import { CUSTOMIZATION, type Customer, type OrderDetail, type OrderInput, type OrderListItem, type Product } from "@/lib/types";
import { Button } from "./ui";

interface ItemRow {
  key: string;
  product: string; // product code
  quantity: string;
  color: string;
  customization: string;
}

const today = () => new Date().toISOString().slice(0, 10);
const input = "mt-1 w-full rounded-md bg-surface px-3 py-2.5 text-base ring-1 ring-line sm:text-sm";
const newRow = (): ItemRow => ({ key: `i${Date.now()}${Math.random().toString(36).slice(2, 6)}`, product: "", quantity: "", color: "", customization: "" });

function firstError(err: unknown): string {
  if (err instanceof ApiError) {
    const body = err.body as Record<string, unknown> | null;
    if (body) {
      if (typeof body.detail === "string") return body.detail;
      for (const [field, value] of Object.entries(body)) {
        const text = Array.isArray(value) ? value[0] : value;
        if (typeof text === "string") return field === "non_field_errors" ? text : `${field}: ${text}`;
      }
    }
  }
  return "No se pudo guardar la orden. Revisa los datos.";
}

// Create (POST /api/orders/) or edit (PATCH /api/orders/<id>/, items replace
// the list) a customer order: customer with search, brand, items by product
// and quantity, promised date and notes (ADR 0025 B).
export function OrderForm({ initial, onSaved, onCancel }: { initial?: OrderDetail; onSaved: (order: OrderListItem) => void; onCancel: () => void }) {
  const { data: customers } = useSWR<Customer[]>("/api/customers/", fetcher);
  const { data: products, error: productsError } = useSWR<Product[]>("/api/products/", fetcher);
  // Without the catalog (endpoint missing or down) the form still works by code.
  const manual = !!productsError && !products;
  const [customer, setCustomer] = useState(initial?.customer.name ?? "");
  const [customerOpen, setCustomerOpen] = useState(false);
  const [brand, setBrand] = useState(initial?.brand.name ?? "");
  const [promisedOn, setPromisedOn] = useState(initial?.promised_on ?? "");
  const [notes, setNotes] = useState(initial?.notes ?? "");
  const [items, setItems] = useState<ItemRow[]>(
    initial?.items.length
      ? initial.items.map((item) => ({
          key: `e${item.id}`,
          product: item.product.code,
          quantity: String(item.quantity),
          color: item.color ?? "",
          customization: item.customization ?? "",
        }))
      : [newRow()],
  );
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const brands = [...new Map((products ?? []).filter((p) => p.brand).map((p) => [p.brand!.name, p.brand!])).values()];
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
    const rows = items.filter((r) => r.product || r.quantity);
    if (!customer.trim()) return setError("Elige o escribe el cliente.");
    if (!brand) return setError("Elige la marca.");
    if (!promisedOn) return setError("Pon la fecha prometida al cliente.");
    if (!rows.length) return setError("Agrega al menos un ítem.");
    const bad = rows.find((r) => !r.product || !(Number(r.quantity) > 0));
    if (bad) return setError("Cada ítem necesita un producto y una cantidad mayor a 0.");
    setBusy(true);
    setError(null);
    const body: OrderInput = {
      customer: customer.trim(),
      brand,
      promised_on: promisedOn,
      notes: notes.trim(),
      items: rows.map((r) => ({ product: r.product, quantity: Number(r.quantity), color: r.color.trim(), customization: r.customization })),
    };
    try {
      const order = initial
        ? await apiFetch<OrderListItem>(`/api/orders/${initial.id}/`, { method: "PATCH", json: body })
        : await apiFetch<OrderListItem>("/api/orders/", {
            method: "POST",
            // The sales system numbers its orders; until it does, one code per form.
            json: { ...body, code: `CP-${new Date().getFullYear()}-${String(Date.now()).slice(-5)}`, issued_on: today() },
          });
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
          {manual ? (
            <input value={brand} onChange={(e) => setBrand(e.target.value)} list="order-brands" placeholder="UNICRACK, NEXO…" className={input} />
          ) : (
            <select value={brand} onChange={(e) => setBrand(e.target.value)} className={input}>
              <option value="">{products ? "Elige la marca" : "Cargando…"}</option>
              {brands.map((b) => (
                <option key={b.name} value={b.name}>
                  {b.name}
                </option>
              ))}
            </select>
          )}
          <datalist id="order-brands">
            {["UNICRACK", "NEXO", "Línea Médica Corpotex"].map((b) => (
              <option key={b} value={b} />
            ))}
          </datalist>
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
        {manual && <p className="mt-1 text-xs text-warning">El catálogo de productos no está disponible: escribe el código del producto tal como figura en la ficha.</p>}
        <ul className="mt-2 space-y-2">
          {items.map((row, i) => {
            const chosen = (products ?? []).find((p) => p.code === row.product);
            return (
              <li key={row.key} className="grid grid-cols-[1fr_auto] gap-2 rounded-lg p-3 ring-1 ring-line sm:grid-cols-[minmax(0,2fr)_6rem_minmax(0,1fr)_minmax(0,1fr)_2rem] sm:items-end">
                <label className="text-xs text-muted sm:col-auto">
                  Producto
                  {manual ? (
                    <input
                      value={row.product}
                      onChange={(e) => update(row.key, { product: e.target.value.trim().toUpperCase() })}
                      placeholder="Código, p. ej. UNI-POL-01"
                      className={`${input} font-mono`}
                      aria-label={`Código del producto del ítem ${i + 1}`}
                    />
                  ) : (
                    <select value={row.product} onChange={(e) => update(row.key, { product: e.target.value })} className={input} aria-label={`Producto del ítem ${i + 1}`}>
                      <option value="">{products ? "Elige el producto" : "Cargando…"}</option>
                      {productOptions.map((p) => (
                        <option key={p.id} value={p.code}>
                          {p.name} · {p.code}
                        </option>
                      ))}
                      {chosen === undefined && row.product && <option value={row.product}>{row.product}</option>}
                    </select>
                  )}
                </label>
                <label className="text-xs text-muted">
                  Cantidad
                  <input type="number" inputMode="numeric" min={1} value={row.quantity} onChange={(e) => update(row.key, { quantity: e.target.value })} className={input} aria-label={`Cantidad del ítem ${i + 1}`} />
                </label>
                <label className="text-xs text-muted">
                  Color
                  <input value={row.color} onChange={(e) => update(row.key, { color: e.target.value })} placeholder="azul marino" className={input} />
                </label>
                <label className="text-xs text-muted">
                  Personalización
                  <select value={row.customization} onChange={(e) => update(row.key, { customization: e.target.value })} className={input}>
                    <option value="">Ninguna</option>
                    {Object.entries(CUSTOMIZATION).map(([value, label]) => (
                      <option key={value} value={value}>
                        {label}
                      </option>
                    ))}
                  </select>
                </label>
                <button
                  type="button"
                  onClick={() => setItems((rows) => (rows.length > 1 ? rows.filter((r) => r.key !== row.key) : [newRow()]))}
                  className="justify-self-end rounded-md p-2 text-muted hover:bg-canvas hover:text-danger"
                  aria-label={`Quitar ítem ${i + 1}`}
                >
                  <Trash2 size={16} />
                </button>
              </li>
            );
          })}
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
