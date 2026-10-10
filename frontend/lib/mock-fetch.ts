// In-browser stand-in for the Django API while B1 is not on main.
// Enabled with NEXT_PUBLIC_USE_MOCKS=1. Shapes follow docs/backend/modelo-de-datos.md.
import badgesByRole from "@/mocks/badges.json";
import conversationsSeed from "@/mocks/conversations.json";
import monitorSeed from "@/mocks/monitor.json";
import ordersSeed from "@/mocks/orders.json";
import poDetailsSeed from "@/mocks/purchase-order-details.json";
import purchaseOrdersSeed from "@/mocks/purchase-orders.json";
import routesSeed from "@/mocks/routes.json";
import simulatorContactsSeed from "@/mocks/simulator-contacts.json";
import suppliersSeed from "@/mocks/suppliers.json";
import users from "@/mocks/users.json";
import type {
  AssistantMessage,
  Badges,
  ChatMessage,
  ClaudeStatus,
  Clock,
  Monitor,
  OrderDetail,
  OrderListItem,
  PurchaseOrderDetail,
  PurchaseOrderListItem,
  Role,
  Route,
  SimulatorContact,
  SupplierDetail,
  SupplierListItem,
  User,
} from "./types";

const poDetails = structuredClone(poDetailsSeed) as Record<string, Partial<PurchaseOrderDetail> & { decision_id?: number }>;
const conversations = structuredClone(conversationsSeed) as Record<string, ChatMessage[]>;

function purchaseOrderDetailFor(po: PurchaseOrderListItem, role: Role): PurchaseOrderDetail {
  const extra = poDetails[po.id] ?? {};
  const detail = {
    rationale: null,
    scores: null,
    candidates: null,
    changed_by_manager: false,
    terms: "",
    delivered_on: null,
    items: [],
    progress_reports: [],
    payments: [],
    paid_amount: "0.00",
    pending_amount: "0.00",
    conversation_id: null,
    redistributed_into: [],
    rating: null,
    ...extra,
    ...po,
    suggested_supplier: null,
    pending_decision: monitor.decisions.find((d) => d.purchase_orders.some((p) => p.id === po.id)) ?? null,
  } as PurchaseOrderDetail;
  if (role !== "manager") {
    // Team members see the supplier's name, never prices, payments or the matching scores.
    Object.assign(detail, { total_amount: null, payments: [], paid_amount: null, pending_amount: null, rationale: null, scores: null, candidates: null, pending_decision: null });
    detail.items = detail.items.map((item) => ({ ...item, unit_price: null }));
  }
  return detail;
}

const suppliers = structuredClone(suppliersSeed.list) as SupplierListItem[];
const supplierDetails = structuredClone(suppliersSeed.detail) as Record<string, Partial<SupplierDetail>>;

function supplierDetailFor(supplier: SupplierListItem): SupplierDetail {
  const extra = (supplierDetails[supplier.id] ??= {});
  const numbers = extra.numbers ?? [];
  return {
    notes: "",
    follow_up_every_hours: 48,
    source_detail: null,
    rates: [],
    ratings: [],
    payments_summary: [],
    ...extra,
    ...supplier,
    numbers,
    numbers_count: numbers.length || supplier.numbers_count,
    active_numbers_count: numbers.length ? numbers.filter((n) => n.active).length : supplier.active_numbers_count,
    purchase_orders: purchaseOrders.filter((po) => po.supplier.id === supplier.id),
  } as SupplierDetail;
}

function supplierRoutes(route: string, body: BodyInit | null | undefined): Response | null {
  if (route === "GET /api/suppliers/" || route.startsWith("GET /api/suppliers/?")) return null;
  let match = route.match(/^GET \/api\/suppliers\/(\d+)\/$/);
  const find = (id: string) => suppliers.find((s) => s.id === Number(id));
  if (match) {
    const supplier = find(match[1]);
    return supplier ? json(200, supplierDetailFor(supplier)) : json(404, { detail: "No existe." });
  }
  match = route.match(/^PATCH \/api\/suppliers\/(\d+)\/$/);
  if (match) {
    const supplier = find(match[1]);
    if (!supplier) return json(404, { detail: "No existe." });
    const patch = readBody(body);
    if (patch.status) {
      supplier.status = patch.status as SupplierListItem["status"];
      supplier.status_display = patch.status === "active" ? "Activo" : patch.status === "inactive" ? "Inactivo" : "Por revisar";
    }
    if (typeof patch.notes === "string") (supplierDetails[supplier.id] ??= {}).notes = patch.notes;
    return json(200, supplierDetailFor(supplier));
  }
  match = route.match(/^POST \/api\/suppliers\/(\d+)\/numbers\/$/);
  if (match) {
    const supplier = find(match[1]);
    if (!supplier) return json(404, { detail: "No existe." });
    const { phone, name } = readBody(body);
    const detail = (supplierDetails[supplier.id] ??= {});
    const number = { id: Date.now(), phone: String(phone), name: String(name ?? ""), active: false };
    detail.numbers = [...(detail.numbers ?? []), number];
    return json(201, number);
  }
  match = route.match(/^PATCH \/api\/suppliers\/(\d+)\/numbers\/(\d+)\/$/);
  if (match) {
    const number = supplierDetails[match[1]]?.numbers?.find((n) => n.id === Number(match![2]));
    if (!number) return json(404, { detail: "No existe." });
    Object.assign(number, readBody(body));
    return json(200, number);
  }
  return null;
}

