"use client";

import { CheckCircle2, Minus, Plus, RotateCcw, Sparkles, TriangleAlert, Wand2, X } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { ApiError, apiFetch } from "@/lib/api";
import { num } from "@/lib/format";
import { type CriticalStep, MATERIAL_UNIT, type OrderDetail } from "@/lib/types";
import { Button, Card, SectionTitle } from "./ui";

// Ficha técnica editable por instrucción (ADR 0029 §4), Gerente and Producción:
// POST /api/orders/<id>/revise/ {instruction, dry_run: true} answers
// {proposal}; POST {proposal} sends it back as is to apply it, without asking
// the model again, so what is applied is exactly what was shown. It re-breaks
// the order down and recomputes the critical path (materials already ordered
// are not touched) and answers {order}.

interface RevisedMaterial {
  sku?: string | null;
  new?: { sku: string; name: string; kind?: string; unit: string } | null;
  name?: string | null;
  qty_per_unit: string | number;
  unit: string;
}

interface Revision {
  summary: string;
  items: {
    item_id: number;
    product?: { code: string; name: string } | null;
    quantity?: number;
    materials: RevisedMaterial[];
    current?: RevisedMaterial[] | null; // the effective recipe before the change
  }[];
  // Keys are stage codes (cutting, sublimation, embroidery, sewing, finishing);
  // stage_labels names them as the critical path does ("Corte").
  stage_overrides?: Record<string, number> | null;
  stage_current?: Record<string, number> | null;
  stage_labels?: Record<string, string> | null;
  warnings?: string[];
}

type ApplyResult = { order?: OrderDetail & { warnings?: string[] }; warnings?: string[]; proposal?: Revision };

const SHORT_UNIT: Record<string, string> = { unit: "u.", units: "u.", kg: "kg", m: "m" };
const unitLabel = (unit: string) => SHORT_UNIT[unit] ?? MATERIAL_UNIT[unit] ?? unit;
const keyOf = (m: RevisedMaterial) => m.sku ?? m.new?.sku ?? m.name ?? m.new?.name ?? "?";
const nameOf = (m: RevisedMaterial) => m.name ?? m.new?.name ?? m.sku ?? "Insumo";
const qty = (v: string | number) => num(v) ?? 0;
const fmt = (n: number) => n.toLocaleString("es-PE", { maximumFractionDigits: 3 });
const DAY = 86_400_000;
const time = (day: string) => new Date(`${day}T12:00:00-05:00`).getTime();

function errorText(err: unknown, fallback: string): string {
  return err instanceof ApiError ? ((err.body as { detail?: string } | null)?.detail ?? fallback) : fallback;
}

// Current days of a stage, from the critical path when the API does not send them.
function currentDays(stage: string, revision: Revision, steps: CriticalStep[]): number | null {
  const sent = revision.stage_current?.[stage];
  if (typeof sent === "number") return sent;
  const label = (revision.stage_labels?.[stage] ?? stage).toLowerCase();
  const step = steps.find((s) => s.stage === stage || s.name.toLowerCase() === label);
  if (!step) return null;
  return Math.max(1, Math.round((time(step.end) - time(step.start)) / DAY) + 1);
}

