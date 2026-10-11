"use client";

import "leaflet/dist/leaflet.css";
import L from "leaflet";
import { useEffect, useMemo, useRef, useState } from "react";
import { MapContainer, Marker, Polyline, TileLayer, Tooltip, useMap } from "react-leaflet";
import type { FleetRoute, FleetStop, LivePosition, TrailPoint, Vehicle } from "./fleet-types";
import { hhmm, signalOf, type Signal } from "./fleet-utils";

const PIURA: [number, number] = [-5.1945, -80.6328];
const CARTO = "https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png";
const OSM = "https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png";
const GRAY = "#8a8994";

// Lucide icons as raw SVG for Leaflet's divIcon (no React inside markers).
const svg = (body: string, size = 16, stroke = "#fff") =>
  `<svg xmlns="http://www.w3.org/2000/svg" width="${size}" height="${size}" viewBox="0 0 24 24" fill="none" stroke="${stroke}" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">${body}</svg>`;
const TRUCK =
  '<path d="M14 18V6a2 2 0 0 0-2-2H4a2 2 0 0 0-2 2v11a1 1 0 0 0 1 1h2"/><path d="M15 18H9"/><path d="M19 18h2a1 1 0 0 0 1-1v-3.65a1 1 0 0 0-.22-.624l-3.48-4.35A1 1 0 0 0 17.52 8H14"/><circle cx="17" cy="18" r="2"/><circle cx="7" cy="18" r="2"/>';
const BIKE = '<circle cx="18.5" cy="17.5" r="3.5"/><circle cx="5.5" cy="17.5" r="3.5"/><circle cx="15" cy="5" r="1"/><path d="M12 17.5V14l-3-3 4-3 2 3h2"/>';
const FACTORY =
  '<path d="M12 16h.01"/><path d="M16 16h.01"/><path d="M3 19a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2V8l-7 5V8l-7 5V4a2 2 0 0 0-2-2H3z"/><path d="M8 16h.01"/>';
const CHECK = '<path d="M20 6 9 17l-5-5"/>';

function routePoints(route: FleetRoute): [number, number][] {
  if (route.path?.coordinates.length) return route.path.coordinates.map(([lng, lat]) => [lat, lng]);
  return [...route.stops].sort((a, b) => a.position - b.position).map((s) => [s.lat, s.lng]);
}

function stopIcon(stop: FleetStop, color: string, faded: boolean) {
  const done = !!stop.delivered_at;
  const inner = done ? svg(CHECK, 14, color) : String(stop.position);
  return L.divIcon({
    className: "",
    iconSize: [28, 28],
    iconAnchor: [14, 14],
    html: `<span style="display:flex;align-items:center;justify-content:center;width:28px;height:28px;border-radius:9999px;background:${done ? "#fff" : color};color:#fff;font:700 13px system-ui;font-variant-numeric:tabular-nums;border:2px solid ${done ? color : "#fff"};box-shadow:0 1px 4px rgba(0,0,0,.35);opacity:${faded ? 0.6 : 1}">${inner}</span>`,
  });
}

const PLANT_ICON = L.divIcon({
  className: "",
  iconSize: [32, 32],
  iconAnchor: [16, 16],
  html: `<span style="display:flex;align-items:center;justify-content:center;width:32px;height:32px;border-radius:8px;background:#15141c;border:2px solid #fff;box-shadow:0 1px 4px rgba(0,0,0,.35)">${svg(FACTORY)}</span>`,
});

function vehicleIcon(vehicle: Vehicle, heading: number | null, signal: Signal) {
  const color = signal === "none" ? GRAY : vehicle.color;
  const pulse = signal === "live" ? `<span class="animate-ping" style="position:absolute;inset:2px;border-radius:9999px;background:${color};opacity:.35"></span>` : "";
  const arrow =
    heading !== null && signal !== "none"
      ? `<span style="position:absolute;inset:0;transform:rotate(${heading}deg)"><span style="position:absolute;left:50%;top:-7px;transform:translateX(-50%);width:0;height:0;border-left:7px solid transparent;border-right:7px solid transparent;border-bottom:10px solid ${color}"></span></span>`
      : "";
  return L.divIcon({
    className: "",
    iconSize: [40, 40],
    iconAnchor: [20, 20],
    html: `<span style="position:relative;display:block;width:40px;height:40px">${pulse}${arrow}<span style="position:absolute;inset:4px;display:flex;align-items:center;justify-content:center;border-radius:9999px;background:${color};border:3px solid #fff;box-shadow:0 2px 6px rgba(0,0,0,.4)">${svg(vehicle.kind === "motorcycle" ? BIKE : TRUCK, 18)}</span></span>`,
  });
}

