// In-browser stand-in for the Django API while B1 is not on main.
// Enabled with NEXT_PUBLIC_USE_MOCKS=1. Shapes follow docs/backend/modelo-de-datos.md.
import badgesByRole from "@/mocks/badges.json";
import conversationsSeed from "@/mocks/conversations.json";
import customersSeed from "@/mocks/customers.json";
import materialsSeed from "@/mocks/materials.json";
import monitorSeed from "@/mocks/monitor.json";
import ordersSeed from "@/mocks/orders.json";
import pendingSeed from "@/mocks/pending-requirements.json";
import poDetailsSeed from "@/mocks/purchase-order-details.json";
import productsSeed from "@/mocks/products.json";
import purchaseOrdersSeed from "@/mocks/purchase-orders.json";
import routesSeed from "@/mocks/routes.json";
import simulatorContactsSeed from "@/mocks/simulator-contacts.json";
import styleSeed from "@/mocks/style.json";
import suppliersSeed from "@/mocks/suppliers.json";
import users from "@/mocks/users.json";
import type {
  AssistantMessage,
  Badges,
  ChatMessage,
  ClaudeStatus,
  Clock,
  Customer,
  GeneratedPurchaseOrders,
  MaterialDetail,
  Monitor,
  OrderDetail,
  OrderItem,
  OrderListItem,
  PendingRequirement,
  Product,
  PurchaseOrderDetail,
  PurchaseOrderListItem,
  Role,
  Route,
  SimulatorContact,
  StyleState,
  StyleVersionDetail,
  SupplierDetail,
  SupplierListItem,
  User,
  WhatsAppState,
} from "./types";

