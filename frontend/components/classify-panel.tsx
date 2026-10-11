"use client";

import { CircleCheck, Plus, RotateCcw, Sparkles, Trash2, X } from "lucide-react";
import { useState } from "react";
import useSWR from "swr";
import { ApiError, apiFetch, fetcher } from "@/lib/api";
import { num } from "@/lib/format";
import {
  type Classification,
  type ClassificationItem,
  type ClassificationMaterial,
  MATERIAL_KIND,
  MATERIAL_UNIT,
  type Material,
  type OrderDetail,
  type Product,
} from "@/lib/types";
import { Button, Card, Pill, SectionTitle, Spinner, type Tone } from "./ui";

type Phase = "idle" | "classifying" | "review" | "applying" | "done";

const input = "mt-0.5 w-full rounded-md bg-surface px-2 py-1.5 text-sm ring-1 ring-line";
const BRANDS = ["UNICRACK", "NEXO", "Línea Médica Corpotex"];

function confidenceTone(value: number | null | undefined): Tone {
  const n = num(value) ?? 0;
  return n >= 0.8 ? "success" : n >= 0.5 ? "warning" : "danger";
}

function Confidence({ value }: { value: number | null | undefined }) {
  const n = num(value);
  if (n === null) return null;
  return <Pill tone={confidenceTone(n)}>{Math.round(n * 100)} % seguro</Pill>;
}

