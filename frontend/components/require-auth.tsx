"use client";

import { usePathname, useRouter } from "next/navigation";
import { createContext, useContext, useEffect, useState } from "react";
import useSWR from "swr";
import { fetcher } from "@/lib/api";
import { getSession, updateUser, type Session } from "@/lib/auth";
import type { Role, User } from "@/lib/types";

const UserContext = createContext<User | null>(null);

export function useUser(): User {
  const user = useContext(UserContext);
  if (!user) throw new Error("useUser outside <RequireAuth>");
  return user;
}

export function RequireAuth({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const pathname = usePathname();
  const [session, setSession] = useState<Session | null>(null);

  useEffect(() => {
    const current = getSession();
    if (!current) router.replace(`/login?next=${encodeURIComponent(pathname)}`);
    else setSession(current);
  }, [router, pathname]);

  // The role can change in the admin; /me/ keeps the stored user fresh.
  const { data: me } = useSWR<User>(session ? "/api/auth/me/" : null, fetcher);
  useEffect(() => {
    if (me) updateUser(me);
  }, [me]);

  if (!session) return null;
  return <UserContext value={me ?? session.user}>{children}</UserContext>;
}

// Hides a view from roles that can't see it; the API enforces it again.
export function RoleGate({ roles, children }: { roles: Role[]; children: React.ReactNode }) {
  const user = useUser();
  const router = useRouter();
  const allowed = roles.includes(user.role);

  useEffect(() => {
    if (!allowed) router.replace("/");
  }, [allowed, router]);

  return allowed ? children : null;
}
