// API types. `S` are the schemas generated from docs/api/openapi.json
// (lib/api-types.ts, `pnpm gen:types`). Hand-written shapes remain only where
// the schema types a nested field as `object` or marks as optional something
// the API always sends.
import type { components } from "./api-types";

type S = components["schemas"];

// DRF serializes decimals as strings; a few views still send numbers. Always go
// through num()/formatNum() (lib/format) before arithmetic or .toFixed.
export type Decimal = string | number;

export interface Rating {
  delay_days: number;
  quality: Decimal;
  defect_pct: Decimal;
  score: Decimal;
  rated_at: string;
}

export type Role = "manager" | "sales" | "production";

export interface User {
  id: number;
  username: string;
  first_name: string;
  role: Role;
}

export interface LoginResponse {
  token: string;
  user: User;
}

export type Clock = S["Clock"];

export type Badges = S["Badges"];

export type Currency = "PEN" | "USD";
export type Risk = "ok" | "at_risk" | "in_danger";
export type Severity = "info" | "warning" | "critical";

export interface Ref {
  id: number;
  code: string;
}

export interface OrderListItem {
  id: number;
  code: string;
  customer: { id: number; name: string };
  brand: { id: number; name: string };
  status: string;
  status_display: string;
  risk: Risk;
  risk_reason: string;
  promised_on: string;
  estimated_on: string | null;
  slack_days: number | null;
  total_units: number | string; // Decimal in the API
  purchase_orders_summary?: { total: number; confirmed: number; waiting_manager: number };
}

export interface PurchaseOrderListItem {
  id: number;
  code: string;
  kind: "material" | "workshop" | "finished";
  kind_display: string;
  status: string;
  status_display: string;
  waiting_manager: boolean;
  supplier: { id: number; name: string; kind: string };
  orders: (Ref & { customer_name: string })[];
  total_units: number | string; // Decimal in the API
  units_done: number;
  progress_pct: number;
  internal_due_on: string | null;
  committed_on: string | null;
  last_progress_at: string | null;
  next_follow_up_at: string | null;
  total_amount?: string | null; // hidden for production
  currency: Currency;
  redistributed_from: Ref | null;
  alert_severity: Severity | null;
}

export type Payment = Omit<S["Payment"], "purchase_order" | "due_on"> & { due_on: string | null };

export type ProgressReport = Omit<S["ProgressReport"], "photo"> & { photo: string | null };

export type ChatMessage = S["Message"] & { media_kind?: "image" | "audio" | "document" | null }; // media_kind is not in the API

export interface PurchaseOrderDetail extends PurchaseOrderListItem {
  status_history?: StatusHistoryEntry[];
  rationale: string | null;
  scores: Record<string, Decimal> | null;
  candidates: Candidate[] | null;
  changed_by_manager: boolean;
  terms: string;
  delivered_on: string | null;
  items: {
    id: number;
    name: string;
    image: string | null;
    order_code: string;
    quantity: string;
    unit_price?: string | null;
    qty_delivered: string;
  }[];
  progress_reports: ProgressReport[];
  payments: Payment[];
  paid_amount: string | null;
  pending_amount: string | null;
  conversation_id: number | null;
  // Reduced in the API: {id, kind, summary, detail}.
  pending_decision: DecisionLike | null;
  suggested_supplier: { id: number; name: string } | null;
  redistributed_into: (Ref & { supplier_name: string; quantity: Decimal; status_display: string })[];
  rating: Rating | null;
}

export interface SupplierListItem {
  id: number;
  name: string;
  kind: "materials" | "workshop" | "finished";
  kind_display: string;
  specialties: string[];
  city: string;
  weekly_capacity: number | null;
  lead_time_days: number | null;
  currency: Currency;
  load_pct: number | null;
  on_time_score: Decimal | null; // 0 to 1
  quality_score: Decimal | null; // 1 to 5
  open_purchase_orders: number;
  numbers_count: number;
  active_numbers_count: number;
  source: "registered" | "self_registered" | "external";
  source_display: string;
  status: "active" | "pending_review" | "inactive";
  status_display: string;
  is_in_house: boolean;
}

export type SupplierNumber = S["AllowedNumber"];

export interface SupplierDetail extends SupplierListItem {
  notes: string;
  address?: string;
  follow_up_every_hours: number;
  source_detail: { url: string; excerpt: string } | null;
  numbers: SupplierNumber[];
  rates: { id: number; item_name: string; unit_price: string; currency: Currency; valid_from: string; material_id?: number | null; product_id?: number | null; image?: string | null }[];
  ratings: (Rating & { purchase_order_code: string })[];
  purchase_orders: PurchaseOrderListItem[];
  payments_summary: { currency: Currency; paid: string; pending: string; overdue_count: number }[];
}

