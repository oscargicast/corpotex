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

export function stopKind(stop: RouteStop): "warehouse" | "workshop" | "customer" {
  if (stop.customer) return "customer";
  if (stop.supplier) return "workshop";
  return "warehouse";
}

const STOP_COLOR = { warehouse: "#15141c", workshop: "#0062fa", customer: "#12773d" };

// Numbered markers without image assets (Leaflet's default icons break with bundlers).
function icon(stop: RouteStop, faded: boolean) {
  const kind = stopKind(stop);
  const label = kind === "warehouse" ? "P" : String(stop.position);
  return L.divIcon({
    className: "",
    iconSize: [28, 28],
    iconAnchor: [14, 14],
    html: `<span style="display:flex;align-items:center;justify-content:center;width:28px;height:28px;border-radius:9999px;background:${STOP_COLOR[kind]};color:#fff;font:700 13px system-ui;border:2px solid #fff;box-shadow:0 1px 4px rgba(0,0,0,.35);opacity:${faded ? 0.55 : 1}">${label}</span>`,
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
        route.stops.map((stop) => (
          <Marker key={`${route.id}-${stop.position}`} position={[stop.lat, stop.lng]} icon={icon(stop, route.status === "replaced")}>
            <Tooltip direction="top" offset={[0, -12]}>
              <strong>{stop.name}</strong>
              <br />
              {stop.kind === "pickup" ? "Recojo" : "Entrega"}
              {stop.eta ? ` · ${new Date(stop.eta).toLocaleTimeString("es-PE", { hour: "2-digit", minute: "2-digit", timeZone: "America/Lima" })}` : ""}
            </Tooltip>
          </Marker>
        )),
      )}
      <FitBounds route={focus ?? routes[0]} />
    </MapContainer>
  );
}
