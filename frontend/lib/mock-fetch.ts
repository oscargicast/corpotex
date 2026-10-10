// In-browser stand-in for the Django API while B1 is not on main.
// Enabled with NEXT_PUBLIC_USE_MOCKS=1. Shapes follow docs/backend/modelo-de-datos.md.
import badgesByRole from "@/mocks/badges.json";
import monitorSeed from "@/mocks/monitor.json";
import ordersSeed from "@/mocks/orders.json";
import purchaseOrdersSeed from "@/mocks/purchase-orders.json";
import users from "@/mocks/users.json";
import type {
  Badges,
  ClaudeStatus,
  Clock,
  Monitor,
  OrderDetail,
  OrderListItem,
  PurchaseOrderListItem,
  Role,
  User,
} from "./types";

const orders = structuredClone(ordersSeed.list) as OrderListItem[];
const orderDetails = structuredClone(ordersSeed.detail) as Record<string, Partial<OrderDetail>>;
const purchaseOrders = structuredClone(purchaseOrdersSeed) as PurchaseOrderListItem[];

// Same rule as the API serializers: production sees no prices, sales no breakdown.
function orderDetailFor(order: OrderListItem, role: Role): OrderDetail {
  const extra = orderDetails[order.id] ?? {};
  const detail: OrderDetail = {
    issued_on: order.promised_on,
    production_stage: null,
    owner: null,
    items: [],
    requirements: [],
    critical_path: [],
    redistributions: [],
    ...extra,
    ...order,
    purchase_orders: purchaseOrders.filter((po) => po.orders.some((o) => o.id === order.id)),
    alerts: monitor.alerts.filter((a) => a.order?.id === order.id),
  } as OrderDetail;
  if (role === "manager") detail.redistributions = monitor.redistributions.filter((d) => d.orders.some((o) => o.id === order.id));
  if (role === "production") {
    detail.total_amount = null;
    detail.items = detail.items.map((item) => ({ ...item, unit_price: null }));
    detail.purchase_orders = detail.purchase_orders.map((po) => ({ ...po, total_amount: null }));
  }
  if (role === "sales") detail.requirements = [];
  return detail;
}

function createOrder(body: Record<string, unknown>): Response {
  const code = String(body.code);
  const existing = orders.find((o) => o.code === code);
  if (existing) return json(200, existing); // idempotent by code, like the API
  const items = (body.items as { quantity: number }[]) ?? [];
  const customer = body.customer as { name: string };
  const order: OrderListItem = {
    id: Math.max(...orders.map((o) => o.id)) + 1,
    code,
    customer: { id: 90 + orders.length, name: customer.name },
    brand: { id: 9, name: String(body.brand) },
    status: "broken_down",
    status_display: "Desglosada",
    risk: "ok",
    risk_reason: "",
    promised_on: String(body.promised_on),
    estimated_on: null,
    slack_days: null,
    total_units: items.reduce((sum, item) => sum + item.quantity, 0),
    purchase_orders_summary: { total: 0, confirmed: 0, waiting_manager: 0 },
  };
  orders.unshift(order);
  return json(201, order);
}

const monitor = structuredClone(monitorSeed) as Monitor;

function monitorFor(role: Role): Monitor {
  const kpis = { ...monitor.kpis, pending_decisions: monitor.decisions.length, open_alerts: monitor.alerts.length };
  if (role === "manager") return { ...monitor, kpis };
  // Other roles: no decisions, prices or payments (the API filters them by role).
  return {
    ...monitor,
    kpis: { ...kpis, pending_decisions: null },
    decisions: [],
    redistributions: [],
    payments_by_supplier: undefined,
  };
}

function resolveDecision(id: number, action: string): Response {
  const decision = monitor.decisions.find((d) => d.id === id);
  if (!decision) return json(404, { detail: "No existe." });
  monitor.decisions = monitor.decisions.filter((d) => d.id !== id);
  const status = action === "approve" ? "approved" : action === "reject" ? "rejected" : "supplier_changed";
  const resolved = { ...decision, status, status_display: status };
  if (action === "approve" && decision.detail.cancelled) monitor.redistributions = [resolved, ...monitor.redistributions];
  return json(200, resolved);
}

const DISCONNECTED: ClaudeStatus = {
  connected: false,
  method: "none",
  subscription_type: null,
  expires_at: null,
  refresh_token_expires_at: null,
  expired: false,
  last_error: null,
};
let claude: ClaudeStatus = { ...DISCONNECTED };

function connectedStatus(method: ClaudeStatus["method"]): ClaudeStatus {
  const in30Days = new Date(Date.now() + 30 * 24 * 3600 * 1000).toISOString();
  return {
    connected: true,
    method,
    subscription_type: method === "oauth" ? "max" : null,
    expires_at: method === "oauth" ? new Date(Date.now() + 8 * 3600 * 1000).toISOString() : null,
    refresh_token_expires_at: method === "oauth" ? in30Days : null,
    expired: false,
    last_error: null,
  };
}

const clock = {
  realStart: Date.now(),
  simStart: new Date("2026-10-12T08:00:00-05:00").getTime(),
  factor: 60,
  paused: false,
};

function clockNow(): number {
  if (clock.paused) return clock.simStart;
  return clock.simStart + (Date.now() - clock.realStart) * clock.factor;
}

function rebase() {
  clock.simStart = clockNow();
  clock.realStart = Date.now();
}

