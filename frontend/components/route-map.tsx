"use client";

import "leaflet/dist/leaflet.css";
import L from "leaflet";
import { useEffect } from "react";
import { MapContainer, Marker, Polyline, TileLayer, Tooltip, useMap } from "react-leaflet";
import type { Route, RouteStop } from "@/lib/types";

const PIURA: [number, number] = [-5.1945, -80.6328];

// Same look as the legend: planned solid blue, proposed dashed green, replaced dashed gray.
export function lineStyle(status: Route["status"]): L.PathOptions {
  if (status === "proposed") return { color: "#12773d", weight: 5, dashArray: "10 8" };
  if (status === "replaced" || status === "discarded") return { color: "#8a8994", weight: 4, dashArray: "6 8", opacity: 0.8 };
  return { color: "#0062fa", weight: 5 };
}

// Straight lines between stops (ADR 0024): the API's GeoJSON path, or the stops in order.
function points(route: Route): [number, number][] {
  if (route.path?.coordinates.length) return route.path.coordinates.map(([lng, lat]) => [lat, lng]);
  return [...route.stops].sort((a, b) => a.position - b.position).map((s) => [s.lat, s.lng]);
}

// Routes are deliveries to customers from the plant (ADR 0024): the first and
// last stops are the plant, the rest customers. Supplier stops no longer exist.
export function isPlant(stop: RouteStop, route: Route): boolean {
  return !stop.customer && !stop.supplier && (stop.position === 0 || stop.position === route.stops.length - 1);
}

// What a stop is, for the list and the tooltip.
export function stopLabel(stop: RouteStop, route: Route): string {
  if (isPlant(stop, route)) return stop.position === 0 ? "Salida de la planta" : "Regreso a la planta";
  if (stop.customer) return `Entrega a ${stop.customer.name}${stop.order ? `, orden ${stop.order.code}` : ""}`;
  return stop.kind === "delivery" ? "Entrega" : stop.name;
}

const PLANT_ICON =
  '<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#fff" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M12 16h.01"/><path d="M16 16h.01"/><path d="M3 19a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2V8l-7 5V8l-7 5V4a2 2 0 0 0-2-2H3z"/><path d="M8 16h.01"/></svg>';

// Markers without image assets (Leaflet's default icons break with bundlers):
// a factory for the plant, the stop number for each customer.
function icon(stop: RouteStop, route: Route, faded: boolean) {
  const plant = isPlant(stop, route);
  return L.divIcon({
    className: "",
    iconSize: [28, 28],
    iconAnchor: [14, 14],
    html: `<span style="display:flex;align-items:center;justify-content:center;width:28px;height:28px;border-radius:9999px;background:${plant ? "#15141c" : "#12773d"};color:#fff;font:700 13px system-ui;border:2px solid #fff;box-shadow:0 1px 4px rgba(0,0,0,.35);opacity:${faded ? 0.55 : 1}">${plant ? PLANT_ICON : stop.position}</span>`,
  });
}

// Zoom to the route that matters (the new one in the scene); the replaced one
// may run off the edge, which is the point: that trip is no longer made.
function FitBounds({ route }: { route: Route | undefined }) {
  const map = useMap();
  const id = route?.id;
  useEffect(() => {
    const all = route ? points(route) : [];
    if (all.length) map.fitBounds(L.latLngBounds(all), { padding: [48, 48] });
    // Only when the focused route changes, not on every poll.
  }, [map, id]);
  return null;
}

export default function RouteMap({ routes, focus }: { routes: Route[]; focus?: Route }) {
  // Draw the faded routes first so the current one stays on top.
  const ordered = [...routes].sort((a, b) => Number(a.status !== "replaced") - Number(b.status !== "replaced"));
  return (
    <MapContainer center={PIURA} zoom={13} scrollWheelZoom={false} className="h-full min-h-[420px] w-full rounded-xl" attributionControl>
      <TileLayer
        attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
        url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
      />
      {ordered.map((route) => (
        <Polyline key={route.id} positions={points(route)} pathOptions={lineStyle(route.status)} />
      ))}
      {ordered.map((route) =>
        route.stops
          // The plant closes the loop: one marker is enough.
          .filter((stop) => !(isPlant(stop, route) && stop.position > 0))
          .map((stop) => (
            <Marker key={`${route.id}-${stop.position}`} position={[stop.lat, stop.lng]} icon={icon(stop, route, route.status === "replaced")}>
              <Tooltip direction="top" offset={[0, -12]}>
                <strong>{isPlant(stop, route) ? "Planta Corpotex" : stop.name}</strong>
                <br />
                {isPlant(stop, route) ? "Salida y regreso" : stopLabel(stop, route)}
                {stop.eta ? ` · ${new Date(stop.eta).toLocaleTimeString("es-PE", { hour: "2-digit", minute: "2-digit", timeZone: "America/Lima" })}` : ""}
              </Tooltip>
            </Marker>
          )),
      )}
      <FitBounds route={focus ?? routes[0]} />
    </MapContainer>
  );
}
