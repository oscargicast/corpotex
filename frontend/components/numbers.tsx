"use client";

import { useState } from "react";
import { ApiError, apiFetch } from "@/lib/api";
import type { SupplierNumber } from "@/lib/types";
import { Button, Pill } from "./ui";

// WhatsApp numbers of a supplier (ADR 0016). New numbers start inactive; the
// agent only writes to active ones. Numbers are never deleted, only turned off.
export function Numbers({ supplierId, numbers, onChange }: { supplierId: number; numbers: SupplierNumber[]; onChange: () => void }) {
  const [confirming, setConfirming] = useState<number | null>(null);
  const [phone, setPhone] = useState("");
  const [name, setName] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function setActive(number: SupplierNumber, active: boolean) {
    setBusy(true);
    setError(null);
    try {
      await apiFetch(`/api/suppliers/${supplierId}/numbers/${number.id}/`, { method: "PATCH", json: { active } });
      setConfirming(null);
      onChange();
    } catch {
      setError("No se pudo cambiar el número.");
    } finally {
      setBusy(false);
    }
  }

  async function add(e: React.FormEvent) {
    e.preventDefault();
    const digits = phone.replace(/\D/g, "");
    if (digits.length < 9) {
      setError("Escribe el celular con código de país, por ejemplo 51987654321.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await apiFetch(`/api/suppliers/${supplierId}/numbers/`, { method: "POST", json: { phone: digits, name } });
      setPhone("");
      setName("");
      onChange();
    } catch (err) {
      setError(err instanceof ApiError && err.status === 400 ? "Ese número no es válido o ya existe." : "No se pudo agregar el número.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div>
      {numbers.length ? (
        <ul className="divide-y divide-line">
          {numbers.map((number) => (
            <li key={number.id} className="py-2.5 first:pt-0">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div className="text-sm">
                  {/* Simulated numbers are ids like "sim-confecciones-norte", not phones. */}
                  <p className="font-medium tabular-nums">{number.simulated ? "Número del simulador" : `+${number.phone}`}</p>
                  {number.name && !(number.simulated && number.name === "Simulador") && <p className="text-xs text-muted">{number.name}</p>}
                </div>
                <div className="flex items-center gap-2">
                  {number.simulated && <Pill tone="info">Simulador</Pill>}
                  {number.active ? <Pill tone="success">Activo para WhatsApp</Pill> : <Pill>Inactivo</Pill>}
                  {number.active ? (
                    <Button className="py-1" busy={busy} onClick={() => setActive(number, false)}>
                      Desactivar
                    </Button>
                  ) : (
                    confirming !== number.id && (
                      <Button kind="dark" className="py-1" disabled={busy} onClick={() => setConfirming(number.id)}>
                        Activar
                      </Button>
                    )
                  )}
                </div>
              </div>
              {confirming === number.id && (
                <div className="mt-2 flex flex-wrap items-center gap-2 rounded-md bg-warning-soft px-3 py-2 text-sm text-warning">
                  El agente podrá escribirle a este número.
                  <Button kind="dark" className="py-1" busy={busy} onClick={() => setActive(number, true)}>
                    Activar
                  </Button>
                  <Button className="py-1" onClick={() => setConfirming(null)}>
                    Cancelar
                  </Button>
                </div>
              )}
            </li>
          ))}
        </ul>
      ) : (
        <p className="text-sm text-muted">Sin números. Sin un número activo, el agente no puede escribirle (sin canal).</p>
      )}

      <form onSubmit={add} className="mt-4 flex flex-wrap items-end gap-2 border-t border-line pt-4">
        <label className="text-sm">
          <span className="block text-xs text-muted">Celular</span>
          <input
            value={phone}
            onChange={(e) => setPhone(e.target.value)}
            inputMode="tel"
            placeholder="51987654321"
            className="mt-1 w-40 rounded-md px-2 py-1.5 tabular-nums ring-1 ring-line"
          />
        </label>
        <label className="text-sm">
          <span className="block text-xs text-muted">Etiqueta</span>
          <input value={name} onChange={(e) => setName(e.target.value)} placeholder="dueño, encargado" className="mt-1 w-36 rounded-md px-2 py-1.5 ring-1 ring-line" />
        </label>
        <Button type="submit" busy={busy} disabled={!phone}>
          Agregar número
        </Button>
      </form>
      {error && (
        <p className="mt-2 text-sm text-danger" role="alert">
          {error}
        </p>
      )}
    </div>
  );
}