// Simulator: the operator writes as the supplier; the "agent" answers after 2 s.
const simulatorContacts = structuredClone(simulatorContactsSeed) as SimulatorContact[];
const agentQueue: { conversationId: number; at: number; message: ChatMessage }[] = [];

function flushAgentQueue() {
  const now = Date.now();
  for (const item of agentQueue.filter((q) => q.at <= now)) {
    (conversations[item.conversationId] ??= []).push(item.message);
  }
  for (let i = agentQueue.length - 1; i >= 0; i--) if (agentQueue[i].at <= now) agentQueue.splice(i, 1);
}

function nextMessageId(): number {
  const all = Object.values(conversations).flat();
  return Math.max(1000, ...all.map((m) => m.id), ...agentQueue.map((q) => q.message.id)) + 1;
}

function agentSays(conversationId: number, text: string, delayMs: number) {
  agentQueue.push({
    conversationId,
    at: Date.now() + delayMs,
    message: { id: nextMessageId(), direction: "outbound", author: "agent", text, media: null, media_kind: null, sent_at: new Date(Date.now() + delayMs).toISOString() },
  });
}

function simulatorPost(body: BodyInit | null | undefined): Response {
  const get = (key: string) => (body instanceof FormData ? body.get(key) : readBody(body)[key]);
  const contact = simulatorContacts.find((c) => c.id === Number(get("allowed_number_id")));
  if (!contact) return json(400, { detail: "Número no permitido." });
  if (contact.channel !== "simulator") return json(400, { detail: "Ese contacto escribe por WhatsApp real." });
  contact.conversation_id ??= 100 + contact.id;
  const photo = get("photo");
  const text = String(get("text") ?? "");
  const message: ChatMessage = {
    id: nextMessageId(),
    direction: "inbound",
    author: "supplier",
    text,
    media: photo instanceof File && photo.size ? URL.createObjectURL(photo) : typeof photo === "string" && photo ? photo : null,
    media_kind: photo ? "image" : null,
    sent_at: new Date().toISOString(),
  };
  (conversations[contact.conversation_id] ??= []).push(message);
  if (/no (voy a|puedo)|cancel/i.test(text)) {
    agentSays(contact.conversation_id, "Entendido, gracias por avisar a tiempo. Coordino con el Gerente y te confirmo cómo recogemos lo que ya tienes.", 2000);
    // The redistribution reaches another workshop: shows the highlight and the toast.
    const other = simulatorContacts.find((c) => c.channel === "simulator" && c.id !== contact.id);
    if (other) {
      other.conversation_id ??= 100 + other.id;
      agentSays(other.conversation_id, "Hola, ¿puedes tomar 250 polos piqué para el 20 oct. a S/ 8.10 c/u? Va con 50 % de adelanto.", 6000);
    }
  } else {
    agentSays(contact.conversation_id, message.media ? "¡Gracias por la foto! Lo registro en el pedido." : "Anotado, gracias.", 2000);
  }
  return json(201, { ...message, conversation_id: contact.conversation_id });
}

// Assistant: one thread per user, with a scripted reply after 1.5 s.
const assistantThreads: Record<string, { messages: AssistantMessage[]; replyAt: number | null; pendingReply: AssistantMessage[] }> = {};

function assistantThread(user: User) {
  if (!assistantThreads[user.username]) {
    const notice: AssistantMessage[] =
      user.role === "production"
        ? []
        : [
            {
              id: 1,
              role: "assistant",
              text:
                user.role === "manager"
                  ? "Taller Sullana canceló PT-0001 con 400 de 1000 hechas. Propongo repartir 600 entre dos talleres; la orden CP-2026-0001 pasa al 27 oct."
                  : "La orden CP-2026-0001 de Caja Piura está en peligro: la fecha estimada pasó del 24 al 27 oct.",
              action: {
                kind: "alert",
                alert_ids: [31],
                alerts: [{ id: 31, kind: "order_in_danger", kind_display: "Orden en peligro", severity: "critical", order: { id: 1, code: "CP-2026-0001" }, purchase_order: null }],
              },
              created_at: new Date(Date.now() - 600_000).toISOString(),
            },
          ];
    assistantThreads[user.username] = { messages: notice, replyAt: null, pendingReply: [] };
  }
  return assistantThreads[user.username];
}