export interface Named {
  id: number;
  name: string;
  image?: string | null;
}

export interface OrderItem {
  id: number;
  product: Named & { code: string };
  quantity: number;
  sizes: Record<string, number>;
  color: string;
  customization: string;
  unit_price?: string | null;
}

export interface Requirement {
  id: number;
  kind: "material" | "workshop" | "finished";
  kind_display: string;
  material?: (Named & { unit: string }) | null;
  product?: Named | null;
  qty_needed: string;
  qty_from_stock: string;
  qty_to_order: string;
  status: string;
  status_display: string;
  purchase_orders: (Ref & { supplier_name: string; quantity: string; status_display: string })[];
}

export interface CriticalStep {
  id: string;
  name: string;
  kind: "material" | "workshop" | "production" | "delivery";
  start: string;
  end: string;
  critical: boolean;
  status: "pending" | "in_progress" | "done" | "late";
  purchase_order_id: number | null;
}

// One row per status change (system, agent or a user), oldest first.
export interface StatusHistoryEntry {
  status: string;
  status_display: string;
  at: string;
  actor: string | null; // system | agent | user | a username
  note?: string | null;
}

export interface OrderDetail extends OrderListItem {
  status_history?: StatusHistoryEntry[];
  issued_on: string;
  production_stage: string | null;
  owner: { id: number; first_name: string } | null;
  notes?: string | null;
  total_amount?: string | null;
  items: OrderItem[];
  requirements: Requirement[];
  critical_path: CriticalStep[];
  purchase_orders: PurchaseOrderListItem[];
  alerts: Alert[];
  redistributions: Decision[];
}

export interface Alert {
  id: number;
  kind: string;
  kind_display: string;
  severity: Severity;
  status: "open" | "acknowledged" | "resolved";
  text: string;
  detected_at: string;
  order: Ref | null;
  purchase_order: (Ref & { supplier_name: string }) | null;
}

// The matching sends the supplier nested; the redistribution sends it flat
// (supplier_id, supplier_name). Read it through candidateSupplier().
export interface Candidate {
  supplier?: { id: number; name: string } | null;
  supplier_id?: number;
  supplier_name?: string;
  score: Decimal;
  scores: Record<string, Decimal>; // on_time, price, load, quality: 0 to 1
  unit_price: string;
  load_pct: number;
  rationale: string;
}

export interface ProposalItem {
  purchase_order: Ref | null;
  supplier: { id: number; name: string };
  quantity: number | string; // Decimal in the API
  unit_price: string;
  currency: Currency;
  rationale: string;
  candidates: Candidate[];
}

export interface Snapshot {
  estimated_on?: string | null; // price decisions carry only the amount
  total_amount: string;
  currency?: Currency;
  route_id?: number | null;
}

export interface Decision {
  id: number;
  kind: string;
  kind_display: string;
  status: string;
  status_display: string;
  summary: string;
  detail: {
    before?: Snapshot | null;
    after?: Snapshot;
    proposal?: ProposalItem[];
    cancelled?: { code: string; supplier_name: string; quantity: Decimal; units_done: number };
  };
  created_at: string;
  purchase_orders: (Ref & { supplier_name: string })[];
  orders: (Ref & { customer_name: string })[];
}

export interface PaymentSummary {
  supplier: { id: number; name: string };
  currency: Currency;
  paid: string;
  pending: string;
  overdue_count: number;
}

export interface Monitor {
  clock: Clock;
  kpis: S["MonitorKpis"];
  alerts: Alert[];
  decisions: Decision[];
  orders_in_danger: OrderListItem[];
  redistributions: Decision[];
  payments_by_supplier?: PaymentSummary[];
}

export type DecisionAction = "approve" | "reject" | "change_supplier";

export type DecisionLike = Pick<Decision, "id" | "kind" | "summary" | "detail"> & Partial<Decision>;

export const DECISION_KIND: Record<string, string> = {
  approve_assignment: "Aprobar asignación",
  price: "Precio",
  terms: "Términos",
  other: "Otro",
};

export const CUSTOMIZATION: Record<string, string> = {
  embroidery: "Bordado",
  sublimation: "Sublimado",
  print: "Estampado",
  screen_print: "Serigrafía",
};

// Assistant chat (ADR 0017 and 0020).
export type LinkKind = "order" | "purchase_order" | "decision" | "supplier";