// Items without a catalog product: the AI proposes the product (existing or
// new) and its bill of materials; Producción or the Gerente edit and confirm
// (ADR 0025 C). POST classify, then POST apply-classification with the edited
// proposal.
export function ClassifyPanel({ order, onApplied }: { order: OrderDetail; onApplied: () => void }) {
  const [phase, setPhase] = useState<Phase>("idle");
  const [items, setItems] = useState<ClassificationItem[]>([]);
  const [error, setError] = useState<string | null>(null);
  const review = phase === "review" || phase === "applying";
  const { data: products } = useSWR<Product[]>(review ? "/api/products/" : null, fetcher);
  const { data: materials } = useSWR<Material[]>(review ? "/api/materials/" : null, fetcher);
  const pending = order.items.filter((item) => !item.product);

  async function classify() {
    setPhase("classifying");
    setError(null);
    try {
      const result = await apiFetch<Classification>(`/api/orders/${order.id}/classify/`, { method: "POST", json: {} });
      // Catalog recipes come with four decimals ("0.2500"); show them as typed ("0.25").
      setItems(
        result.items.map((item) => ({
          ...item,
          materials: item.materials.map((m) => ({ ...m, qty_per_unit: String(num(m.qty_per_unit) ?? m.qty_per_unit) })),
        })),
      );
      setPhase("review");
    } catch (err) {
      setError(err instanceof ApiError ? ((err.body as { detail?: string } | null)?.detail ?? "No se pudo clasificar.") : "No se pudo clasificar.");
      setPhase("idle");
    }
  }

  async function apply() {
    setPhase("applying");
    setError(null);
    try {
      await apiFetch(`/api/orders/${order.id}/apply-classification/`, { method: "POST", json: { items } });
      setPhase("done");
      onApplied();
    } catch (err) {
      setError(err instanceof ApiError ? ((err.body as { detail?: string } | null)?.detail ?? "No se pudo aplicar el desglose.") : "No se pudo aplicar el desglose.");
      setPhase("review");
    }
  }

  function updateItem(index: number, patch: Partial<ClassificationItem>) {
    setItems((all) => all.map((it, i) => (i === index ? { ...it, ...patch } : it)));
  }

  function updateMaterial(index: number, m: number, patch: Partial<ClassificationMaterial>) {
    setItems((all) => all.map((it, i) => (i === index ? { ...it, materials: it.materials.map((mat, j) => (j === m ? { ...mat, ...patch } : mat)) } : it)));
  }

  if (phase === "done" && !pending.length) return null;

  return (
    <Card className={review ? "xl:col-span-2" : ""}>
      <div className="flex flex-wrap items-center gap-2">
        <SectionTitle count={pending.length}>Desglosar componentes</SectionTitle>
        {phase === "idle" && (
          <Button kind="primary" className="ml-auto" onClick={classify}>
            <Sparkles size={16} /> Desglosar componentes
          </Button>
        )}
      </div>
      {phase === "idle" && (
        <p className="text-sm text-muted">
          {pending.length === 1 ? "Un ítem no tiene producto en el catálogo" : `${pending.length} ítems no tienen producto en el catálogo`}. La IA propone el producto y su
          lista de materiales; tú revisas y confirmas.
        </p>
      )}
      {phase === "classifying" && (
        <div className="flex items-center gap-3 rounded-lg bg-canvas px-3 py-3 text-sm" role="status">
          <Spinner className="text-accent" />
          <span>
            <strong>Clasificando con IA…</strong> lee la descripción de cada prenda y arma su lista de materiales. Puede tardar entre 10 y 30 segundos.
          </span>
        </div>
      )}
      {phase === "done" && (
        <p className="rounded-lg bg-success-soft px-3 py-2 text-sm text-success" role="status">
          Desglose aplicado: los productos y materiales nuevos ya están en el catálogo y la orden se desglosó contra inventario.
        </p>
      )}
      {error && (
        <p className="mt-2 text-sm text-danger" role="alert">
          {error}
        </p>
      )}

      {review && (
        <div className="mt-3 space-y-4">
          {items.map((proposal, index) => {
            const source = order.items.find((it) => it.id === proposal.item_id);
            const existingId = proposal.product.existing_id ?? null;
            const isNew = !existingId;
            return (
              <article key={proposal.item_id} className="rounded-lg p-3 ring-1 ring-line">
                <p className="text-sm font-semibold">
                  {source ? `${source.quantity} × ${source.description || source.product?.name || `Ítem ${proposal.item_id}`}` : `Ítem ${proposal.item_id}`}
                </p>

                <div className="mt-2 grid gap-2 sm:grid-cols-[minmax(0,1fr)_auto] sm:items-end">
                  <label className="text-xs text-muted">
                    Producto
                    <select
                      value={isNew ? "new" : String(existingId)}
                      onChange={(e) => {
                        const value = e.target.value;
                        if (value === "new") {
                          updateItem(index, { product: { existing_id: null, new: proposal.product.new ?? { code: "", name: source?.description?.slice(0, 40) ?? "", brand: order.brand.name } } });
                        } else {
                          updateItem(index, { product: { existing_id: Number(value), new: null } });
                        }
                      }}
                      className={input}
                      aria-label={`Producto para el ítem ${proposal.item_id}`}
                    >
                      <option value="new">Producto nuevo</option>
                      {(products ?? []).map((p) => (
                        <option key={p.id} value={p.id}>
                          {p.name} · {p.code}
                        </option>
                      ))}
                    </select>
                  </label>
                  <Confidence value={proposal.confidence} />
                </div>
                {isNew && (
                  <div className="mt-2 grid gap-2 sm:grid-cols-[9rem_minmax(0,1fr)_minmax(0,14rem)]">
                    <label className="text-xs text-muted">
                      Código
                      <input
                        value={proposal.product.new?.code ?? ""}
                        onChange={(e) => updateItem(index, { product: { existing_id: null, new: { ...(proposal.product.new ?? { name: "", brand: order.brand.name }), code: e.target.value.toUpperCase() } } })}
                        placeholder="UNI-BUZ-02"
                        className={`${input} font-mono`}
                      />
                    </label>
                    <label className="text-xs text-muted">
                      Nombre
                      <input
                        value={proposal.product.new?.name ?? ""}
                        onChange={(e) => updateItem(index, { product: { existing_id: null, new: { ...(proposal.product.new ?? { code: "", brand: order.brand.name }), name: e.target.value } } })}
                        className={input}
                      />
                    </label>
                    <label className="text-xs text-muted">
                      Marca
                      <input
                        list="classify-brands"
                        value={proposal.product.new?.brand ?? order.brand.name}
                        onChange={(e) => updateItem(index, { product: { existing_id: null, new: { ...(proposal.product.new ?? { code: "", name: "" }), brand: e.target.value } } })}
                        className={input}
                      />
                    </label>
                  </div>
                )}

                <p className="mt-3 text-xs font-medium text-muted">Materiales por prenda</p>
                <ul className="mt-1 space-y-1.5">
                  {proposal.materials.map((material, m) => {
                    const newMaterial = !material.sku;
                    return (
                      <li key={m} className="rounded-md bg-canvas p-2">
                        <div className="grid grid-cols-[minmax(0,1fr)_5rem_auto_2rem] items-end gap-2">
                          <label className="text-xs text-muted">
                            Insumo
                            <select
                              value={newMaterial ? "new" : material.sku!}
                              onChange={(e) => {
                                const value = e.target.value;
                                if (value === "new") updateMaterial(index, m, { sku: null, new: material.new ?? { sku: "", name: "", kind: "other", unit: material.unit || "unit" } });
                                else {
                                  const found = (materials ?? []).find((x) => x.sku === value);
                                  updateMaterial(index, m, { sku: value, new: null, unit: found?.unit ?? material.unit });
                                }
                              }}
                              className={input}
                              aria-label={`Insumo ${m + 1} del ítem ${proposal.item_id}`}
                            >
                              <option value="new">Insumo nuevo</option>
                              {(materials ?? []).map((x) => (
                                <option key={x.id} value={x.sku}>
                                  {x.sku} · {x.name}
                                </option>
                              ))}
                              {material.sku && !(materials ?? []).some((x) => x.sku === material.sku) && <option value={material.sku}>{material.sku}</option>}
                            </select>
                          </label>
                          <label className="text-xs text-muted">
                            Cant./prenda
                            <input
                              type="number"
                              inputMode="decimal"
                              min={0}
                              step="0.01"
                              value={String(material.qty_per_unit)}
                              onChange={(e) => updateMaterial(index, m, { qty_per_unit: e.target.value })}
                              className={`${input} tabular-nums`}
                              aria-label={`Cantidad por prenda del insumo ${m + 1}`}
                            />
                          </label>
                          <span className="pb-2 text-xs text-muted">{MATERIAL_UNIT[material.unit] ?? material.unit}</span>
                          <button
                            type="button"
                            onClick={() => updateItem(index, { materials: proposal.materials.filter((_, j) => j !== m) })}
                            className="justify-self-end rounded-md p-1.5 text-muted hover:bg-surface hover:text-danger"
                            aria-label={`Quitar insumo ${m + 1}`}
                          >
                            <Trash2 size={14} />
                          </button>
                        </div>
                        {newMaterial && (
                          <div className="mt-2 grid grid-cols-[9rem_minmax(0,1fr)] gap-2 lg:grid-cols-[9rem_minmax(0,1fr)_9rem_7rem]">
                            <label className="text-xs text-muted">
                              SKU
                              <input value={material.new?.sku ?? ""} onChange={(e) => updateMaterial(index, m, { new: { ...(material.new ?? { name: "", kind: "other", unit: "unit" }), sku: e.target.value.toUpperCase() } })} className={`${input} font-mono`} />
                            </label>
                            <label className="text-xs text-muted">
                              Nombre
                              <input value={material.new?.name ?? ""} onChange={(e) => updateMaterial(index, m, { new: { ...(material.new ?? { sku: "", kind: "other", unit: "unit" }), name: e.target.value } })} className={input} />
                            </label>
                            <label className="text-xs text-muted">
                              Tipo
                              <select value={material.new?.kind ?? "other"} onChange={(e) => updateMaterial(index, m, { new: { ...(material.new ?? { sku: "", name: "", unit: "unit" }), kind: e.target.value } })} className={input}>
                                {Object.entries(MATERIAL_KIND).map(([value, label]) => (
                                  <option key={value} value={value}>
                                    {label}
                                  </option>
                                ))}
                              </select>
                            </label>
                            <label className="text-xs text-muted">
                              Unidad
                              <select
                                value={material.new?.unit ?? material.unit ?? "unit"}
                                onChange={(e) => updateMaterial(index, m, { unit: e.target.value, new: { ...(material.new ?? { sku: "", name: "", kind: "other" }), unit: e.target.value } })}
                                className={input}
                              >
                                {Object.entries(MATERIAL_UNIT).map(([value, label]) => (
                                  <option key={value} value={value}>
                                    {label}
                                  </option>
                                ))}
                              </select>
                            </label>
                          </div>
                        )}
                        <div className="mt-1">
                          <Confidence value={material.confidence} />
                        </div>
                      </li>
                    );
                  })}
                </ul>
                <Button
                  type="button"
                  size="sm"
                  className="mt-2"
                  onClick={() => updateItem(index, { materials: [...proposal.materials, { sku: null, new: { sku: "", name: "", kind: "other", unit: "unit" }, qty_per_unit: "1", unit: "unit" }] })}
                >
                  <Plus size={14} /> Agregar insumo
                </Button>
              </article>
            );
          })}
          <datalist id="classify-brands">
            {BRANDS.map((b) => (
              <option key={b} value={b} />
            ))}
          </datalist>
          <div className="flex flex-wrap gap-2">
            <Button disabled={phase === "applying"} onClick={() => setPhase("idle")}>
              <X size={16} aria-hidden /> Cancelar
            </Button>
            <Button disabled={phase === "applying"} onClick={classify}>
              <RotateCcw size={16} aria-hidden /> Volver a clasificar
            </Button>
            <Button kind="primary" busy={phase === "applying"} onClick={apply}>
              <CircleCheck size={16} aria-hidden /> Confirmar desglose
            </Button>
          </div>
        </div>
      )}
    </Card>
  );
}
