"use client";

import { CalendarClock, CheckCircle2, Plus, RotateCcw, Search, Sparkles, Trash2, TriangleAlert, X } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import useSWR from "swr";
import { ApiError, apiFetch, fetcher } from "@/lib/api";
import { num } from "@/lib/format";
import { type ClassificationMaterial, type Customer, type DraftClassification, type DraftProposal, MATERIAL_UNIT, type OrderDetail, type Product } from "@/lib/types";
import { Button, Card, Pill, SectionTitle } from "./ui";

// Orden mágica (ADR 0028): each item is one line as the customer says it. When
// the user stops typing (600 ms) or leaves the field, the line is recognized
// against the catalog and inventory, and the order is saved already broken down.

const DRAFT_URL = "/api/orders/classify-draft/";
const DEBOUNCE_MS = 600;
const MIN_CHARS = 12; // the API leaves shorter lines "pending"
const PRODUCTION_DAYS = 7; // own production (Corpotex interview)
const BRANDS = ["UNICRACK", "NEXO", "Línea Médica Corpotex"];
const input = "mt-1 w-full rounded-md bg-surface px-3 py-2.5 text-base ring-1 ring-line sm:text-sm";

type LineState = "idle" | "recognizing" | "done" | "pending" | "error";

interface Line {
  key: string;
  text: string;
  quantity: string; // typed by hand; otherwise it comes from the start of the line
  quantityTouched: boolean;
  state: LineState;
  proposal: DraftProposal | null;
  ai: DraftProposal | null; // the model's proposal, to undo "Cambiar producto"
  signature: string; // brand and description last sent
}

const newLine = (): Line => ({
  key: `k${Date.now().toString(36)}${Math.random().toString(36).slice(2, 6)}`,
  text: "",
  quantity: "",
  quantityTouched: false,
  state: "idle",
  proposal: null,
  ai: null,
  signature: "",
});

const today = () => new Date().toISOString().slice(0, 10);
const fmt = (n: number) => n.toLocaleString("es-PE", { maximumFractionDigits: 2 });
const SHORT_UNIT: Record<string, string> = { unit: "u.", units: "u.", kg: "kg", m: "m" };
const unitLabel = (unit: string) => SHORT_UNIT[unit] ?? MATERIAL_UNIT[unit] ?? unit;
const plural = (n: number, one: string, many: string) => (n === 1 ? one : many);

// "300 polos deportivos…", "1 200 x polos…", "300 unidades de polos…" → 300 and the rest.
export function splitQuantity(text: string): { quantity: number | null; description: string } {
  const match = /^\s*(\d{1,3}(?:[.\s]\d{3})+|\d+)\s*(?:x|×|unidades|unid\.?|und\.?|uds?\.?|piezas|pzas?\.?)?\s*(?:de\s+)?(\p{L}.*)$/isu.exec(text);
  if (!match) return { quantity: null, description: text.trim() };
  const quantity = Number(match[1].replace(/[.\s]/g, ""));
  return quantity > 0 ? { quantity, description: match[2].trim() } : { quantity: null, description: text.trim() };
}

const signatureOf = (brand: string, description: string) => `${brand}|${description}`;

function draftOf(line: Line): { description: string; quantity: number } {
  const parsed = splitQuantity(line.text);
  const quantity = line.quantityTouched ? Number(line.quantity) : (parsed.quantity ?? Number(line.quantity));
  return { description: parsed.description, quantity: Number.isFinite(quantity) ? quantity : 0 };
}

const materialKey = (m: ClassificationMaterial) => m.sku ?? m.new?.sku ?? m.new?.name ?? m.name ?? "?";
const materialName = (m: ClassificationMaterial) => m.name ?? m.new?.name ?? m.sku ?? "Insumo";

function firstError(err: unknown): string {
  if (err instanceof ApiError) {
    const body = err.body as Record<string, unknown> | null;
    const detail = body && typeof body.detail === "string" ? body.detail : null;
    if (detail) return detail;
    const first = body && Object.entries(body)[0];
    if (first) return `${first[0]}: ${Array.isArray(first[1]) ? String(first[1][0]) : JSON.stringify(first[1])}`;
  }
  return "No se pudo guardar la orden. Revisa los datos.";
}