const reducedMotion = () => typeof window !== "undefined" && window.matchMedia("(prefers-reduced-motion: reduce)").matches;

// One vehicle, handled imperatively: the marker glides between two positions
// with requestAnimationFrame (Leaflet moves it with a transform) and jumps when
// the user prefers reduced motion.
function VehicleMarker({ vehicle, position, signal }: { vehicle: Vehicle; position: { lat: number; lng: number; heading: number | null }; signal: Signal }) {
  const map = useMap();
  const marker = useRef<L.Marker | null>(null);
  const frame = useRef(0);
  const lastUpdate = useRef(0);

  useEffect(() => {
    const m = L.marker([position.lat, position.lng], { icon: vehicleIcon(vehicle, position.heading, signal), zIndexOffset: 1000, keyboard: false })
      .bindTooltip(vehicle.name, { permanent: true, direction: "right", offset: [18, 0], className: "font-semibold" })
      .addTo(map);
    marker.current = m;
    return () => {
      cancelAnimationFrame(frame.current);
      m.remove();
      marker.current = null;
    };
    // Created once per vehicle; position and look update below.
  }, [map, vehicle.id]);

  useEffect(() => {
    marker.current?.setIcon(vehicleIcon(vehicle, position.heading, signal));
  }, [vehicle, position.heading, signal]);

  useEffect(() => {
    const m = marker.current;
    if (!m) return;
    const from = m.getLatLng();
    const to = L.latLng(position.lat, position.lng);
    cancelAnimationFrame(frame.current);
    if (reducedMotion() || from.distanceTo(to) > 5000) {
      m.setLatLng(to);
      return;
    }
    // Glide for as long as updates take to arrive (the simulator's interval plus
    // the tunnel's latency), so the marker never stops between two positions.
    const start = performance.now();
    const gap = lastUpdate.current ? start - lastUpdate.current : 3000;
    lastUpdate.current = start;
    const duration = Math.min(Math.max(gap, 600), 6000);
    const step = (t: number) => {
      const f = Math.min(1, (t - start) / duration);
      m.setLatLng([from.lat + (to.lat - from.lat) * f, from.lng + (to.lng - from.lng) * f]);
      if (f < 1) frame.current = requestAnimationFrame(step);
    };
    frame.current = requestAnimationFrame(step);
  }, [position.lat, position.lng]);

  return null;
}

// Fit to what is on screen when asked (button, first load, another day), and
// keep the followed vehicle centred.
function Camera({ bounds, fitSignal, follow, fullscreen }: { bounds: [number, number][]; fitSignal: number; follow: [number, number] | null; fullscreen: boolean }) {
  const map = useMap();
  const boundsRef = useRef(bounds);
  boundsRef.current = bounds;
  useEffect(() => {
    if (boundsRef.current.length) map.fitBounds(L.latLngBounds(boundsRef.current), { padding: [56, 56], maxZoom: 15 });
  }, [map, fitSignal]);
  useEffect(() => {
    if (follow) map.panTo(follow, { animate: !reducedMotion() });
  }, [map, follow?.[0], follow?.[1]]);
  useEffect(() => {
    const id = setTimeout(() => map.invalidateSize(), 250);
    return () => clearTimeout(id);
  }, [map, fullscreen]);
  return null;
}

export interface FleetMapProps {
  routes: FleetRoute[];
  vehicles: Vehicle[];
  positions: Record<number, LivePosition>;
  trails: Record<number, TrailPoint[]>;
  visible: number[];
  showVehicles: boolean;
  follow: number | null;
  fitSignal: number;
  fullscreen: boolean;
  now: number;
  plant: [number, number] | null;
}