const poDetails = structuredClone(poDetailsSeed) as unknown as Record<string, Partial<PurchaseOrderDetail> & { decision_id?: number }>;
const conversations = structuredClone(conversationsSeed) as unknown as Record<string, ChatMessage[]>;

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
    status_history: [],
    ...extra,
    ...po,
    suggested_supplier: null,
    pending_decision: monitor.decisions.find((d) => d.purchase_orders.some((p) => p.id === po.id)) ?? null,
  } as PurchaseOrderDetail;
  if (role !== "manager") {
    // Team members see the supplier's name, never prices, payments, the matching scores or the chat.
    Object.assign(detail, { total_amount: null, payments: [], paid_amount: null, pending_amount: null, rationale: null, scores: null, candidates: null, pending_decision: null, conversation_id: null });
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

function createSupplier(body: Record<string, unknown>, source: "registered" | "self_registered"): Response {
  const name = String(body.name ?? "").trim();
  if (!name) return json(400, { name: ["Este campo es requerido."] });
  const supplier: SupplierListItem = {
    id: Math.max(...suppliers.map((s) => s.id)) + 1,
    name,
    kind: (body.kind as SupplierListItem["kind"]) ?? "workshop",
    kind_display: body.kind === "materials" ? "Insumos" : body.kind === "finished" ? "Terminado" : "Taller",
    specialties: Array.isArray(body.specialties) ? (body.specialties as string[]) : String(body.specialties ?? "").split(";").map((x) => x.trim()).filter(Boolean),
    city: String(body.city ?? ""),
    weekly_capacity: body.weekly_capacity ? Number(body.weekly_capacity) : null,
    lead_time_days: body.lead_time_days ? Number(body.lead_time_days) : null,
    currency: (body.currency as SupplierListItem["currency"]) ?? "PEN",
    load_pct: null,
    on_time_score: null,
    quality_score: null,
    open_purchase_orders: 0,
    numbers_count: body.phone ? 1 : 0,
    active_numbers_count: 0,
    source,
    source_display: source === "self_registered" ? "Autoregistro" : "Registrado",
    status: source === "self_registered" ? "pending_review" : "active",
    status_display: source === "self_registered" ? "Por revisar" : "Activo",
    is_in_house: false,
  };
  suppliers.push(supplier);
  if (body.phone) supplierDetails[supplier.id] = { numbers: [{ id: Date.now(), phone: String(body.phone), name: "", active: false }] };
  return json(201, supplier);
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

// Style onboarding: an extraction walks through reading, analyzing and merging in ~8 s.
const style = structuredClone(styleSeed) as {
  state: StyleState;
  versions: StyleVersionDetail[];
  whatsapp: WhatsAppState;
};
let extractionStartedAt: number | null = null;

function styleState(): StyleState {
  const s = style.state;
  if (extractionStartedAt === null) return s;
  const t = Date.now() - extractionStartedAt;
  const withPhone = s.suppliers.filter((p) => !["no_phone", "not_allowed"].includes(p.status));
  if (t < 3000) {
    withPhone.forEach((p, i) => Object.assign(p, { status: t > 1000 * (i + 1) ? "analyzing" : "reading", messages_read: Math.round(t / 100) }));
    return { ...s, status: "extracting", status_display: "Extrayendo", step: "suppliers" };
  }
  withPhone.forEach((p) => (p.status = "done"));
  if (t < 8000) return { ...s, status: "extracting", status_display: "Extrayendo", step: "merging" };
  extractionStartedAt = null;
  Object.assign(s, { status: "draft", status_display: "Borrador", step: null });
  return s;
}

function styleRoutes(route: string, body: BodyInit | null | undefined): Response | null {
  const busy = () => json(409, { detail: "Hay una extracción en curso." });
  switch (route) {
    case "GET /api/onboarding/style/":
      return json(200, styleState());
    case "PUT /api/onboarding/style/": {
      if (styleState().status === "extracting") return busy();
      const { style_md, notes } = readBody(body) as { style_md: string; notes?: StyleState["notes"] };
      style.state.style_md = style_md;
      if (notes) style.state.notes = style.state.notes.map((n) => ({ ...n, notes: notes.find((x) => x.supplier_id === n.supplier_id)?.notes ?? n.notes }));
      Object.assign(style.state, { status: "draft", status_display: "Borrador" });
      return json(200, style.state);
    }
    case "POST /api/onboarding/style/extract/":
    case "POST /api/onboarding/style/import-txt/": {
      if (styleState().status === "extracting") return busy();
      const since = body instanceof FormData ? body.get("since") : readBody(body).since;
      if (!since) return json(400, { detail: "Falta la fecha desde la que se lee." });
      style.state.since = String(since);
      extractionStartedAt = Date.now();
      return json(202, styleState());
    }
    case "POST /api/onboarding/style/template/":
      Object.assign(style.state, { style_md: "## Resumen\n\nPerfil base escrito desde la entrevista a Corpotex.\n", status: "draft", status_display: "Borrador" });
      return json(200, style.state);
    case "POST /api/onboarding/style/approve/": {
      const now = new Date().toISOString();
      Object.assign(style.state, { status: "approved", status_display: "Aprobado", approved_at: now });
      style.versions.unshift({ id: Math.max(...style.versions.map((v) => v.id)) + 1, source: "onboarding", source_display: "Onboarding", changelog: "Aprobado desde el onboarding.", created_at: now, style_md: style.state.style_md, notes_snapshot: {} });
      return json(200, style.state);
    }
    case "GET /api/style/versions/":
      return json(200, style.versions.map(({ style_md: _md, notes_snapshot: _n, ...v }) => v));
    case "GET /api/onboarding/whatsapp/":
      return json(200, style.whatsapp);
    case "POST /api/onboarding/whatsapp/qr/":
      return json(200, { qr_base64: style.whatsapp.state === "open" ? null : "" });
    case "POST /api/onboarding/whatsapp/webhook/":
      return json(200, style.whatsapp);
  }
  let match = route.match(/^GET \/api\/style\/versions\/(\d+)\/$/);
  if (match) {
    const version = style.versions.find((v) => v.id === Number(match![1]));
    return version ? json(200, version) : json(404, { detail: "No existe." });
  }
  match = route.match(/^POST \/api\/style\/versions\/(\d+)\/restore\/$/);
  if (match) {
    const version = style.versions.find((v) => v.id === Number(match![1]));
    if (!version) return json(404, { detail: "No existe." });
    const restored = { ...version, id: Math.max(...style.versions.map((v) => v.id)) + 1, source: "rollback" as const, source_display: "Vuelta atrás", changelog: `Volví a la versión del ${new Date(version.created_at).toLocaleDateString("es-PE")}.`, created_at: new Date().toISOString() };
    style.versions.unshift(restored);
    return json(201, restored);
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
    message: { id: nextMessageId(), direction: "outbound", author: "agent", text, media: null, media_kind: null, status: "sent", turn_id: null, sent_at: new Date(Date.now() + delayMs).toISOString() },
  });
}

function simulatorPost(body: BodyInit | null | undefined): Response {
  const get = (key: string) => (body instanceof FormData ? body.get(key) : readBody(body)[key]);
  const contact = simulatorContacts.find((c) => c.allowed_number_id === Number(get("allowed_number_id")));
  if (!contact) return json(400, { detail: "Número no permitido." });
  if (contact.channel !== "simulator") return json(400, { detail: "Ese contacto escribe por WhatsApp real." });
  contact.conversation_id ??= 100 + contact.allowed_number_id;
  const photo = get("photo");
  const text = String(get("text") ?? "");
  const message: ChatMessage = {
    id: nextMessageId(),
    direction: "inbound",
    author: "supplier",
    text,
    media: photo instanceof File && photo.size ? URL.createObjectURL(photo) : typeof photo === "string" && photo ? photo : null,
    media_kind: photo ? "image" : null,
    status: "received",
    turn_id: null,
    sent_at: new Date().toISOString(),
  };
  (conversations[contact.conversation_id] ??= []).push(message);
  if (/no (voy a|puedo)|cancel/i.test(text)) {
    agentSays(contact.conversation_id, "Entendido, gracias por avisar a tiempo. Coordino con el Gerente y te confirmo cómo recogemos lo que ya tienes.", 2000);
    // The redistribution reaches another workshop: shows the highlight and the toast.
    const other = simulatorContacts.find((c) => c.channel === "simulator" && c.allowed_number_id !== contact.allowed_number_id);
    if (other) {
      other.conversation_id ??= 100 + other.allowed_number_id;
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
// "Por pedir" (ADR 0025 A): open material requirements by material; generating moves them to purchase orders.
const pending = structuredClone(pendingSeed) as unknown as PendingRequirement[];
let nextPurchaseOrderId = 100;
let nextMaterialCode = 10;

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
    status_history: [],
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

const customers = structuredClone(customersSeed) as Customer[];
const products = structuredClone(productsSeed) as Product[];

type ItemInput = { product: string; quantity: number; color?: string; customization?: string; sizes?: Record<string, number> };

function itemsFrom(body: Record<string, unknown>): OrderItem[] {
  return ((body.items as ItemInput[]) ?? []).map((item, i) => {
    const product = products.find((p) => p.code === item.product);
    return {
      id: i + 1,
      product: { id: product?.id ?? 0, code: item.product, name: product?.name ?? item.product, image: product?.image ?? null },
      quantity: Number(item.quantity),
      sizes: item.sizes ?? {},
      color: item.color ?? "",
      customization: item.customization ?? "",
      unit_price: null,
    } as OrderItem;
  });
}

function createOrder(body: Record<string, unknown>, user: User): Response {
  const code = String(body.code);
  const existing = orders.find((o) => o.code === code);
  if (existing) return json(200, existing); // idempotent by code, like the API
  const items = (body.items as { quantity: number }[]) ?? [];
  const customer = String(body.customer);
  if (!customers.some((c) => c.name === customer)) customers.push({ id: 90 + customers.length, name: customer, ruc: null });
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
  orderDetails[order.id] = {
    issued_on: String(body.issued_on ?? new Date().toISOString().slice(0, 10)),
    owner: { id: user.id, first_name: user.first_name || user.username },
    notes: typeof body.notes === "string" ? body.notes : "",
    items: itemsFrom(body),
  };
  return json(201, order);
}

const monitor = structuredClone(monitorSeed) as unknown as Monitor;
const materials = structuredClone(materialsSeed) as MaterialDetail[];
const routes = structuredClone(routesSeed) as unknown as Record<string, Route>;

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
  connected_at: null,
  last_error: null,
  last_error_at: null,
};
let claude: ClaudeStatus = { ...DISCONNECTED };

function connectedStatus(method: ClaudeStatus["method"]): ClaudeStatus {
  // Epoch milliseconds, like the API.
  return {
    connected: true,
    method,
    subscription_type: method === "oauth" ? "max" : null,
    expires_at: method === "oauth" ? Date.now() + 8 * 3600 * 1000 : null,
    refresh_token_expires_at: method === "oauth" ? Date.now() + 30 * 24 * 3600 * 1000 : null,
    expired: false,
    connected_at: new Date().toISOString(),
    last_error: null,
    last_error_at: null,
  };
}

// The clock is real time now (factor 1); the endpoint stays for compatibility.
function clockNow(): number {
  return Date.now();
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

  if (route === "POST /api/suppliers/self-register/") return createSupplier(readBody(init.body), "self_registered");

  // Public progress report by token (ADR 0024 C); "demo" is the mock token.
  const reportMatch = route.match(/^(GET|POST) \/api\/report\/([^/]+)\/$/);
  if (reportMatch) {
    const po = purchaseOrders.find((p) => p.code === "PT-0002");
    if (reportMatch[2] !== "demo" || !po) return json(404, { detail: "Enlace no válido." });
    if (reportMatch[1] === "POST") {
      const units = Number(formValue(init.body, "units_done"));
      Object.assign(po, { units_done: units, progress_pct: Math.round((units / Number(po.total_units)) * 100), last_progress_at: new Date().toISOString() });
      return json(201, { units_done: units });
    }
    return json(200, { code: po.code, product: { name: "Buzo escolar", image: null }, quantity: po.total_units, committed_on: po.committed_on, units_done: po.units_done });
  }

  const user = userFor(init.headers);
  if (!user) return json(401, { detail: "Authentication credentials were not provided." });

  switch (route) {
    case "GET /api/auth/me/":
      return json(200, user);
    case "POST /api/auth/logout/":
      return json(204);
    case "GET /api/clock/":
      return json(200, { now: new Date(clockNow()).toISOString(), factor: "1", paused: false } satisfies Clock);
    case "GET /api/me/badges/":
      return json(200, (badgesByRole as Record<Role, Badges>)[user.role]);
  }

  if (route === "GET /api/monitor/") return json(200, monitorFor(user.role));

  if (route === "GET /api/orders/") {
    const params = new URL(path, "http://mock").searchParams;
    const filtered = orders.filter(
      (o) =>
        (!params.get("status") || params.get("status")!.split(",").includes(o.status)) &&
        (!params.get("risk") || o.risk === params.get("risk")) &&
        (!params.get("brand") || String(o.brand.id) === params.get("brand")) &&
        (!params.get("code") || o.code === params.get("code")) &&
        (!params.get("q") || o.code.toLowerCase().includes(params.get("q")!.toLowerCase())),
    );
    return json(200, filtered);
  }
  if (route === "POST /api/orders/break-down/") {
    if (user.role === "sales") return json(403, { detail: "Solo Producción y Gerente." });
    const body = readBody(init.body) as { order_ids?: number[] };
    const targets = orders.filter((o) => (body.order_ids ? body.order_ids.includes(o.id) : true));
    const broken_down: string[] = [];
    const skipped: { code: string; reason: string }[] = [];
    for (const order of targets) {
      if (order.status !== "registered") {
        skipped.push({ code: order.code, reason: `ya está ${order.status_display.toLowerCase()}` });
        continue;
      }
      order.status = "broken_down";
      order.status_display = "Desglosada";
      broken_down.push(order.code);
    }
    return json(200, { broken_down, skipped });
  }
  if (route === "POST /api/orders/") {
    if (user.role === "production") return json(403, { detail: "Solo Comercial y Gerente." });
    return createOrder(readBody(init.body), user);
  }
  if (route === "GET /api/customers/") return json(200, customers);
  if (route === "GET /api/products/") return json(200, products);
  const orderPatch = route.match(/^PATCH \/api\/orders\/(\d+)\/$/);
  if (orderPatch) {
    const order = orders.find((o) => o.id === Number(orderPatch[1]));
    if (!order) return json(404, { detail: "No existe." });
    const detail = orderDetails[order.id] ?? {};
    const own = detail.owner?.id === user.id;
    if (user.role === "production" || (user.role === "sales" && !(own && ["registered", "broken_down"].includes(order.status)))) {
      return json(403, { detail: "No puedes editar esta orden." });
    }
    const body = readBody(init.body);
    if (typeof body.customer === "string") order.customer = { ...order.customer, name: body.customer };
    if (typeof body.brand === "string") order.brand = { ...order.brand, name: body.brand };
    if (typeof body.promised_on === "string") order.promised_on = body.promised_on;
    if (Array.isArray(body.items)) {
      const items = itemsFrom(body);
      order.total_units = items.reduce((sum, item) => sum + item.quantity, 0);
      orderDetails[order.id] = { ...detail, items };
    }
    if (typeof body.notes === "string") orderDetails[order.id] = { ...orderDetails[order.id], notes: body.notes };
    return json(200, orderDetailFor(order, user.role));
  }
  const orderCancel = route.match(/^POST \/api\/orders\/(\d+)\/cancel\/$/);
  if (orderCancel) {
    const order = orders.find((o) => o.id === Number(orderCancel[1]));
    if (!order) return json(404, { detail: "No existe." });
    const own = orderDetails[order.id]?.owner?.id === user.id;
    if (user.role === "production" || (user.role === "sales" && !(own && ["registered", "broken_down"].includes(order.status)))) {
      return json(403, { detail: "No puedes cancelar esta orden." });
    }
    order.status = "cancelled";
    order.status_display = "Cancelada";
    return json(200, orderDetailFor(order, user.role));
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
  if (path.startsWith("/api/materials/")) {
    if (user.role === "sales") return json(403, { detail: "Solo Gerente y Producción." });
    if (route === "GET /api/materials/") return json(200, materials.map(({ requirements: _r, ...m }) => m));
    const m = route.match(/^GET \/api\/materials\/(\d+)\/$/);
    const material = m && materials.find((x) => x.id === Number(m[1]));
    return material ? json(200, material) : json(404, { detail: "No existe." });
  }
  if (path.startsWith("/api/onboarding/") || path.startsWith("/api/style/")) {
    if (user.role !== "manager") return json(403, { detail: "Solo el Gerente." });
    const handled = styleRoutes(route, init.body);
    if (handled) return handled;
  }
  if (path.startsWith("/api/suppliers/")) {
    if (user.role !== "manager") return json(403, { detail: "Solo el Gerente." });
    if (route === "POST /api/suppliers/") return createSupplier(readBody(init.body), "registered");
    if (route === "GET /api/suppliers/") {
      const status = new URL(path, "http://mock").searchParams.get("status");
      const list = suppliers.filter((s) => (status ? s.status === status : s.status !== "pending_review"));
      return json(200, list.map((s) => ({ ...s, ...(supplierDetails[s.id]?.numbers && { numbers_count: supplierDetailFor(s).numbers_count, active_numbers_count: supplierDetailFor(s).active_numbers_count }) })));
    }
    const handled = supplierRoutes(route, init.body);
    if (handled) return handled;
  }
  if (route === "GET /api/requirements/pending/") {
    if (user.role === "sales") return json(403, { detail: "Solo Producción y Gerente." });
    // Prices are the Gerente's.
    return json(
      200,
      pending.map((row) =>
        user.role === "manager"
          ? row
          : { ...row, reference_price: null, candidates: [] },
      ),
    );
  }
  if (route === "POST /api/purchase-orders/generate/") {
    if (user.role === "sales") return json(403, { detail: "Solo Producción y Gerente." });
    const body = readBody(init.body) as { material_ids?: number[]; supplier_overrides?: Record<string, number> };
    const ids = body.material_ids ?? pending.map((row) => row.material.id);
    const created: NonNullable<GeneratedPurchaseOrders["created"]> = [];
    const skipped: GeneratedPurchaseOrders["skipped"] = [];
    for (const id of ids) {
      const index = pending.findIndex((row) => row.material.id === id);
      if (index < 0) continue;
      const row = pending[index];
      const override = body.supplier_overrides?.[String(id)];
      const supplier = row.candidates?.find((c) => c.supplier.id === override)?.supplier ?? row.suggested_supplier;
      if (!supplier) {
        skipped.push({ material_id: id, reason: "sin proveedor sugerido" });
        continue;
      }
      const candidate = row.candidates?.find((c) => c.supplier.id === supplier.id);
      const po: PurchaseOrderListItem = {
        id: nextPurchaseOrderId++,
        code: `PI-${String(nextMaterialCode++).padStart(4, "0")}`,
        kind: "material",
        kind_display: "Insumo",
        status: "suggested",
        status_display: "Sugerido",
        waiting_manager: true,
        supplier: { id: supplier.id, name: supplier.name, kind: "materials" },
        orders: row.orders.map((o) => ({ id: o.id, code: o.code, customer_name: o.customer_name })),
        total_units: Number(row.total_to_order),
        units_done: 0,
        progress_pct: 0,
        internal_due_on: row.due_on,
        committed_on: null,
        last_progress_at: null,
        next_follow_up_at: null,
        total_amount: candidate?.unit_price ? String(Number(candidate.unit_price) * Number(row.total_to_order)) : null,
        currency: candidate?.currency ?? "PEN",
        redistributed_from: null,
        alert_severity: null,
      } as unknown as PurchaseOrderListItem;
      purchaseOrders.unshift(po);
      pending.splice(index, 1);
      created.push({ id: po.id, code: po.code, supplier: po.supplier, material: row.material, orders: po.orders });
    }
    return json(201, { created, decision_id: 900, skipped });
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
            (!params.get("status") || params.get("status")!.split(",").includes(po.status)) &&
            (!params.get("q") || [po.code, ...po.orders.map((o) => o.code)].some((c) => c.toLowerCase().includes(params.get("q")!.toLowerCase()))) &&
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
