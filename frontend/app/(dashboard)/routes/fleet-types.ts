// Fleet and dispatch shapes (ADR 0026 §3). Written by hand next to the page so
// the shared generated types do not have to move with this view.

export type RouteStatus = "proposed" | "planned" | "in_progress" | "completed" | "replaced" | "discarded";

export interface Vehicle {
  id: number;
  name: string;
  plate: string;
  kind: "van" | "pickup" | "motorcycle" | "truck";
  kind_display: string;
  capacity_units: number;
  color: string;
  driver_name: string;
  is_active: boolean;
  last_lat: number | null;
  last_lng: number | null;
  last_heading: number | null;
  last_speed_kmh: number | null;
  last_seen_at: string | null;
  sim_active: boolean;
}

export interface FleetStop {
  id: number;
  position: number;
  kind: "plant" | "pickup" | "delivery";
  name: string;
  address: string;
  lat: number;
  lng: number;
  eta: string | null;
  delivered_at: string | null;
  customer: { id: number; name: string } | null;
  order: { id: number; code: string; promised_on: string } | null;
  units: number;
  on_time: boolean | null;
}

export interface FleetRoute {
  id: number;
  name: string;
  date: string;
  status: RouteStatus;
  status_display: string;
  distance_km: string | number;
  duration_min: number;
  path: { type: "LineString"; coordinates: [number, number][] } | null; // [lng, lat]
  stops: FleetStop[];
  vehicle: { id: number; name: string; color: string; kind: Vehicle["kind"]; capacity_units: number } | null;
  started_at: string | null;
  completed_at: string | null;
  summary: { deliveries: number; delivered: number; units: number; capacity_pct: number | null; returns_at: string | null; text: string };
}

export interface Dispatch {
  order: { id: number; code: string; customer_name: string; units: number; promised_on: string };
  status: "ready" | "delivered";
  scheduled_on: string;
  delivered_at: string | null;
  address: string;
  lat: number | null;
  lng: number | null;
  route_id: number | null;
  vehicle: { id: number; name: string; color: string } | null;
  stop: { id: number; position: number; eta: string | null } | null;
  on_time: boolean;
}

export interface Unassigned {
  order_id: number;
  code: string;
  reason: "capacity" | "shift" | "no_coordinates";
  reason_display: string;
}

export interface PlanDayResult {
  routes: FleetRoute[];
  unassigned: Unassigned[];
  suggested_next_day: number[];
}

export interface LivePosition {
  vehicle_id: number;
  lat: number | null;
  lng: number | null;
  heading: number | null;
  speed_kmh: number | null;
  at: string | null;
  route_id: number | null;
  next_stop: { id: number; position: number; name: string; eta: string | null } | null;
  simulating: boolean;
}

export interface TrailPoint {
  lat: number;
  lng: number;
  recorded_at: string;
}

export interface StopEvent {
  route_id: number;
  stop_id: number;
  vehicle_id: number;
  order_code: string | null;
  delivered_at: string;
}
