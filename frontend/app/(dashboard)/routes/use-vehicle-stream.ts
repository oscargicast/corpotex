"use client";

import { useEffect, useRef, useState } from "react";
import { getSession } from "@/lib/auth";
import type { LivePosition, StopEvent } from "./fleet-types";

export type StreamMode = "off" | "connecting" | "live" | "polling";

// The vehicles' live positions (ADR 0026 §4). EventSource cannot send the token
// header, so the SSE is read with fetch and a ReadableStream and split by hand.
// If no snapshot arrives in 8 s (a proxy buffering the stream) or the stream
// fails, it falls back to polling /vehicles/live/ every 3 s.
export function useVehicleStream(ids: number[], enabled: boolean, onStop?: (event: StopEvent) => void) {
  const [positions, setPositions] = useState<Record<number, LivePosition>>({});
  const [mode, setMode] = useState<StreamMode>("off");
  const onStopRef = useRef(onStop);
  onStopRef.current = onStop;
  const key = [...ids].sort((a, b) => a - b).join(",");

  useEffect(() => {
    if (!enabled || !key) {
      setMode("off");
      return;
    }
    let cancelled = false;
    let controller: AbortController | null = null;
    let poll: ReturnType<typeof setInterval> | null = null;
    let retry: ReturnType<typeof setTimeout> | null = null;
    let lastId = "";
    const token = getSession()?.token;
    const auth: Record<string, string> = token ? { Authorization: `Token ${token}` } : {};

    const apply = (list: LivePosition[]) =>
      setPositions((prev) => {
        const next = { ...prev };
        for (const p of list) next[p.vehicle_id] = p;
        return next;
      });

    const startPolling = () => {
      if (cancelled || poll) return;
      setMode("polling");
      const load = () =>
        fetch(`/api/vehicles/live/?ids=${key}`, { headers: { ...auth, Accept: "application/json" }, cache: "no-store" })
          .then((r) => (r.ok ? (r.json() as Promise<LivePosition[]>) : []))
          .then(apply)
          .catch(() => undefined);
      void load();
      poll = setInterval(load, 3000);
    };

    const connect = async () => {
      controller = new AbortController();
      setMode((m) => (m === "live" ? m : "connecting"));
      const watchdog = setTimeout(() => controller?.abort(), 8000);
      try {
        const headers: Record<string, string> = { ...auth, Accept: "text/event-stream" };
        if (lastId) headers["Last-Event-ID"] = lastId;
        const res = await fetch(`/api/vehicles/stream/?ids=${key}`, { headers, cache: "no-store", signal: controller.signal });
        if (!res.ok || !res.body) throw new Error(`stream ${res.status}`);
        const reader = res.body.pipeThrough(new TextDecoderStream()).getReader();
        let buffer = "";
        for (;;) {
          const { value, done } = await reader.read();
          if (done) break;
          buffer += value;
          let cut = buffer.indexOf("\n\n");
          while (cut >= 0) {
            const block = buffer.slice(0, cut);
            buffer = buffer.slice(cut + 2);
            cut = buffer.indexOf("\n\n");
            let name = "message";
            let data = "";
            for (const line of block.split("\n")) {
              if (line.startsWith("id:")) lastId = line.slice(3).trim();
              else if (line.startsWith("event:")) name = line.slice(6).trim();
              else if (line.startsWith("data:")) data += line.slice(5).trim();
            }
            if (!data) continue; // ": ping" and "retry:" carry no data.
            clearTimeout(watchdog);
            const payload: unknown = JSON.parse(data);
            if (name === "snapshot") {
              apply(payload as LivePosition[]);
              setMode("live");
            } else if (name === "position") apply([payload as LivePosition]);
            else if (name === "stop") onStopRef.current?.(payload as StopEvent);
          }
        }
        clearTimeout(watchdog);
        if (!cancelled) retry = setTimeout(connect, 500); // The server closes after 10 min.
      } catch {
        clearTimeout(watchdog);
        if (!cancelled) startPolling();
      }
    };

    void connect();
    return () => {
      cancelled = true;
      controller?.abort();
      if (poll) clearInterval(poll);
      if (retry) clearTimeout(retry);
    };
  }, [enabled, key]);

  return { positions, mode };
}

// A clock for "live / no signal" badges: re-renders every `ms`.
export function useNow(ms = 5000): number {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), ms);
    return () => clearInterval(id);
  }, [ms]);
  return now;
}