export default function FleetMap({ routes, vehicles, positions, trails, visible, showVehicles, follow, fitSignal, fullscreen, now, plant }: FleetMapProps) {
  const [tiles, setTiles] = useState(CARTO);
  const errors = useRef(0);
  const shown = useMemo(() => routes.filter((r) => r.vehicle && visible.includes(r.vehicle.id)), [routes, visible]);

  const where = (v: Vehicle) => {
    const p = positions[v.id];
    const lat = p?.lat ?? v.last_lat;
    const lng = p?.lng ?? v.last_lng;
    if (lat === null || lng === null) return null;
    return { lat, lng, heading: p?.heading ?? v.last_heading, at: p?.at ?? v.last_seen_at };
  };
  const onMap = showVehicles ? vehicles.filter((v) => visible.includes(v.id)) : [];

  const bounds: [number, number][] = [
    ...shown.flatMap(routePoints),
    ...onMap.map(where).filter((p): p is NonNullable<ReturnType<typeof where>> => !!p).map((p): [number, number] => [p.lat, p.lng]),
  ];
  const followed = follow !== null ? vehicles.find((v) => v.id === follow) : undefined;
  const followAt = followed ? where(followed) : null;

  return (
    <MapContainer center={PIURA} zoom={13} scrollWheelZoom className="h-full w-full" attributionControl zoomControl={false}>
      <TileLayer
        key={tiles}
        url={tiles}
        attribution={'&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>' + (tiles === CARTO ? ' &copy; <a href="https://carto.com/attributions">CARTO</a>' : "")}
        eventHandlers={{
          tileerror: () => {
            errors.current += 1;
            if (errors.current > 6 && tiles === CARTO) setTiles(OSM); // CARTO unreachable: OSM as fallback.
          },
        }}
      />
      {shown.map((route) => {
        const color = route.vehicle?.color ?? GRAY;
        const done = route.status === "completed";
        return <Polyline key={route.id} positions={routePoints(route)} pathOptions={{ color, weight: done ? 4 : 5, opacity: done ? 0.55 : 0.9, dashArray: done ? "8 8" : undefined }} />;
      })}
      {showVehicles &&
        onMap.map((v) => {
          const trail = trails[v.id] ?? [];
          return trail.length > 1 ? (
            <Polyline key={`trail-${v.id}`} positions={trail.map((p): [number, number] => [p.lat, p.lng])} pathOptions={{ color: v.color, weight: 3, opacity: 0.45, dashArray: "2 7", lineCap: "round" }} />
          ) : null;
        })}
      {plant && (
        <Marker position={plant} icon={PLANT_ICON}>
          <Tooltip direction="top" offset={[0, -14]}>
            <strong>Planta Corpotex</strong>
            <br />
            Salida y regreso
          </Tooltip>
        </Marker>
      )}
      {shown.map((route) =>
        route.stops
          .filter((stop) => stop.kind === "delivery")
          .map((stop) => (
            <Marker key={`${route.id}-${stop.id}`} position={[stop.lat, stop.lng]} icon={stopIcon(stop, route.vehicle?.color ?? GRAY, route.status === "completed")}>
              <Tooltip direction="top" offset={[0, -12]}>
                <strong>
                  {stop.position}. {stop.name}
                </strong>
                <br />
                {stop.order ? `Orden ${stop.order.code} · ${stop.units} prendas` : stop.address}
                <br />
                {route.vehicle?.name} · {stop.delivered_at ? `Entregada ${hhmm(stop.delivered_at)}` : `Llega ${hhmm(stop.eta)}`}
                {stop.on_time === false ? " · Atrasada" : ""}
              </Tooltip>
            </Marker>
          )),
      )}
      {onMap.map((v) => {
        const p = where(v);
        return p ? <VehicleMarker key={v.id} vehicle={v} position={p} signal={signalOf(p.at, now)} /> : null;
      })}
      <Camera bounds={bounds} fitSignal={fitSignal} follow={followAt ? [followAt.lat, followAt.lng] : null} fullscreen={fullscreen} />
    </MapContainer>
  );
}
