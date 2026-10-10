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
  factor: number;
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
  total_units: number;
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
  total_units: number;
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
