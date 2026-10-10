// In-browser stand-in for the Django API while B1 is not on main.
// Enabled with NEXT_PUBLIC_USE_MOCKS=1. Shapes follow docs/backend/modelo-de-datos.md.
import badgesByRole from "@/mocks/badges.json";
import users from "@/mocks/users.json";
import type { Badges, Clock, Role, User } from "./types";

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
  return json(404, { detail: `mock: ${route} not implemented` });
}
