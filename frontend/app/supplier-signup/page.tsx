"use client";

import { CheckCircle2 } from "lucide-react";
import { useState } from "react";
import { SupplierForm } from "@/components/supplier-form";
import { Lockup } from "@/components/brand";

// Public self-registration (ADR 0024, criterion 7). The Gerente reviews it in /suppliers.
export default function SupplierSignupPage() {
  const [sent, setSent] = useState(false);
  return (
    <main className="mx-auto max-w-lg px-4 py-8">
      <Lockup height={32} priority />
      {sent ? (
        <section className="mt-8 rounded-xl bg-success-soft p-6 text-center ring-1 ring-success/30">
          <CheckCircle2 className="mx-auto text-success" size={40} />
          <h1 className="mt-3 text-xl font-bold">Gracias por registrarte</h1>
          <p className="mt-2 text-sm text-muted">El Gerente revisará tu registro y te escribirá por WhatsApp si hay un pedido para ti.</p>
          <button type="button" onClick={() => setSent(false)} className="mt-5 text-sm font-medium text-accent underline">
            Registrar otro taller
          </button>
        </section>
      ) : (
        <>
          <h1 className="mt-6 text-xl font-bold">Registra tu taller o tu empresa de insumos</h1>
          <p className="mt-1 text-sm text-muted">Trabaja con Corpotex. Toma dos minutos; el celular es opcional, pero con él te podemos contactar directo.</p>
          <div className="mt-6 rounded-xl bg-surface p-5 ring-1 ring-line">
            <SupplierForm endpoint="/api/suppliers/self-register/" submitLabel="Enviar registro" onSaved={() => setSent(true)} />
          </div>
        </>
      )}
    </main>
  );
}