export function MagicOrderForm({ onSaved, onCancel }: { onSaved: (order: OrderDetail) => void; onCancel: () => void }) {
  const { data: customers } = useSWR<Customer[]>("/api/customers/", fetcher);
  const { data: products } = useSWR<Product[]>("/api/products/", fetcher);
  const [customer, setCustomer] = useState("");
  const [customerOpen, setCustomerOpen] = useState(false);
  const [brand, setBrand] = useState("");
  const [promisedOn, setPromisedOn] = useState("");
  const [notes, setNotes] = useState("");
  const [lines, setLines] = useState<Line[]>(() => [newLine()]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [created, setCreated] = useState<string | null>(null);
  const [focusKey, setFocusKey] = useState<string | null>(null);

  // The latest values for the timers and requests.
  const linesRef = useRef(lines);
  const brandRef = useRef(brand);
  const customerRef = useRef(customer);
  useEffect(() => {
    linesRef.current = lines;
    brandRef.current = brand;
    customerRef.current = customer;
  });
  const timers = useRef(new Map<string, ReturnType<typeof setTimeout>>());
  const controllers = useRef(new Map<string, AbortController>());
  const fields = useRef(new Map<string, HTMLTextAreaElement>());

  useEffect(() => {
    const pendingTimers = timers.current;
    const pendingRequests = controllers.current;
    return () => {
      pendingTimers.forEach(clearTimeout);
      pendingRequests.forEach((c) => c.abort());
    };
  }, []);

  // Choosing (or changing) the brand recognizes what is already written.
  useEffect(() => {
    if (!brand) return;
    for (const line of linesRef.current) if (line.text.trim()) schedule(line.key, 0);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [brand]);

  useEffect(() => {
    if (!focusKey) return;
    fields.current.get(focusKey)?.focus();
    setFocusKey(null);
  }, [focusKey]);

  function patch(key: string, change: Partial<Line> | ((line: Line) => Partial<Line>)) {
    setLines((all) => all.map((l) => (l.key === key ? { ...l, ...(typeof change === "function" ? change(l) : change) } : l)));
  }

  function schedule(key: string, delay = DEBOUNCE_MS) {
    clearTimeout(timers.current.get(key));
    timers.current.set(
      key,
      setTimeout(() => recognize(key), delay),
    );
  }

  async function recognize(key: string, force = false) {
    const line = linesRef.current.find((l) => l.key === key);
    if (!line) return;
    const { description, quantity } = draftOf(line);
    const brand = brandRef.current;
    // The API needs the brand (an unknown one is a 400) and does nothing with short lines.
    if (!brand || description.length < MIN_CHARS || !(quantity > 0)) return;
    const signature = signatureOf(brand, description);
    if (!force && signature === line.signature && (line.state === "done" || line.state === "recognizing")) return;
    controllers.current.get(key)?.abort();
    const controller = new AbortController();
    controllers.current.set(key, controller);
    patch(key, { state: "recognizing", signature });
    try {
      const res = await apiFetch<DraftClassification>(DRAFT_URL, {
        method: "POST",
        json: { brand, ...(customerRef.current.trim() && { customer: customerRef.current.trim() }), items: [{ key, description, quantity }] },
        signal: controller.signal,
      });
      if (controller.signal.aborted) return;
      const item = res?.items?.find((i) => i.key === key) ?? res?.items?.[0];
      const status = item?.status as string | undefined;
      if (!item || !item.product || (status !== "classified" && status !== "done")) {
        patch(key, { state: status === "error" ? "error" : "pending", proposal: null });
        return;
      }
      // Catalog recipes come with four decimals ("0.2500"): show them as typed.
      const proposal: DraftProposal = {
        product: item.product,
        confidence: item.confidence ?? null,
        lead_time_days: item.lead_time_days,
        materials: (item.materials ?? []).map((m) => ({ ...m, qty_per_unit: String(num(m.qty_per_unit) ?? m.qty_per_unit) })),
      };
      patch(key, { state: "done", proposal, ai: proposal });
    } catch (err) {
      if (controller.signal.aborted || (err as Error)?.name === "AbortError") return;
      patch(key, { state: "error" });
    } finally {
      if (controllers.current.get(key) === controller) controllers.current.delete(key);
    }
  }

  function addLine(after?: string) {
    const line = newLine();
    setLines((all) => {
      const at = after ? all.findIndex((l) => l.key === after) + 1 : all.length;
      return [...all.slice(0, at), line, ...all.slice(at)];
    });
    setFocusKey(line.key);
  }

  function removeLine(key: string) {
    clearTimeout(timers.current.get(key));
    controllers.current.get(key)?.abort();
    setLines((all) => (all.length > 1 ? all.filter((l) => l.key !== key) : [newLine()]));
  }

  // ---- Summary ----
  const drafts = lines.map((line) => ({ line, ...draftOf(line) }));
  const counted = drafts.filter((d) => d.description && d.quantity > 0);
  const garments = counted.reduce((sum, d) => sum + d.quantity, 0);
  // Recognized for the text as it is now (an edited line waits for its new result).
  const recognized = counted.filter((d) => d.line.state === "done" && d.line.proposal && signatureOf(brand, d.description) === d.line.signature);
  const recognizing = lines.filter((l) => l.state === "recognizing").length;
  const needs = new Map<string, { name: string; unit: string; total: number; isNew: boolean }>();
  for (const { line, quantity } of recognized) {
    for (const m of line.proposal!.materials) {
      const key = materialKey(m);
      const entry = needs.get(key) ?? { name: materialName(m), unit: m.unit, total: 0, isNew: !m.sku };
      entry.total += (num(m.qty_per_unit) ?? 0) * quantity;
      needs.set(key, entry);
    }
  }
  const needList = [...needs.values()].sort((a, b) => Number(b.isNew) - Number(a.isNew) || b.total - a.total);
  const newMaterials = needList.filter((n) => n.isNew).length;
  const newProducts = recognized.filter((d) => !d.line.proposal!.product.existing_id).length;
  // A catalog product picked by hand: its recipe is added by the server.
  const pickedRecipes = recognized.filter((d) => d.line.proposal!.product.existing_id && !d.line.proposal!.materials.length).map((d) => d.line.proposal!.product.name ?? d.line.proposal!.product.code);
  const leads = recognized.map((d) => d.line.proposal!.lead_time_days).filter((v): v is number => typeof v === "number");
  const lead = leads.length ? Math.max(...leads) : null;
  // No buffer_days here: the backend's internal due date already holds it back,
  // so adding it again would count it twice and contradict the order's detail.
  const neededDays = lead ?? PRODUCTION_DAYS;
  const estimated = lead === null;
  const promisedDays = promisedOn ? Math.round((new Date(`${promisedOn}T12:00:00`).getTime() - new Date(`${today()}T12:00:00`).getTime()) / 86_400_000) : null;
  const atRisk = promisedDays !== null && neededDays > promisedDays;

  // ---- Save ----
  async function submit(e: React.FormEvent) {
    e.preventDefault();
    const rows = drafts.filter((d) => d.line.text.trim());
    if (!customer.trim()) return setError("Elige o escribe el cliente.");
    if (!brand) return setError("Elige la marca.");
    if (!promisedOn) return setError("Pon la fecha prometida al cliente.");
    if (!rows.length) return setError("Escribe al menos un ítem.");
    const bad = rows.find((d) => !d.description || !(d.quantity > 0) || !Number.isInteger(d.quantity));
    if (bad) {
      setFocusKey(bad.line.key);
      return setError("Cada ítem necesita la prenda y una cantidad entera mayor a 0 (al inicio de la línea o en Cantidad).");
    }
    setBusy(true);
    setError(null);
    const classified = rows.filter((d) => recognized.includes(d));
    const classification = classified.map(({ line }) => {
      const product = line.proposal!.product;
      return {
        key: line.key,
        // A catalog product brings its own recipe: the server ignores materials.
        product: product.existing_id ? { existing_id: product.existing_id } : { new: { ...(product.new ?? { code: "", name: "" }), brand } },
        materials: product.existing_id ? [] : line.proposal!.materials.map((m) => ({ ...(m.sku ? { sku: m.sku } : { new: m.new }), qty_per_unit: m.qty_per_unit, unit: m.unit })),
      };
    });
    try {
      const order = await apiFetch<OrderDetail>("/api/orders/", {
        method: "POST",
        json: {
          customer: customer.trim(),
          brand,
          promised_on: promisedOn,
          issued_on: today(),
          notes: notes.trim(),
          items: rows.map((d) => ({ key: d.line.key, description: d.description, quantity: d.quantity })),
          ...(classification.length && { classification: { items: classification } }),
        },
      });
      // Materials only: the workshop requirements (sewing) are not "insumos".
      const toOrder = (order.requirements ?? []).filter((r) => r.kind === "material" && (num(r.qty_to_order) ?? 0) > 0).length || needList.length;
      const left = rows.length - classified.length;
      const warnings = (order as { warnings?: string[] }).warnings ?? [];
      const warned = warnings.length ? ` Ojo: ${warnings[0]}${warnings.length > 1 ? ` (y ${warnings.length - 1} más)` : ""}.` : "";
      setCreated(
        (order as { needs_classification?: boolean }).needs_classification || left > 0
          ? `Orden ${order.code} creada. ${left > 0 ? `${left} ${plural(left, "ítem queda", "ítems quedan")} por clasificar` : "Queda por desglosar"}: Producción lo desglosa desde el detalle.`
          : `Orden ${order.code} creada y desglosada: ${toOrder} ${plural(toOrder, "insumo", "insumos")} por pedir.${warned}`,
      );
      setTimeout(() => onSaved(order), 1600);
    } catch (err) {
      setError(firstError(err));
      setBusy(false);
    }
  }

  const query = customer.trim().toLowerCase();
  const matches = (customers ?? []).filter((c) => !query || c.name.toLowerCase().includes(query) || (c.ruc ?? "").includes(query)).slice(0, 6);
  const exact = (customers ?? []).some((c) => c.name.toLowerCase() === query);
  const brands = [...new Set([...BRANDS, ...(products ?? []).map((p) => p.brand?.name).filter((b): b is string => !!b)])];

  return (
    <form onSubmit={submit} className="grid items-start gap-4 lg:grid-cols-[minmax(0,1fr)_21rem]">
      <div className="min-w-0 space-y-4">
        <Card>
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
                        className="flex min-h-11 w-full items-center justify-between gap-2 px-3 py-2 text-left hover:bg-canvas"
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
                  <option key={b} value={b}>
                    {b}
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
        </Card>

        <section aria-labelledby="items-title">
          <div className="flex flex-wrap items-end justify-between gap-2">
            <div>
              <h2 id="items-title" className="flex items-center gap-2 font-semibold">
                <Sparkles size={16} className="text-accent" aria-hidden /> Ítems
              </h2>
              <p className="mt-0.5 text-sm text-muted">Escribe cada prenda como la pide el cliente. Se reconoce sola contra el catálogo y el inventario.</p>
            </div>
          </div>
          <ol className="mt-3 space-y-3">
            {lines.map((line, i) => (
              <ItemCard
                key={line.key}
                index={i}
                line={line}
                needsBrand={!brand}
                products={products ?? []}
                fieldRef={(el) => {
                  if (el) fields.current.set(line.key, el);
                  else fields.current.delete(line.key);
                }}
                onText={(text) => {
                  patch(line.key, { text });
                  schedule(line.key);
                }}
                onQuantity={(quantity) => {
                  patch(line.key, { quantity, quantityTouched: quantity !== "" });
                  schedule(line.key);
                }}
                onBlur={() => schedule(line.key, 0)}
                onEnter={() => {
                  schedule(line.key, 0);
                  if (line.text.trim() && i === lines.length - 1) addLine(line.key);
                }}
                onRetry={() => recognize(line.key, true)}
                onRemove={() => removeLine(line.key)}
                onProposal={(proposal) => patch(line.key, { proposal })}
              />
            ))}
          </ol>
          <Button type="button" className="mt-3 min-h-11 sm:min-h-0" onClick={() => addLine()}>
            <Plus size={16} aria-hidden /> Agregar ítem
          </Button>
        </section>
      </div>

      <aside aria-label="Resumen de la orden" className="space-y-3 lg:sticky lg:top-4">
        <Card>
          <SectionTitle>Resumen</SectionTitle>
          <div aria-live="polite" className="space-y-4 text-sm">
            <dl className="grid grid-cols-2 gap-2">
              <div className="rounded-lg bg-canvas p-3">
                <dt className="text-xs text-muted">Prendas</dt>
                <dd className="text-2xl font-bold tabular-nums">{fmt(garments)}</dd>
              </div>
              <div className="rounded-lg bg-canvas p-3">
                <dt className="text-xs text-muted">Reconocidos</dt>
                <dd className="text-2xl font-bold tabular-nums">
                  {recognized.length}
                  <span className="text-base font-medium text-muted">/{counted.length}</span>
                </dd>
              </div>
            </dl>
            {recognizing > 0 && (
              <p className="flex items-center gap-2 text-accent">
                <Sparkles size={14} aria-hidden /> Reconociendo {recognizing} {plural(recognizing, "ítem", "ítems")}…
              </p>
            )}

            <div>
              <p className="font-medium">Insumos que necesita</p>
              {needList.length ? (
                <>
                  <ul className="mt-1.5 space-y-1">
                    {needList.slice(0, 7).map((n) => (
                      <li key={n.name} className="flex items-baseline justify-between gap-3">
                        <span className="min-w-0">
                          {n.name}
                          {n.isNew && (
                            <span className="ml-1.5 align-middle">
                              <Pill tone="warning">Nuevo</Pill>
                            </span>
                          )}
                        </span>
                        <span className="shrink-0 tabular-nums text-muted">
                          {fmt(n.total)} {unitLabel(n.unit)}
                        </span>
                      </li>
                    ))}
                  </ul>
                  {needList.length > 7 && <p className="mt-1 text-xs text-muted">y {needList.length - 7} más</p>}
                  {pickedRecipes.length > 0 && <p className="mt-1 text-xs text-muted">Más la receta del catálogo de {pickedRecipes.join(" y ")}.</p>}
                  {(newMaterials > 0 || newProducts > 0) && (
                    <p className="mt-2 text-xs text-warning">
                      {[
                        newMaterials > 0 && `${newMaterials} ${plural(newMaterials, "insumo nuevo", "insumos nuevos")}`,
                        newProducts > 0 && `${newProducts} ${plural(newProducts, "producto nuevo", "productos nuevos")}`,
                      ]
                        .filter(Boolean)
                        .join(" · ")}
                      : se crean al guardar.
                    </p>
                  )}
                </>
              ) : (
                <p className="mt-1 text-muted">Aparecen al reconocer los ítems.</p>
              )}
            </div>

            <div className={`flex items-start gap-2 rounded-lg px-3 py-2.5 ${promisedDays === null ? "bg-canvas" : atRisk ? "bg-danger-soft text-danger" : "bg-success-soft text-success"}`}>
              {atRisk ? <TriangleAlert size={16} className="mt-0.5 shrink-0" aria-hidden /> : <CalendarClock size={16} className="mt-0.5 shrink-0" aria-hidden />}
              <p>
                Necesita {estimated ? "unos " : ""}
                {neededDays} días
                {promisedDays === null ? (
                  <span className="text-muted">. Pon la fecha prometida para compararla.</span>
                ) : (
                  <>
                    ; prometida en {promisedDays} → <strong>{atRisk ? "en riesgo" : "a tiempo"}</strong>
                    {estimated ? " (estimado)" : ""}
                  </>
                )}
              </p>
            </div>
          </div>

          {created ? (
            <p className="mt-4 flex items-start gap-2 rounded-lg bg-success-soft px-3 py-2.5 text-sm text-success" role="status">
              <CheckCircle2 size={16} className="mt-0.5 shrink-0" aria-hidden /> {created}
            </p>
          ) : (
            <div className="mt-4 space-y-2">
              {error && (
                <p className="text-sm text-danger" role="alert">
                  {error}
                </p>
              )}
              <Button kind="primary" type="submit" busy={busy} className="h-12 w-full text-base">
                {busy ? "Creando…" : "Crear orden"}
              </Button>
              <Button type="button" onClick={onCancel} disabled={busy} className="min-h-11 w-full">
                Cancelar
              </Button>
              {recognizing > 0 && <p className="text-xs text-muted">Puedes guardar ya: lo que no termine de reconocerse lo desglosa Producción después.</p>}
            </div>
          )}
        </Card>
      </aside>
    </form>
  );
}

function ItemCard({
  index,
  line,
  needsBrand,
  products,
  fieldRef,
  onText,
  onQuantity,
  onBlur,
  onEnter,
  onRetry,
  onRemove,
  onProposal,
}: {
  index: number;
  line: Line;
  needsBrand: boolean;
  products: Product[];
  fieldRef: (el: HTMLTextAreaElement | null) => void;
  onText: (text: string) => void;
  onQuantity: (quantity: string) => void;
  onBlur: () => void;
  onEnter: () => void;
  onRetry: () => void;
  onRemove: () => void;
  onProposal: (proposal: DraftProposal) => void;
}) {
  const parsed = splitQuantity(line.text);
  const quantityValue = line.quantityTouched ? line.quantity : parsed.quantity !== null ? String(parsed.quantity) : line.quantity;
  const fromLine = !line.quantityTouched && parsed.quantity !== null;
  const n = index + 1;
  const draft = draftOf(line);
  const waitingBrand = needsBrand && draft.description.length >= MIN_CHARS && draft.quantity > 0;
  const open = line.state !== "idle" || waitingBrand;

  return (
    <li className="rounded-xl bg-surface p-3 ring-1 ring-line sm:p-4">
      <div className="flex items-start gap-2 sm:gap-3">
        <span className="mt-3 flex size-6 shrink-0 items-center justify-center rounded-full bg-canvas text-xs font-semibold tabular-nums text-muted" aria-hidden>
          {n}
        </span>
        <div className="grid min-w-0 flex-1 gap-2 sm:grid-cols-[minmax(0,1fr)_7rem]">
          <label className="text-xs text-muted">
            Prenda
            <textarea
              ref={fieldRef}
              value={line.text}
              rows={2}
              onChange={(e) => onText(e.target.value)}
              onBlur={onBlur}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();
                  onEnter();
                }
              }}
              placeholder="300 polos deportivos azul marino con escudo sublimado, tallas 6 a 14"
              aria-label={`Ítem ${n}: la prenda como la pide el cliente`}
              className={`${input} resize-none text-ink`}
            />
          </label>
          <label className="max-w-36 text-xs text-muted sm:max-w-none">
            Cantidad
            <input
              type="number"
              inputMode="numeric"
              min={1}
              value={quantityValue}
              onChange={(e) => onQuantity(e.target.value)}
              onBlur={onBlur}
              aria-label={`Cantidad del ítem ${n}`}
              className={`${input} tabular-nums text-ink`}
            />
            {fromLine && <span className="mt-0.5 block text-[11px]">de la línea</span>}
          </label>
        </div>
        <button
          type="button"
          onClick={onRemove}
          aria-label={`Quitar ítem ${n}`}
          className="mt-5 flex size-11 shrink-0 items-center justify-center rounded-md text-muted hover:bg-canvas hover:text-danger sm:size-9"
        >
          <Trash2 size={16} aria-hidden />
        </button>
      </div>

      <div className="magic-reveal" data-open={open}>
        <div className="sm:pl-9">
          {line.state === "recognizing" && (
            <div className="mt-3 rounded-lg p-3 magic-shimmer" role="status">
              <p className="flex items-center gap-2 text-sm font-medium text-accent">
                <Sparkles size={15} aria-hidden /> Reconociendo…
              </p>
              <div className="mt-2 space-y-1.5" aria-hidden>
                <div className="h-2.5 w-2/3 rounded-full bg-surface/70" />
                <div className="h-2.5 w-1/2 rounded-full bg-surface/70" />
              </div>
            </div>
          )}
          {waitingBrand && line.state === "idle" && <p className="mt-3 text-sm text-muted">Elige la marca arriba para reconocerla.</p>}
          {line.state === "pending" && <p className="mt-3 text-sm text-muted">Agrega la prenda y la cantidad para reconocerla.</p>}
          {line.state === "error" && (
            <p className="mt-3 flex flex-wrap items-center gap-2 text-sm text-warning" role="alert">
              <TriangleAlert size={15} aria-hidden /> No se pudo reconocer. Se guarda igual y Producción la desglosa después.
              <button type="button" onClick={onRetry} className="inline-flex min-h-11 items-center gap-1 font-medium text-accent underline sm:min-h-0">
                <RotateCcw size={14} aria-hidden /> Reintentar
              </button>
            </p>
          )}
          {line.state === "done" && line.proposal && (
            <Proposal line={line} proposal={line.proposal} products={products} quantity={draftOf(line).quantity} onChange={onProposal} />
          )}
        </div>
      </div>
    </li>
  );
}

