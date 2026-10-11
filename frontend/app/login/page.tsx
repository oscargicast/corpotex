"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";
import { ApiError, apiFetch } from "@/lib/api";
import { getSession, saveSession } from "@/lib/auth";
import { type LoginResponse, ROLE_LABELS, type User } from "@/lib/types";
import { Spinner } from "@/components/ui";
import { Lockup } from "@/components/brand";

const USE_MOCKS = process.env.NEXT_PUBLIC_USE_MOCKS === "1";

export default function LoginPage() {
  return (
    <main className="flex min-h-dvh items-center justify-center px-4 py-10">
      <Suspense>
        <LoginForm />
      </Suspense>
    </main>
  );
}

// Only same-origin paths, so ?next= can't send the user elsewhere. Browsers
// read "\" as "/", so "/\evil.com" must be resolved, not just prefix-checked.
function safeNext(next: string | null): string {
  if (typeof window === "undefined") return "/";
  if (!next || !next.startsWith("/") || next.startsWith("//") || next.includes("\\")) return "/";
  try {
    const url = new URL(next, window.location.origin);
    if (url.origin !== window.location.origin) return "/";
    // Normalizing can turn "/.//evil.com" into "//evil.com": collapse leading slashes.
    return url.pathname.replace(/^\/+/, "/") + url.search + url.hash;
  } catch {
    return "/";
  }
}

function LoginForm() {
  const router = useRouter();
  const next = safeNext(useSearchParams().get("next"));
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (getSession()) router.replace(next);
  }, [router, next]);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const login = await apiFetch<Partial<LoginResponse> & { token: string }>("/api/auth/login/", {
        method: "POST",
        json: { username: username.trim(), password },
      });
      const user =
        login.user ??
        (await apiFetch<User>("/api/auth/me/", { headers: { Authorization: `Token ${login.token}` } }));
      // The API answers 403 to users without a role group (the admin superuser, for one).
      if (!(user.role in ROLE_LABELS)) {
        setError("Tu usuario no tiene rol (Gerente, Comercial o Producción). Pídele al Gerente que te lo asigne en el admin.");
        setBusy(false);
        return;
      }
      saveSession({ token: login.token, user });
      router.replace(next);
    } catch (err) {
      setError(
        err instanceof ApiError && err.status === 400
          ? "Usuario o contraseña incorrectos."
          : "No se pudo conectar. Inténtalo de nuevo.",
      );
      setBusy(false);
    }
  }

  return (
    <form onSubmit={submit} className="w-full max-w-sm rounded-xl bg-surface p-6 shadow-sm ring-1 ring-line sm:p-8">
      <Lockup height={32} priority />
      <h1 className="mt-2 text-sm text-muted">Órdenes, pedidos y talleres</h1>

      <label className="mt-8 block text-sm font-medium" htmlFor="username">
        Usuario
      </label>
      <input
        id="username"
        autoComplete="username"
        autoCapitalize="none"
        required
        value={username}
        onChange={(e) => setUsername(e.target.value)}
        className="mt-1 w-full rounded-md border border-line bg-surface px-3 py-2.5 text-base"
      />

      <label className="mt-4 block text-sm font-medium" htmlFor="password">
        Contraseña
      </label>
      <input
        id="password"
        type="password"
        autoComplete="current-password"
        required
        value={password}
        onChange={(e) => setPassword(e.target.value)}
        className="mt-1 w-full rounded-md border border-line bg-surface px-3 py-2.5 text-base"
      />

      {error && (
        <p className="mt-4 rounded-md bg-danger-soft px-3 py-2 text-sm text-danger" role="alert">
          {error}
        </p>
      )}

      <button
        type="submit"
        disabled={busy}
        aria-busy={busy || undefined}
        className="mt-6 inline-flex w-full items-center justify-center gap-2 rounded-md bg-brand px-4 py-2.5 font-semibold text-ink hover:bg-brand-hover disabled:opacity-60"
      >
        {busy && <Spinner />}
        {busy ? "Entrando…" : "Entrar"}
      </button>

      {USE_MOCKS && (
        <p className="mt-4 text-center text-xs text-muted">
          Datos de prueba: gerente, comercial o produccion (la contraseña es el mismo usuario).
        </p>
      )}
    </form>
  );
}
