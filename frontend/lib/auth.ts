import type { User } from "./types";

const TOKEN_KEY = "corpotex.token";
const USER_KEY = "corpotex.user";

export interface Session {
  token: string;
  user: User;
}

// The session lives in sessionStorage, one per tab, so two windows of the same
// browser can be logged in as different roles (demo: Gerente and Comercial side
// by side). localStorage only seeds new tabs with the last login.

function read(storage: Storage, key: string): string | null {
  try {
    return storage.getItem(key);
  } catch {
    return null;
  }
}

function write(storage: Storage, token: string, user: User) {
  try {
    storage.setItem(TOKEN_KEY, token);
    storage.setItem(USER_KEY, JSON.stringify(user));
  } catch {
    // Storage blocked (private mode): the session lasts until reload.
  }
}

function parse(token: string | null, user: string | null): Session | null {
  if (!token || !user) return null;
  try {
    return { token, user: JSON.parse(user) as User };
  } catch {
    return null;
  }
}

let memory: Session | null = null;

export function getSession(): Session | null {
  if (typeof window === "undefined") return null;
  const own = parse(read(sessionStorage, TOKEN_KEY), read(sessionStorage, USER_KEY));
  if (own) return own;
  const seeded = parse(read(localStorage, TOKEN_KEY), read(localStorage, USER_KEY));
  if (seeded) {
    write(sessionStorage, seeded.token, seeded.user);
    return seeded;
  }
  return memory;
}

export function saveSession(session: Session) {
  memory = session;
  write(sessionStorage, session.token, session.user);
  write(localStorage, session.token, session.user);
}

export function updateUser(user: User) {
  const session = getSession();
  if (session) saveSession({ token: session.token, user });
}

export function clearSession() {
  const current = getSession();
  memory = null;
  try {
    sessionStorage.removeItem(TOKEN_KEY);
    sessionStorage.removeItem(USER_KEY);
    // Only forget the seed if it is this tab's login; another tab may own it.
    if (current && read(localStorage, TOKEN_KEY) === current.token) {
      localStorage.removeItem(TOKEN_KEY);
      localStorage.removeItem(USER_KEY);
    }
  } catch {
    // Nothing to clear.
  }
}