function Proposal({
  line,
  proposal,
  products,
  quantity,
  onChange,
}: {
  line: Line;
  proposal: DraftProposal;
  products: Product[];
  quantity: number;
  onChange: (proposal: DraftProposal) => void;
}) {
  const [picking, setPicking] = useState(false);
  const product = proposal.product;
  const existing = product.existing_id ? products.find((p) => p.id === product.existing_id) : undefined;
  const catalog = !!product.existing_id;
  const name = product.name ?? existing?.name ?? product.code ?? "";
  const confidence = num(proposal.confidence);

  function setMaterial(index: number, change: Partial<ClassificationMaterial> | null) {
    const materials = change === null ? proposal.materials.filter((_, j) => j !== index) : proposal.materials.map((m, j) => (j === index ? { ...m, ...change } : m));
    onChange({ ...proposal, materials });
  }

  function pick(next: DraftProposal["product"]) {
    const ai = line.ai;
    const backToAi = ai && (next.existing_id ? next.existing_id === ai.product.existing_id : !ai.product.existing_id);
    // Another catalog product: the server adds its recipe, which the form does not know.
    onChange(backToAi ? ai : { ...proposal, product: next, confidence: null, materials: [] });
    setPicking(false);
  }

  return (
    <div className="mt-3 border-t border-line pt-3">
      <div className="flex flex-wrap items-center gap-2">
        {catalog ? (
          <span className="magic-in inline-flex items-center gap-1.5 rounded-full bg-success-soft px-3 py-1 text-sm font-medium text-success">
            <CheckCircle2 size={14} aria-hidden />
            {name}
            {confidence !== null ? ` · ${Math.round(confidence * 100)} %` : " · elegido"}
          </span>
        ) : (
          <span className="magic-in inline-flex items-center gap-1.5 rounded-full bg-warning-soft px-3 py-1 text-sm font-medium text-warning">
            <Sparkles size={14} aria-hidden />
            Producto nuevo · {product.new?.name || "sin nombre"}
          </span>
        )}
        <button
          type="button"
          onClick={() => setPicking((v) => !v)}
          aria-expanded={picking}
          className="inline-flex min-h-11 items-center gap-1 rounded-md px-2 text-sm font-medium text-accent hover:bg-canvas sm:min-h-8"
        >
          <Search size={14} aria-hidden /> Cambiar producto
        </button>
      </div>

      {picking && <ProductPicker products={products} ai={line.ai} onPick={pick} onClose={() => setPicking(false)} />}

      <p className="mt-3 text-xs font-medium text-muted">{catalog ? "Receta del catálogo, por prenda" : "Insumos por prenda"}</p>
      {catalog && !proposal.materials.length ? (
        <p className="mt-1 text-sm text-muted">Se usa la receta de {name} tal como está en el catálogo.</p>
      ) : proposal.materials.length ? (
        <ul className="mt-1 divide-y divide-line/70 rounded-lg bg-canvas/70">
          {proposal.materials.map((m, j) => {
            const isNew = !m.sku;
            const per = num(m.qty_per_unit) ?? 0;
            return (
              <li key={`${materialKey(m)}-${j}`} className="magic-in flex items-center gap-2 px-2.5 py-1.5 text-sm" style={{ animationDelay: `${j * 30}ms` }}>
                <span className="min-w-0 flex-1">
                  {materialName(m)}
                  {isNew && (
                    <span className="ml-1.5 align-middle">
                      <Pill tone="warning">Nuevo</Pill>
                    </span>
                  )}
                  {quantity > 0 && per > 0 && (
                    <span className="block text-xs text-muted tabular-nums">
                      {fmt(per * quantity)} {unitLabel(m.unit)} en total
                    </span>
                  )}
                </span>
                {catalog ? (
                  // The catalog recipe is used as is: nothing to edit here.
                  <span className="tabular-nums text-muted">
                    {fmt(per)} {unitLabel(m.unit)}
                  </span>
                ) : (
                  <>
                    <input
                      type="number"
                      inputMode="decimal"
                      min={0}
                      step="0.01"
                      value={String(m.qty_per_unit)}
                      onChange={(e) => setMaterial(j, { qty_per_unit: e.target.value })}
                      aria-label={`Cantidad por prenda de ${materialName(m)}`}
                      className="h-11 w-20 rounded-md bg-surface px-2 text-right tabular-nums ring-1 ring-line sm:h-8"
                    />
                    <span className="w-7 text-xs text-muted">{unitLabel(m.unit)}</span>
                    <button
                      type="button"
                      onClick={() => setMaterial(j, null)}
                      aria-label={`Quitar ${materialName(m)}`}
                      className="flex size-11 shrink-0 items-center justify-center rounded-md text-muted hover:bg-surface hover:text-danger sm:size-8"
                    >
                      <X size={15} aria-hidden />
                    </button>
                  </>
                )}
              </li>
            );
          })}
        </ul>
      ) : (
        <p className="mt-1 text-sm text-muted">Sin insumos: Producción los agrega al desglosar.</p>
      )}
    </div>
  );
}