export function ReviseFicha({ order, onApplied }: { order: OrderDetail; onApplied: () => void }) {
  const [instruction, setInstruction] = useState("");
  const [busy, setBusy] = useState<"propose" | "apply" | null>(null);
  const [revision, setRevision] = useState<Revision | null>(null);
  const [proposal, setProposal] = useState<unknown>(null); // sent back as is to apply
  const [error, setError] = useState<{ text: string; retry: () => void } | null>(null);
  const [toast, setToast] = useState<Revision | null>(null);

  async function propose(text = instruction.trim()) {
    if (!text) return;
    setBusy("propose");
    setError(null);
    setRevision(null);
    try {
      const res = await apiFetch<Revision & { proposal?: Revision }>(`/api/orders/${order.id}/revise/`, { method: "POST", json: { instruction: text, dry_run: true } });
      const shown = res?.proposal ?? res;
      setRevision(shown);
      setProposal(shown);
    } catch (err) {
      setError({ text: errorText(err, "No se pudo preparar la propuesta."), retry: () => propose(text) });
    } finally {
      setBusy(null);
    }
  }

  async function apply() {
    setBusy("apply");
    setError(null);
    try {
      const res = await apiFetch<ApplyResult>(`/api/orders/${order.id}/revise/`, { method: "POST", json: { proposal } });
      setToast({
        ...(revision as Revision),
        summary: res?.proposal?.summary || revision?.summary || "Ficha técnica actualizada.",
        warnings: res?.warnings ?? res?.order?.warnings ?? res?.proposal?.warnings ?? [],
      });
      setRevision(null);
      setInstruction("");
      onApplied();
    } catch (err) {
      setError({ text: errorText(err, "No se pudo aplicar el cambio."), retry: apply });
    } finally {
      setBusy(null);
    }
  }

  const stages = Object.entries(revision?.stage_overrides ?? {});

  return (
    <Card className="xl:col-span-2">
      <SectionTitle>Ajustar la ficha técnica</SectionTitle>
      <form
        onSubmit={(e) => {
          e.preventDefault();
          propose();
        }}
        className="flex flex-col gap-2 sm:flex-row sm:items-start"
      >
        <label className="min-w-0 flex-1 text-sm">
          Ajustar la ficha técnica con una instrucción
          <textarea
            value={instruction}
            onChange={(e) => setInstruction(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                propose();
              }
            }}
            rows={2}
            placeholder="Ej.: agrega 2 botones por polo, el corte toma 3 días"
            className="mt-1 block w-full resize-y rounded-md bg-surface px-3 py-2.5 text-base ring-1 ring-line sm:text-sm"
          />
        </label>
        <Button kind="primary" type="submit" busy={busy === "propose"} disabled={!instruction.trim() || busy !== null} className="min-h-11 sm:mt-6">
          <Wand2 size={16} aria-hidden /> Proponer
        </Button>
      </form>
      <p className="mt-1 text-xs text-muted">Cambia solo esta orden; la receta del catálogo no se toca. Los insumos ya pedidos no cambian.</p>

      {busy === "propose" && (
        <div className="magic-shimmer mt-4 rounded-lg p-3" role="status">
          <p className="flex items-center gap-2 text-sm font-medium text-accent">
            <Sparkles size={15} aria-hidden /> Preparando la propuesta…
          </p>
          <div className="mt-2 space-y-1.5" aria-hidden>
            <div className="h-2.5 w-2/3 rounded-full bg-surface/70" />
            <div className="h-2.5 w-1/2 rounded-full bg-surface/70" />
          </div>
        </div>
      )}

      {error && (
        <p className="mt-4 flex flex-wrap items-center gap-2 text-sm text-warning" role="alert">
          <TriangleAlert size={15} aria-hidden /> {error.text}
          <button type="button" onClick={error.retry} className="inline-flex min-h-11 items-center gap-1 font-medium text-accent underline sm:min-h-0">
            <RotateCcw size={14} aria-hidden /> Reintentar
          </button>
        </p>
      )}

      {revision && (
        <div className="magic-in mt-4 space-y-4 rounded-lg bg-canvas p-4">
          <p className="text-sm">
            <span className="font-semibold">Propuesta:</span> {revision.summary}
          </p>
          {revision.items.map((item) => (
            <ItemDiff key={item.item_id} order={order} item={item} />
          ))}
          {stages.length > 0 && (
            <div>
              <p className="text-xs font-medium text-muted">Pasos</p>
              <ul className="mt-1 space-y-1 text-sm">
                {stages.map(([stage, days]) => {
                  const before = currentDays(stage, revision, order.critical_path);
                  return (
                    <li key={stage} className="tabular-nums">
                      <span className="font-medium">{revision.stage_labels?.[stage] ?? stage}</span>:{" "}
                      {before !== null && before !== days ? (
                        <>
                          <span className="text-muted line-through">{before}</span> → <span className="font-semibold text-accent">{days}</span> días
                        </>
                      ) : (
                        <span className="font-semibold text-accent">{days} días</span>
                      )}
                    </li>
                  );
                })}
              </ul>
            </div>
          )}
          <div className="flex flex-wrap gap-2">
            <Button kind="primary" busy={busy === "apply"} disabled={busy !== null} onClick={apply} className="min-h-11 sm:min-h-0">
              Aplicar
            </Button>
            <Button disabled={busy !== null} onClick={() => setRevision(null)} className="min-h-11 sm:min-h-0">
              Descartar
            </Button>
          </div>
        </div>
      )}

      {toast && <AppliedToast revision={toast} onClose={() => setToast(null)} />}
    </Card>
  );
}