function json(status: number, data?: unknown): Response {
  return new Response(data === undefined ? null : JSON.stringify(data), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function userFor(headers: Headers): User | null {
  const token = headers.get("Authorization")?.replace(/^Token /, "");
  const username = token?.replace(/^mock-/, "");
  return (users as User[]).find((u) => u.username === username) ?? null;
}

function readBody(body: BodyInit | null | undefined): Record<string, unknown> {
  return typeof body === "string" ? JSON.parse(body) : {};
}

export async function mockFetch(path: string, init: RequestInit & { headers: Headers }): Promise<Response> {
  const method = (init.method ?? "GET").toUpperCase();
  const route = `${method} ${path.split("?")[0]}`;

  if (route === "POST /api/auth/login/") {
    const { username, password } = readBody(init.body);
    const user = (users as User[]).find((u) => u.username === username);
    // Seed passwords equal the username (planning, open question 3).
    if (!user || password !== username) {
      return json(400, { non_field_errors: ["Unable to log in with provided credentials."] });
    }
    return json(200, { token: `mock-${user.username}`, user });
  }

  const user = userFor(init.headers);
  if (!user) return json(401, { detail: "Authentication credentials were not provided." });

  switch (route) {
    case "GET /api/auth/me/":
      return json(200, user);
    case "POST /api/auth/logout/":
      return json(204);
    case "GET /api/clock/":
      return json(200, { now: new Date(clockNow()).toISOString(), factor: clock.factor, paused: clock.paused } satisfies Clock);
    case "PATCH /api/clock/": {
      if (user.role !== "manager") return json(403, { detail: "Solo el Gerente." });
      const { factor, paused, advance_hours } = readBody(init.body);
      rebase();
      if (typeof factor === "number") clock.factor = factor;
      if (typeof paused === "boolean") clock.paused = paused;
      if (typeof advance_hours === "number") clock.simStart += advance_hours * 3_600_000;
      return json(200, { now: new Date(clockNow()).toISOString(), factor: clock.factor, paused: clock.paused } satisfies Clock);
    }
    case "GET /api/me/badges/":
      return json(200, (badgesByRole as Record<Role, Badges>)[user.role]);
  }

  if (route === "GET /api/monitor/") return json(200, monitorFor(user.role));

  if (route === "GET /api/orders/") {
    const params = new URL(path, "http://mock").searchParams;
    const filtered = orders.filter(
      (o) =>
        (!params.get("status") || o.status === params.get("status")) &&
        (!params.get("risk") || o.risk === params.get("risk")) &&
        (!params.get("brand") || String(o.brand.id) === params.get("brand")) &&
        (!params.get("code") || o.code === params.get("code")),
    );
    return json(200, filtered);
  }
  if (route === "POST /api/orders/") {
    if (user.role === "production") return json(403, { detail: "Solo Comercial y Gerente." });
    return createOrder(readBody(init.body));
  }
  const orderMatch = route.match(/^GET \/api\/orders\/(\d+)\/$/);
  if (orderMatch) {
    const order = orders.find((o) => o.id === Number(orderMatch[1]));
    return order ? json(200, orderDetailFor(order, user.role)) : json(404, { detail: "No existe." });
  }
  const confirmMatch = route.match(/^POST \/api\/orders\/(\d+)\/confirm\/$/);
  if (confirmMatch) {
    if (user.role === "sales") return json(403, { detail: "Solo Producción y Gerente." });
    const order = orders.find((o) => o.id === Number(confirmMatch[1]));
    if (!order) return json(404, { detail: "No existe." });
    Object.assign(order, { status: "confirmed", status_display: "Confirmada" });
    return json(200, orderDetailFor(order, user.role));
  }
  const decisionMatch = route.match(/^POST \/api\/manager\/decisions\/(\d+)\/$/);
  if (decisionMatch) {
    if (user.role !== "manager") return json(403, { detail: "Solo el Gerente." });
    return resolveDecision(Number(decisionMatch[1]), String(readBody(init.body).action));
  }
  const alertMatch = route.match(/^POST \/api\/alerts\/(\d+)\/acknowledge\/$/);
  if (alertMatch) {
    monitor.alerts = monitor.alerts.filter((a) => a.id !== Number(alertMatch[1]));
    return json(200, { id: Number(alertMatch[1]), status: "acknowledged" });
  }

  if (path.startsWith("/api/settings/claude/") && user.role !== "manager") {
    return json(403, { detail: "Solo el Gerente." });
  }
  switch (route) {
    case "GET /api/settings/claude/status/":
      return json(200, claude);
    case "POST /api/settings/claude/start/":
      return json(200, { url: "about:blank#mock-claude-oauth", state: "mock-verifier" });
    case "POST /api/settings/claude/exchange/": {
      const code = String(readBody(init.body).code ?? "");
      if (!code.includes("#")) return json(400, { error_code: "missing_state", detail: "missing state" });
      if (code.startsWith("bad")) return json(400, { error_code: "invalid_code", detail: "invalid_grant" });
      claude = connectedStatus("oauth");
      return json(200, claude);
    }
    case "POST /api/settings/claude/set-key/": {
      const key = String(readBody(init.body).api_key ?? "");
      if (!key.startsWith("sk-ant-")) return json(400, { error_code: "key_format", detail: "invalid api key format" });
      claude = connectedStatus("api_key");
      return json(200, claude);
    }
    case "POST /api/settings/claude/disconnect/":
      claude = { ...DISCONNECTED };
      return json(200, claude);
  }
  return json(404, { detail: `mock: ${route} not implemented` });
}