function ProductPicker({
  products,
  ai,
  onPick,
  onClose,
}: {
  products: Product[];
  ai: DraftProposal | null;
  onPick: (product: DraftProposal["product"]) => void;
  onClose: () => void;
}) {
  const [query, setQuery] = useState("");
  const q = query.trim().toLowerCase();
  const results = products.filter((p) => !q || p.name.toLowerCase().includes(q) || p.code.toLowerCase().includes(q)).slice(0, 6);
  const aiNew = ai && !ai.product.existing_id ? ai.product : null;

  return (
    <div className="magic-in mt-2 rounded-lg bg-surface p-2 shadow-lg ring-1 ring-line">
      <div className="flex items-center gap-2">
        <label className="relative min-w-0 flex-1">
          <Search size={15} className="pointer-events-none absolute left-2.5 top-1/2 -translate-y-1/2 text-muted" aria-hidden />
          <input
            autoFocus
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={(e) => e.key === "Escape" && onClose()}
            placeholder="Busca en el catálogo"
            aria-label="Buscar producto del catálogo"
            className="h-11 w-full rounded-md bg-canvas pl-8 pr-3 text-base ring-1 ring-line sm:h-9 sm:text-sm"
          />
        </label>
        <button type="button" onClick={onClose} aria-label="Cerrar el buscador" className="flex size-11 items-center justify-center rounded-md text-muted hover:bg-canvas sm:size-9">
          <X size={16} aria-hidden />
        </button>
      </div>
      <ul className="mt-1 max-h-60 overflow-y-auto">
        {results.map((p) => (
          <li key={p.id}>
            <button
              type="button"
              onClick={() => onPick({ existing_id: p.id, code: p.code, name: p.name, new: null })}
              className="flex min-h-11 w-full items-center justify-between gap-2 rounded-md px-2.5 py-2 text-left text-sm hover:bg-canvas"
            >
              <span>{p.name}</span>
              <span className="font-mono text-xs text-muted">{p.code}</span>
            </button>
          </li>
        ))}
        {!results.length && <li className="px-2.5 py-2 text-sm text-muted">Ningún producto coincide.</li>}
        {aiNew && (
          <li className="border-t border-line pt-1">
            <button type="button" onClick={() => onPick(aiNew)} className="flex min-h-11 w-full items-center gap-2 rounded-md px-2.5 py-2 text-left text-sm text-warning hover:bg-canvas">
              <Sparkles size={14} aria-hidden /> Dejarlo como producto nuevo · {aiNew.new?.name}
            </button>
          </li>
        )}
      </ul>
    </div>
  );
}
