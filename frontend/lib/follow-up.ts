// Proactive follow-up configured by the Gerente (ADR 0027).
// GET/PATCH /api/settings/follow-up/ and GET /api/settings/follow-up/preview/.

export type FollowUpMode = "minimal" | "balanced" | "high";

export interface FollowUpSettings {
  follow_up_mode: FollowUpMode;
  follow_up_window_start: string; // "09:00", Lima time
  follow_up_window_end: string; // "18:00"
  follow_up_weekdays: number[]; // 0 = Monday … 6 = Sunday
}

export interface FollowUpPreviewItem {
  supplier: { id: number; name: string };
  purchase_orders: string[]; // codes
  at: string; // ISO datetime
  kind: "checkpoint" | "reminder";
  reason: string;
}

export const DEFAULT_FOLLOW_UP: FollowUpSettings = {
  follow_up_mode: "balanced",
  follow_up_window_start: "09:00",
  follow_up_window_end: "18:00",
  follow_up_weekdays: [0, 1, 2, 3, 4, 5],
};

// ADR 0027 §2: checkpoints for a 10-day purchase order, and the reminder rule.
export const FOLLOW_UP_MODES: Record<FollowUpMode, { label: string; about: string; reminder: string; days: number[] }> = {
  minimal: {
    label: "Mínimo",
    about: "A la mitad del plazo y la víspera de la entrega. Se salta si el proveedor ya escribió o reportó avance.",
    reminder: "Recordatorio al día siguiente si no responde.",
    days: [5, 9],
  },
  balanced: {
    label: "Balanceado",
    about: "Al 30 %, 60 % y 85 % del plazo y la víspera. Se salta si reportó avance en las últimas 24 h y va a ritmo.",
    reminder: "Recordatorio a las 4 h, el mismo día, si no responde.",
    days: [3, 6, 8, 9],
  },
  high: {
    label: "Alto",
    about: "Un mensaje corto cada día hábil hasta la entrega.",
    reminder: "Recordatorio a las 2 h si no responde.",
    days: [1, 2, 3, 4, 5, 6, 7, 8, 9],
  },
};

export const WEEKDAYS = ["L", "M", "X", "J", "V", "S", "D"];
export const WEEKDAY_NAMES = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"];

export function minutesOf(time: string): number | null {
  const match = /^(\d{1,2}):(\d{2})/.exec(time);
  if (!match) return null;
  return Number(match[1]) * 60 + Number(match[2]);
}

// 0 = Monday, in Lima.
export function todayWeekday(): number {
  const day = new Intl.DateTimeFormat("en-US", { timeZone: "America/Lima", weekday: "short" }).format(new Date());
  return ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"].indexOf(day);
}
