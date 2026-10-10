// Base types for F1. F2.1 replaces them with types generated from docs/api/openapi.json.

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

export interface Clock {
  now: string;
  factor: number | string; // Decimal in the API
  paused: boolean;
}

export interface Badges {
  assistant_unread: number;
  latest_unread: { id: number; preview: string; alert_kind: string | null } | null;
  claude_ok: boolean;
  // Manager only; null for the other roles.
  pending_decisions: number | null;
  orders_in_danger: number | null;
  claude_expired: boolean | null;
  claude_last_error: string | null;
  claude_refresh_expires_at: string | null;
}

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

export interface Payment {
  id: number;
  kind: "advance" | "balance";
  kind_display: string;
  amount: string;
  status: "pending" | "paid";
  due_on: string | null;
  paid_at: string | null;
  method: "yape" | "transfer" | "cash" | null;
  receipt: string | null;
}

export interface ProgressReport {
  id: number;
  units_done: number;
  note: string;
  photo: string | null;
  source: "whatsapp" | "web" | "manual" | "simulator";
  reported_at: string;
}

export interface ChatMessage {
  id: number;
  direction: "inbound" | "outbound";
  author: "supplier" | "agent" | "manager" | "system";
  text: string;
  media: string | null;
  media_kind?: "image" | "audio" | "document" | null; // not in the API yet
  sent_at: string;
}

export interface PurchaseOrderDetail extends PurchaseOrderListItem {
  rationale: string | null;
  scores: Record<string, number> | null;
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
  redistributed_into: (Ref & { supplier_name: string; quantity: number; status_display: string })[];
  rating: { delay_days: number; quality: number; defect_pct: number; score: number; rated_at: string } | null;
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
  on_time_score: number | null; // 0 to 1
  quality_score: number | null; // 1 to 5
  open_purchase_orders: number;
  numbers_count: number;
  active_numbers_count: number;
  source: "registered" | "self_registered" | "external";
  source_display: string;
  status: "active" | "pending_review" | "inactive";
  status_display: string;
  is_in_house: boolean;
}

export interface SupplierNumber {
  id: number;
  phone: string;
  name: string;
  active: boolean;
  simulated?: boolean; // answered through the simulator, not WhatsApp
}

export interface SupplierDetail extends SupplierListItem {
  notes: string;
  follow_up_every_hours: number;
  source_detail: { url: string; excerpt: string } | null;
  numbers: SupplierNumber[];
  rates: { id: number; item_name: string; unit_price: string; currency: Currency; valid_from: string }[];
  ratings: { purchase_order_code: string; delay_days: number; quality: number; defect_pct: number; score: number; rated_at: string }[];
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

export interface OrderDetail extends OrderListItem {
  issued_on: string;
  production_stage: string | null;
  owner: { id: number; first_name: string } | null;
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

export interface Candidate {
  supplier: { id: number; name: string };
  score: number;
  scores: Record<string, number>; // on_time, price, load, quality: 0 to 1
  unit_price: string;
  load_pct: number;
  rationale: string;
}

export interface ProposalItem {
  purchase_order: Ref | null;
  supplier: { id: number; name: string };
  quantity: number;
  unit_price: string;
  currency: Currency;
  rationale: string;
  candidates: Candidate[];
}

export interface Snapshot {
  estimated_on: string;
  total_amount: string;
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
    cancelled?: { code: string; supplier_name: string; quantity: number; units_done: number };
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
  kpis: {
    orders_in_danger: number;
    orders_at_risk: number;
    stalled_purchase_orders: number;
    pending_decisions: number | null;
    open_alerts: number;
  };
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

export interface AssistantMessage {
  id: number;
  role: "user" | "assistant";
  text: string;
  action: AssistantAction | null;
  created_at: string;
}

// Inventory (F2.6): stock, reserved by open orders, and what is left.
export interface Material {
  id: number;
  sku: string;
  name: string;
  kind: "fabric" | "button" | "zipper" | "collar_cuff" | "other";
  kind_display?: string;
  unit: "m" | "kg" | "unit";
  stock: string | number;
  committed: string | number;
  available: string | number;
  image: string | null;
}

export interface MaterialDetail extends Material {
  requirements: {
    order_id?: number;
    order_code: string;
    qty_needed: string | number;
    qty_from_stock: string | number;
    qty_to_order: string | number;
    status: string;
    status_display?: string;
  }[];
}

// Onboarding (ADR 0011, 0019) and style history.
export type StyleSupplierStatus = "pending" | "reading" | "analyzing" | "done" | "no_phone" | "no_chat" | "not_allowed" | "error";

export interface StyleState {
  status: "not_started" | "extracting" | "draft" | "approved" | "error";
  status_display: string;
  error: string;
  since: string | null;
  step: "suppliers" | "merging" | null;
  suppliers: { id: number; name: string; status: StyleSupplierStatus; messages_read: number | null; error: string }[];
  style_md: string;
  notes: { supplier_id: number; supplier_name: string; notes: string }[];
  approved_at: string | null;
}

export interface StyleVersion {
  id: number;
  source: "onboarding" | "daily" | "template" | "manual" | "rollback";
  source_display: string;
  changelog: string;
  created_at: string;
}

export interface StyleVersionDetail extends StyleVersion {
  style_md: string;
  notes_snapshot: Record<string, string>;
}

export interface WhatsAppState {
  state: string; // open | connecting | close
  webhook: { url: string; events: string[]; base64: boolean } | null;
  settings: Record<string, unknown> | null;
  offline: boolean;
  done_at: string | null;
}

// Routes (ADR 0024): straight lines between stops, no routing service.
export interface RouteStop {
  position: number;
  kind: "pickup" | "delivery";
  name: string;
  address: string;
  lat: number;
  lng: number;
  eta: string | null;
  supplier?: { id: number; name: string } | null;
  customer?: { id: number; name: string } | null;
  purchase_order?: Ref | null;
  order?: Ref | null;
}

export interface Route {
  id: number;
  date: string;
  status: "proposed" | "planned" | "in_progress" | "completed" | "replaced" | "discarded";
  distance_km: string | number;
  duration_min: number;
  path: { type: "LineString"; coordinates: [number, number][] } | null; // [lng, lat]
  recalculated_from: number | null;
  stops: RouteStop[];
}

// Simulator (ADR 0017 demo decision: one real supplier on WhatsApp, the rest here).
export interface SimulatorContact {
  allowed_number_id: number;
  name: string; // the number's label ("Simulador", "dueña"); the supplier name is in supplier.name
  supplier: { id: number; name: string } | null;
  conversation_id: number | null;
  channel: "simulator" | "whatsapp";
  simulated?: boolean;
  last_message: { id: number; text: string; direction: "inbound" | "outbound"; sent_at: string } | null;
}

export interface AssistantContext {
  path: string;
  view: string;
  id?: number;
}

// /api/settings/claude/* (ADR 0022). The credential itself never reaches the browser.
export interface ClaudeStatus {
  connected: boolean;
  method: "oauth" | "api_key" | "none";
  subscription_type: string | null;
  expires_at: string | null;
  refresh_token_expires_at: string | null;
  expired: boolean;
  last_error: string | null;
}

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