function scriptedReply(text: string, nextId: number): AssistantMessage[] {
  const now = new Date().toISOString();
  const say = (body: string, extra: Partial<AssistantMessage> = {}): AssistantMessage => ({ id: nextId++, role: "assistant", text: body, action: null, created_at: now, ...extra });
  // No \b here: in JS regexes "í" is not a word character.
  if (/^s[ií]\s*[.!]?$/i.test(text.trim())) {
    return [
      say("Aprobé la redistribución", {
        action: { kind: "tool", tool: "resolve_decision", status: "done", title: "Aprobé la redistribución de CP-2026-0001", summary: "PT-0004 (350) y PT-0005 (250) quedan aprobados; el agente les escribe para acordar fecha.", links: [{ kind: "purchase_order", id: 7, code: "PT-0004" }, { kind: "purchase_order", id: 8, code: "PT-0005" }] },
      }),
      say("Listo. Te aviso cuando los dos talleres confirmen fecha."),
    ];
  }
  if (/^no\b/i.test(text)) return [say("Entendido, no cambio nada.")];
  if (/aprueb|redistrib/i.test(text)) return [say("¿Apruebo la redistribución de PT-0004 y PT-0005 para CP-2026-0001? (sí/no)")];
  if (/pendiente/i.test(text)) {
    return [
      say(
        "Tienes **2 decisiones**:\n\n- Redistribución de CP-2026-0001: 600 polos entre PT-0004 y PT-0005.\n- Precio de PI-0003: piden S/ 21.00 por kg, referencia S/ 19.50.\n\n| Orden | Cliente | Estimada |\n|---|---|---|\n| CP-2026-0001 | Caja Piura | 27 oct |\n| CP-2026-0002 | Colegio San José | 26 oct |",
      ),
    ];
  }
  return [say("Entendido. (Respuesta de prueba: el asistente real llega con el backend.)")];
}

