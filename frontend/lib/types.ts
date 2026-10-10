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
