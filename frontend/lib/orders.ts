import type { OrderDetail, OrderListItem, User } from "./types";

// Who may do what with an order (ADR 0025 B). Comercial owns what it registered
// and can touch it until the breakdown is confirmed; the Gerente can always;
// Producción only confirms breakdowns and moves purchase orders.
const EDITABLE_BY_SALES = ["registered", "broken_down"];
const CLOSED = ["delivered", "cancelled"];
const IN_PRODUCTION_OR_LATER = ["in_production", "ready", "delivered", "cancelled"];

function ownedBy(user: User, order: Partial<OrderDetail>): boolean {
  return !!order.owner && order.owner.id === user.id;
}

export function canCreateOrder(user: User): boolean {
  return user.role !== "production";
}

export function canEditOrder(user: User, order: OrderListItem & Partial<OrderDetail>): boolean {
  if (user.role === "manager") return !CLOSED.includes(order.status);
  if (user.role === "sales") return ownedBy(user, order) && EDITABLE_BY_SALES.includes(order.status);
  return false;
}

export function canCancelOrder(user: User, order: OrderListItem & Partial<OrderDetail>): boolean {
  if (user.role === "manager") return !IN_PRODUCTION_OR_LATER.includes(order.status);
  if (user.role === "sales") return ownedBy(user, order) && EDITABLE_BY_SALES.includes(order.status);
  return false;
}
