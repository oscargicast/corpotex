"use client";

import { FastForward, Pause, Play } from "lucide-react";
import { useEffect, useState } from "react";
import useSWR from "swr";
import { apiFetch, fetcher } from "@/lib/api";
import type { Clock as ClockState } from "@/lib/types";
import { useUser } from "./require-auth";

const FACTORS = [1, 60, 360, 1440];

const format = new Intl.DateTimeFormat("es-PE", {
  timeZone: "America/Lima",
  weekday: "short",
  day: "numeric",
  month: "short",
  hour: "2-digit",
  minute: "2-digit",
});

// Simulated business clock (accelerated). Polls every 3 s and ticks locally in between.
export function Clock() {
  const user = useUser();
  const { data, mutate } = useSWR<ClockState>("/api/clock/", fetcher, { refreshInterval: 3000 });
  const [fetchedAt, setFetchedAt] = useState(() => Date.now());
  const [, tick] = useState(0);

  useEffect(() => setFetchedAt(Date.now()), [data]);
  useEffect(() => {
    const id = setInterval(() => tick((n) => n + 1), 1000);
    return () => clearInterval(id);
  }, []);

  if (!data) return <div className="h-8 w-40 animate-pulse rounded-md bg-line" />;

  const elapsed = data.paused ? 0 : (Date.now() - fetchedAt) * data.factor;
  const now = new Date(new Date(data.now).getTime() + elapsed);

  async function update(patch: Partial<{ factor: number; paused: boolean; advance_hours: number }>) {
    const next = await apiFetch<ClockState>("/api/clock/", { method: "PATCH", json: patch });
    mutate(next, { revalidate: false });
  }

  return (
    <div className="flex items-center gap-2 text-sm">
      <span
        className="rounded-md bg-surface px-2 py-1 font-medium tabular-nums ring-1 ring-line"
        title="Hora simulada de la demo"
      >
        {format.format(now)}
      </span>
      {(data.paused || user.role !== "manager") && (
        <span className="hidden text-muted sm:inline">{data.paused ? "en pausa" : `×${data.factor}`}</span>
      )}
      {user.role === "manager" && (
        <div className="hidden items-center gap-1 md:flex">
          <button
            type="button"
            onClick={() => update({ paused: !data.paused })}
            className="rounded-md p-1.5 hover:bg-line"
            aria-label={data.paused ? "Reanudar reloj" : "Pausar reloj"}
            title={data.paused ? "Reanudar reloj" : "Pausar reloj"}
          >
            {data.paused ? <Play size={16} /> : <Pause size={16} />}
          </button>
          <select
            value={data.factor}
            onChange={(e) => update({ factor: Number(e.target.value) })}
            className="rounded-md bg-transparent px-1 py-1 text-muted hover:bg-line"
            aria-label="Velocidad del reloj"
          >
            {FACTORS.map((f) => (
              <option key={f} value={f}>
                ×{f}
              </option>
            ))}
          </select>
          <button
            type="button"
            onClick={() => update({ advance_hours: 24 })}
            className="flex items-center gap-1 rounded-md px-1.5 py-1 text-muted hover:bg-line"
            title="Adelantar un día"
          >
            <FastForward size={16} />
            <span className="hidden lg:inline">+1 día</span>
          </button>
        </div>
      )}
    </div>
  );
}
