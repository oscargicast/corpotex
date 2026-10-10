import { clearSession, getSession } from "./auth";
import { mockFetch } from "./mock-fetch";

const USE_MOCKS = process.env.NEXT_PUBLIC_USE_MOCKS === "1";

export class ApiError extends Error {
  constructor(
    readonly status: number,
    readonly body: unknown,
  ) {
    super(`API ${status}`);
  }
}

type ApiInit = Omit<RequestInit, "body"> & { body?: BodyInit | null; json?: unknown };

// All paths are same-origin and keep Django's trailing slash: "/api/clock/".
export async function apiFetch<T>(path: string, init: ApiInit = {}): Promise<T> {
  const session = getSession();
  const headers = new Headers(init.headers);
  headers.set("Accept", "application/json");
  if (session && !headers.has("Authorization")) headers.set("Authorization", `Token ${session.token}`);

  let body = init.body;
  if (init.json !== undefined) {
    headers.set("Content-Type", "application/json");
    body = JSON.stringify(init.json);
  }

  const request = { ...init, headers, body };
  const res = USE_MOCKS ? await mockFetch(path, request) : await fetch(path, request);

  if (res.status === 401 && session) {
    clearSession();
    const next = encodeURIComponent(window.location.pathname + window.location.search);
    window.location.assign(`/login?next=${next}`);
  }
  if (!res.ok) {
    throw new ApiError(res.status, await res.json().catch(() => null));
  }
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

export const fetcher = <T>(path: string) => apiFetch<T>(path);
