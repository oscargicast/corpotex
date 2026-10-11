"use client";

import { useEffect, useRef, useState } from "react";
import { FilterChips, type ChipOption } from "./filter-chips";
import { SearchBox } from "./list-filters";

// The same bar on every list (Oscar, 11/10): the search on the left, the
// one-choice chips with counts, and room for one more control on the right
// (the group toggle of Pedidos). On the phone it stacks and the chips scroll.
export function FilterBar<K extends string>({
  search,
  chips,
  children,
}: {
  search: { value: string; onChange: (value: string) => void; placeholder?: string };
  chips: { options: ChipOption<K>[]; value: K; onChange: (key: K) => void; label: string };
  children?: React.ReactNode;
}) {
  // The box answers every keystroke; the URL (and the list) follow 200 ms
  // later, so fast typing never races the router. A change that comes from
  // outside (Limpiar filtros, back) still reaches the box.
  const [typed, setTyped] = useState(search.value);
  const sent = useRef(search.value);
  useEffect(() => {
    if (search.value !== sent.current) {
      sent.current = search.value;
      setTyped(search.value);
    }
  }, [search.value]);
  useEffect(() => {
    if (typed === sent.current) return;
    const id = setTimeout(() => {
      sent.current = typed;
      search.onChange(typed);
    }, 200);
    return () => clearTimeout(id);
  }, [typed, search]);

  return (
    <div className="flex flex-col gap-2 sm:flex-row sm:flex-wrap sm:items-center">
      <SearchBox value={typed} onChange={setTyped} placeholder={search.placeholder ?? "Buscar…"} />
      <FilterChips {...chips} />
      {children && <div className="sm:ml-auto">{children}</div>}
    </div>
  );
}
