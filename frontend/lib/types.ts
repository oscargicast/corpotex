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

export const ROLE_LABELS: Record<Role, string> = {
  manager: "Gerente",
  sales: "Comercial",
  production: "Producción",
};