function formValue(body: BodyInit | null | undefined, key: string): FormDataEntryValue | null {
  return body instanceof FormData ? body.get(key) : null;
}

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
  const customer = String(body.customer);
  const order: OrderListItem = {
    id: Math.max(...orders.map((o) => o.id)) + 1,
    code,
    customer: { id: 90 + orders.length, name: customer },
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
const routes = structuredClone(routesSeed) as Record<string, Route>;

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
  // Approving the redistribution swaps the routes; rejecting discards the proposal.
  const before = decision.detail.before?.route_id;
  const after = decision.detail.after?.route_id;
  if (after && routes[after]) routes[after].status = action === "reject" ? "discarded" : "planned";
  if (before && routes[before] && action !== "reject") routes[before].status = "replaced";
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
  if (path.startsWith("/api/assistant/")) {
    const thread = assistantThread(user);
    if (thread.replyAt && Date.now() >= thread.replyAt) {
      thread.messages.push(...thread.pendingReply);
      thread.replyAt = null;
      thread.pendingReply = [];
    }
    if (route === "GET /api/assistant/messages/") {
      const after = Number(new URL(path, "http://mock").searchParams.get("after") ?? 0);
      return json(200, { typing: thread.replyAt !== null, messages: thread.messages.filter((m) => m.id > after) });
    }
    if (route === "POST /api/assistant/messages/") {
      const text = String(readBody(init.body).text ?? "");
      const nextId = (thread.messages.at(-1)?.id ?? 0) + 1;
      const mine: AssistantMessage = { id: nextId, role: "user", text, action: null, created_at: new Date().toISOString() };
      thread.messages.push(mine);
      thread.pendingReply = scriptedReply(text, nextId + 1);
      thread.replyAt = Date.now() + 1500;
      return json(201, mine);
    }
    if (route === "POST /api/assistant/messages/read/") return json(200, { ok: true });
  }
  if (path.startsWith("/api/suppliers/")) {
    if (user.role !== "manager") return json(403, { detail: "Solo el Gerente." });
    if (route === "GET /api/suppliers/") {
      const status = new URL(path, "http://mock").searchParams.get("status");
      const list = suppliers.filter((s) => (status ? s.status === status : s.status !== "pending_review"));
      return json(200, list.map((s) => ({ ...s, ...(supplierDetails[s.id]?.numbers && { numbers_count: supplierDetailFor(s).numbers_count, active_numbers_count: supplierDetailFor(s).active_numbers_count }) })));
    }
    const handled = supplierRoutes(route, init.body);
    if (handled) return handled;
  }
  if (route === "GET /api/purchase-orders/") {
    const params = new URL(path, "http://mock").searchParams;
    return json(
      200,
      purchaseOrders
        .filter(
          (po) =>
            (!params.get("kind") || po.kind === params.get("kind")) &&
            (!params.get("waiting_manager") || po.waiting_manager) &&
            (!params.get("code") || po.code === params.get("code")),
        )
        .map((po) => (user.role === "manager" ? po : { ...po, total_amount: null })),
    );
  }
  const poMatch = route.match(/^GET \/api\/purchase-orders\/(\d+)\/$/);
  if (poMatch) {
    const po = purchaseOrders.find((p) => p.id === Number(poMatch[1]));
    return po ? json(200, purchaseOrderDetailFor(po, user.role)) : json(404, { detail: "No existe." });
  }
  const progressMatch = route.match(/^POST \/api\/purchase-orders\/(\d+)\/progress\/$/);
  if (progressMatch) {
    if (user.role === "sales") return json(403, { detail: "Solo Producción y Gerente." });
    const po = purchaseOrders.find((p) => p.id === Number(progressMatch[1]));
    if (!po) return json(404, { detail: "No existe." });
    const units = Number(formValue(init.body, "units_done"));
    const photo = formValue(init.body, "photo");
    const reports = (poDetails[po.id] ??= {}).progress_reports ?? [];
    poDetails[po.id].progress_reports = [
      {
        id: Date.now(),
        units_done: units,
        note: String(formValue(init.body, "note") ?? ""),
        photo: photo instanceof File && photo.size ? URL.createObjectURL(photo) : null,
        source: "web",
        reported_at: new Date().toISOString(),
      },
      ...reports,
    ];
    Object.assign(po, { units_done: units, progress_pct: Math.round((units / Number(po.total_units)) * 100), last_progress_at: new Date().toISOString() });
    return json(201, poDetails[po.id].progress_reports![0]);
  }
  const payMatch = route.match(/^POST \/api\/payments\/(\d+)\/pay\/$/);
  if (payMatch) {
    if (user.role !== "manager") return json(403, { detail: "Solo el Gerente." });
    for (const detail of Object.values(poDetails)) {
      const payment = detail.payments?.find((p) => p.id === Number(payMatch[1]));
      if (!payment) continue;
      Object.assign(payment, { status: "paid", paid_at: new Date().toISOString(), method: String(formValue(init.body, "method")) });
      const paid = detail.payments!.filter((p) => p.status === "paid").reduce((sum, p) => sum + Number(p.amount), 0);
      const total = detail.payments!.reduce((sum, p) => sum + Number(p.amount), 0);
      detail.paid_amount = paid.toFixed(2);
      detail.pending_amount = (total - paid).toFixed(2);
      return json(200, payment);
    }
    return json(404, { detail: "No existe." });
  }
  flushAgentQueue();
  if (route === "GET /api/routes/") {
    const all = Object.values(routes);
    const current = all.find((r) => r.status === "planned" || r.status === "in_progress") ?? null;
    const replaced = current?.recalculated_from ? routes[current.recalculated_from] ?? null : null;
    return json(200, { current, replaced });
  }
  const routeMatch = route.match(/^GET \/api\/routes\/(\d+)\/$/);
  if (routeMatch) return routes[routeMatch[1]] ? json(200, routes[routeMatch[1]]) : json(404, { detail: "No existe." });
  if (route === "GET /api/simulator/contacts/") {
    return json(
      200,
      simulatorContacts.map((c) => {
        const last = c.conversation_id ? conversations[c.conversation_id]?.at(-1) : undefined;
        return { ...c, last_message: last ? { id: last.id, text: last.text, direction: last.direction, sent_at: last.sent_at } : null };
      }),
    );
  }
  if (route === "POST /api/simulator/messages/") return simulatorPost(init.body);
  const messagesMatch = route.match(/^GET \/api\/conversations\/(\d+)\/messages\/$/);
  if (messagesMatch) {
    const after = Number(new URL(path, "http://mock").searchParams.get("after") ?? 0);
    const messages = (conversations[messagesMatch[1]] ?? []).filter((m) => m.id > after);
    const typing = agentQueue.some((q) => q.conversationId === Number(messagesMatch[1]) && q.at - Date.now() < 2500);
    return json(200, { typing, messages });
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