export type AssistantAction =
  | {
      kind: "tool";
      tool: string;
      status: "done" | "failed";
      title: string;
      summary: string;
      links: { kind: LinkKind; id: number; code?: string }[];
    }
  | {
      kind: "alert";
      alert_ids: number[];
      alerts: {
        id: number;
        kind: string;
        kind_display: string;
        severity: Severity;
        order: Ref | null;
        purchase_order: Ref | null;
      }[];
    };

export type AssistantMessage = Omit<S["AssistantMessage"], "role" | "text" | "action"> & {
  role: "user" | "assistant";
  text: string;
  action: AssistantAction | null;
};

// Inventory (F2.6): stock, reserved by open orders, and what is left.
export type Material = Omit<S["Material"], "stock"> & { stock: string | number };

export type MaterialDetail = Omit<S["MaterialDetailSchema"], "stock"> & { stock: string | number };

// Onboarding (ADR 0011, 0019) and style history.
export type StyleSupplierStatus = S["StyleSupplierProgressStatusEnum"];

export type StyleState = S["OnboardingStyle"];

export type StyleVersion = S["StyleVersion"];

export type StyleVersionDetail = S["StyleVersionDetail"];

export type WhatsAppState = S["WhatsAppOnboarding"];

// Routes (ADR 0024): straight lines between stops, no routing service.
export type RouteStop = Omit<S["RouteStop"], "supplier" | "customer" | "purchase_order" | "order"> & {
  supplier?: { id: number; name: string } | null;
  customer?: { id: number; name: string } | null;
  purchase_order?: Ref | null;
  order?: Ref | null;
};

export type Route = Omit<S["Route"], "status" | "distance_km" | "duration_min" | "path" | "stops"> & {
  status: S["RouteStatusEnum"];
  distance_km: string | number;
  duration_min: number;
  path: { type: "LineString"; coordinates: [number, number][] } | null; // [lng, lat]
  stops: RouteStop[];
};

// Simulator (ADR 0017 demo decision: one real supplier on WhatsApp, the rest here).
export type SimulatorContact = S["SimulatorContact"];

export interface AssistantContext {
  path: string;
  view: string;
  id?: number;
}

// /api/settings/claude/* (ADR 0022). The credential itself never reaches the browser.
// expires_at and refresh_token_expires_at arrive as epoch numbers (seconds or ms).
export type ClaudeStatus = S["ClaudeStatus"];

export type ClaudeErrorCode =
  | "invalid_code"
  | "missing_state"
  | "unreachable"
  | "key_rejected"
  | "key_unverifiable"
  | "key_format"
  | "not_connected";

export const ROLE_LABELS: Record<Role, string> = {
  manager: "Gerente",
  sales: "Comercial",
  production: "Producción",
};

export function candidateSupplier(candidate: Candidate): { id: number; name: string } {
  return candidate.supplier ?? { id: candidate.supplier_id ?? 0, name: candidate.supplier_name ?? "—" };
}

// "Por pedir" (ADR 0025 A): open material requirements grouped by material.
// GET /api/requirements/pending/; prices only reach the Gerente.
export interface PendingRequirement {
  material: { id: number; sku: string; name: string; unit: string; image?: string | null };
  total_to_order: Decimal;
  due_on: string | null; // the earliest of its orders
  orders: { id: number; code: string; customer_name: string; qty: Decimal; due_on: string | null }[];
  suggested_supplier: { id: number; name: string } | null;
  candidates?: { supplier: { id: number; name: string }; unit_price?: Decimal | null; currency?: Currency; score?: Decimal | null }[]; // [] for Producción
  reference_price?: Decimal | null; // Gerente only; per unit, in `currency`
  currency?: Currency;
  alert_id?: number | null;
}

// POST /api/purchase-orders/generate/ {material_ids?, supplier_overrides?} → 201
export interface GeneratedPurchaseOrders {
  created: { id: number; code: string; supplier: { id: number; name: string }; material: { id: number; sku: string; name: string }; orders: Ref[] }[];
  skipped: { material_id: number; reason: string }[];
}

// Order form (ADR 0025 B): GET /api/customers/ and GET /api/products/.
export interface Customer {
  id: number;
  name: string;
  ruc?: string | null;
}

export interface Product {
  id: number;
  code: string;
  name: string;
  brand?: { id: number; name: string } | null;
  image?: string | null;
}

// POST /api/orders/ and PATCH /api/orders/<id>/ (items replace the list).
export interface OrderInput {
  code?: string;
  customer: string;
  brand: string;
  promised_on: string;
  issued_on?: string;
  notes?: string;
  items: { product: string; quantity: number; color?: string; customization?: string; sizes?: Record<string, number> }[];
}