function ItemDiff({ order, item }: { order: OrderDetail; item: Revision["items"][number] }) {
  const source = order.items.find((it) => it.id === item.item_id);
  const label = source
    ? `${source.quantity} × ${source.description || source.product?.name || "Prenda"}`
    : `${item.quantity ? `${item.quantity} × ` : ""}${item.product?.name ?? `Ítem ${item.item_id}`}`;
  const after = new Map(item.materials.map((m) => [keyOf(m), m]));
  const before = item.current ? new Map(item.current.map((m) => [keyOf(m), m])) : null;

  const rows: { key: string; kind: "add" | "remove" | "change" | "same"; m: RevisedMaterial; from?: number }[] = [];
  if (before) {
    for (const [key, m] of after) {
      const old = before.get(key);
      if (!old) rows.push({ key, kind: "add", m });
      else if (qty(old.qty_per_unit) !== qty(m.qty_per_unit)) rows.push({ key, kind: "change", m, from: qty(old.qty_per_unit) });
      else rows.push({ key, kind: "same", m });
    }
    for (const [key, m] of before) if (!after.has(key)) rows.push({ key, kind: "remove", m });
  } else {
    for (const [key, m] of after) rows.push({ key, kind: "same", m });
  }
  const changes = rows.filter((r) => r.kind !== "same");
  const same = rows.length - changes.length;

  return (
    <div>
      <p className="text-sm font-semibold">{label}</p>
      <ul className="mt-1 space-y-1 text-sm">
        {(before ? changes : rows).map((r) => (
          <li key={`${r.kind}-${r.key}`} className={`flex items-center gap-2 tabular-nums ${r.kind === "add" ? "text-success" : r.kind === "remove" ? "text-danger" : ""}`}>
            {r.kind === "add" ? <Plus size={14} aria-label="Entra" /> : r.kind === "remove" ? <Minus size={14} aria-label="Sale" /> : <span className="w-3.5" aria-hidden />}
            <span className={r.kind === "remove" ? "line-through" : ""}>{nameOf(r.m)}</span>
            {r.m.new && r.kind === "add" && <span className="text-xs">(nuevo)</span>}
            <span className="ml-auto text-muted">
              {r.kind === "change" ? (
                <>
                  {fmt(r.from!)} → <span className="font-semibold text-accent">{fmt(qty(r.m.qty_per_unit))}</span> {unitLabel(r.m.unit)}
                </>
              ) : (
                <>
                  {fmt(qty(r.m.qty_per_unit))} {unitLabel(r.m.unit)}
                </>
              )}{" "}
              por prenda
            </span>
          </li>
        ))}
      </ul>
      {before && same > 0 && (
        <p className="mt-1 text-xs text-muted">
          {same} {same === 1 ? "insumo sigue igual" : "insumos siguen iguales"}.
        </p>
      )}
      {before && !changes.length && <p className="text-xs text-muted">Sin cambios de insumos en esta prenda.</p>}
      {!before && <p className="mt-1 text-xs text-muted">La ficha propuesta completa (sin la anterior para comparar).</p>}
    </div>
  );
}

function AppliedToast({ revision, onClose }: { revision: Revision; onClose: () => void }) {
  const close = useRef(onClose);
  useEffect(() => {
    close.current = onClose;
  });
  useEffect(() => {
    const id = setTimeout(() => close.current(), 12_000);
    return () => clearTimeout(id);
  }, [revision]);
  return (
    <div role="status" className="fixed inset-x-4 bottom-20 z-50 rounded-xl bg-surface p-4 text-sm shadow-xl ring-1 ring-line md:inset-x-auto md:bottom-6 md:left-1/2 md:w-[30rem] md:-translate-x-1/2">
      <div className="flex items-start gap-3">
        <CheckCircle2 size={20} className="mt-0.5 shrink-0 text-success" aria-hidden />
        <div className="min-w-0 flex-1">
          <p className="font-semibold">Ficha técnica actualizada</p>
          <p className="mt-1">{revision.summary}</p>
          {(revision.warnings ?? []).map((w) => (
            <p key={w} className="mt-1 flex items-start gap-1 text-warning">
              <TriangleAlert size={13} className="mt-0.5 shrink-0" aria-hidden /> {w}
            </p>
          ))}
        </div>
        <button type="button" onClick={onClose} aria-label="Cerrar aviso" className="flex size-11 shrink-0 items-center justify-center text-muted hover:text-ink sm:size-8">
          <X size={16} />
        </button>
      </div>
    </div>
  );
}
