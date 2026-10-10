import type { SupplierListItem } from "@/lib/types";
import { Pill } from "./ui";

// WhatsApp channel: "Sin canal" means no active number (ADR 0016).
export function ChannelPill({ supplier }: { supplier: SupplierListItem }) {
  if (supplier.is_in_house) return <Pill tone="info">Planta propia</Pill>;
  if (!supplier.active_numbers_count) return <Pill tone="danger">Sin canal</Pill>;
  return (
    <Pill tone="success">
      {supplier.active_numbers_count} de {supplier.numbers_count} {supplier.numbers_count === 1 ? "activo" : "activos"}
    </Pill>
  );
}
