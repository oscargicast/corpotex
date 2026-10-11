"use client";

import { LogOut, MoreHorizontal, Sparkles, X } from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { clearSession } from "@/lib/auth";
import { useBadges } from "@/lib/badges";
import { isActive, type NavItem, navFor } from "@/lib/nav";
import { ROLE_LABELS } from "@/lib/types";
import { AssistantPanel } from "./assistant/panel";
import { AssistantToast } from "./assistant/toast";
import { ClaudeBanner } from "./claude-banner";
import { useUser } from "./require-auth";

function Count({ value, className = "" }: { value: number | null | undefined; className?: string }) {
  if (!value) return null;
  return (
    <span
      className={`inline-flex min-w-5 items-center justify-center rounded-full bg-danger px-1.5 text-xs font-semibold leading-5 text-white ${className}`}
    >
      {value > 99 ? "99+" : value}
    </span>
  );
}

// Clears this tab only. The token stays valid on the server (logout does not
// revoke it), so other windows of the same user keep working.
function logout() {
  clearSession();
  window.location.assign("/login");
}

export function Shell({ children }: { children: React.ReactNode }) {
  const user = useUser();
  const pathname = usePathname();
  const router = useRouter();
  const badges = useBadges();
  const [assistantOpen, setAssistantOpen] = useState(false);
  const items = navFor(user.role);
  const pending = badges?.pending_decisions ?? 0;
  const unread = badges?.assistant_unread ?? 0;
  const name = user.first_name || user.username;
  const role = ROLE_LABELS[user.role];

  useEffect(() => {
    const total = unread + pending;
    document.title = total ? `(${total}) Corpotex` : "Corpotex";
  }, [unread, pending]);

  // Desktop opens the side panel; on a phone the assistant is its own screen.
  function openAssistant() {
    if (window.matchMedia("(min-width: 768px)").matches) setAssistantOpen(true);
    else router.push("/assistant");
  }

  return (
    <div className="flex min-h-dvh">
      {/* Icons only from 768 px (two windows side by side on the projector); labels from 1280 px. */}
      <aside className="sticky top-0 hidden h-dvh w-16 shrink-0 flex-col border-r border-line bg-surface md:flex xl:w-60">
        <Link href="/" className="flex h-14 items-center px-5 text-lg font-black tracking-tight">
          <span className="xl:hidden">C</span>
          <span className="hidden xl:inline">CORPOTEX</span>
        </Link>
        <nav className="flex flex-1 flex-col gap-1 px-2" aria-label="Principal">
          {items.map((item) => (
            <SideLink key={item.href} item={item} active={isActive(pathname, item.href)} count={item.href === "/" ? pending : 0} />
          ))}
        </nav>
        <div className="m-2 border-t border-line pt-2">
          <Profile name={name} role={role} compact />
          <button
            type="button"
            onClick={logout}
            className="flex w-full items-center gap-3 rounded-md px-3 py-2 text-sm text-muted hover:bg-canvas"
            title="Salir"
          >
            <LogOut size={18} className="shrink-0" />
            <span className="hidden xl:inline">Salir</span>
          </button>
        </div>
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="sticky top-0 z-20 flex h-14 items-center gap-3 border-b border-line bg-surface/95 px-4 backdrop-blur">
          <Link href="/" className="text-lg font-black tracking-tight md:hidden">
            CORPOTEX
          </Link>
          <div className="ml-auto flex items-center gap-3">
            <button
              type="button"
              onClick={() => setAssistantOpen((open) => !open)}
              aria-expanded={assistantOpen}
              className="hidden items-center gap-2 rounded-md px-2 py-1.5 text-sm font-medium hover:bg-canvas md:flex"
            >
              <Sparkles size={18} />
              <span className="hidden lg:inline">Asistente</span>
              <Count value={unread} />
            </button>
          </div>
        </header>
        <ClaudeBanner badges={badges} />
        <main className="flex-1 px-4 pb-24 pt-4 md:px-6 md:pb-8">{children}</main>
      </div>

      <BottomNav items={items} pathname={pathname} unread={unread} pending={pending} name={name} role={role} />
      {pathname !== "/assistant" && <AssistantPanel open={assistantOpen} onClose={() => setAssistantOpen(false)} />}
      <AssistantToast badges={badges} chatOpen={assistantOpen || pathname === "/assistant"} onOpen={openAssistant} />
    </div>
  );
}

// Who is logged in: avatar with the initial, name and role. In the icon-only
// sidebar (768 to 1279 px) only the avatar shows, with the rest as a tooltip.
function Profile({ name, role, compact = false }: { name: string; role: string; compact?: boolean }) {
  return (
    <div className="flex items-center gap-3 px-3 py-2" title={`${name} · ${role}`}>
      <span className="flex size-8 shrink-0 items-center justify-center rounded-full bg-ink text-sm font-semibold uppercase text-white" aria-hidden>
        {name.trim().charAt(0) || "?"}
      </span>
      <span className={`min-w-0 leading-tight ${compact ? "hidden xl:block" : ""}`}>
        <span className="block truncate text-sm font-medium">{name}</span>
        <span className="block truncate text-xs text-muted">{role}</span>
      </span>
    </div>
  );
}

function SideLink({ item, active, count }: { item: NavItem; active: boolean; count: number }) {
  const Icon = item.icon;
  return (
    <Link
      href={item.href}
      title={item.label}
      aria-label={item.label}
      aria-current={active ? "page" : undefined}
      className={`relative flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium ${
        active ? "bg-ink text-white" : "text-ink hover:bg-canvas"
      }`}
    >
      <Icon size={18} className="shrink-0" />
      <span className="hidden xl:inline">{item.label}</span>
      <Count value={count} className="absolute right-1 top-1 xl:static xl:ml-auto" />
    </Link>
  );
}

const PRIMARY = ["/", "/orders", "/purchase-orders"];

function BottomNav({
  items,
  pathname,
  unread,
  pending,
  name,
  role,
}: {
  items: NavItem[];
  pathname: string;
  unread: number;
  pending: number;
  name: string;
  role: string;
}) {
  const [moreOpen, setMoreOpen] = useState(false);
  const primary = items.filter((item) => PRIMARY.includes(item.href));
  const rest = items.filter((item) => !PRIMARY.includes(item.href));

  useEffect(() => setMoreOpen(false), [pathname]);

  const tab = "relative flex flex-1 flex-col items-center gap-0.5 py-2 text-[11px] font-medium";
  return (
    <>
      {moreOpen && (
        <div className="fixed inset-0 z-30 bg-ink/40 md:hidden" onClick={() => setMoreOpen(false)}>
          <nav
            className="absolute inset-x-0 bottom-16 rounded-t-xl bg-surface p-2 shadow-lg"
            onClick={(e) => e.stopPropagation()}
            aria-label="Más vistas"
          >
            <div className="mb-1 border-b border-line pb-1">
              <Profile name={name} role={role} />
            </div>
            {rest.map((item) => {
              const Icon = item.icon;
              return (
                <Link key={item.href} href={item.href} className="flex items-center gap-3 rounded-md px-3 py-3 text-sm hover:bg-canvas">
                  <Icon size={18} />
                  {item.label}
                </Link>
              );
            })}
            <button type="button" onClick={logout} className="flex w-full items-center gap-3 rounded-md px-3 py-3 text-sm text-muted hover:bg-canvas">
              <LogOut size={18} />
              Salir
            </button>
          </nav>
        </div>
      )}
      <nav
        className="fixed inset-x-0 bottom-0 z-40 flex border-t border-line bg-surface pb-[env(safe-area-inset-bottom)] md:hidden"
        aria-label="Principal"
      >
        {primary.map((item) => {
          const Icon = item.icon;
          const active = isActive(pathname, item.href);
          return (
            <Link key={item.href} href={item.href} className={`${tab} ${active ? "text-ink" : "text-muted"}`}>
              <Icon size={20} />
              {item.label}
              {item.href === "/" && <Count value={pending} className="absolute right-[22%] top-1" />}
            </Link>
          );
        })}
        <Link href="/assistant" className={`${tab} ${isActive(pathname, "/assistant") ? "text-ink" : "text-muted"}`}>
          <Sparkles size={20} />
          Asistente
          <Count value={unread} className="absolute right-[22%] top-1" />
        </Link>
        <button type="button" onClick={() => setMoreOpen((open) => !open)} className={`${tab} text-muted`}>
          {moreOpen ? <X size={20} /> : <MoreHorizontal size={20} />}
          Más
        </button>
      </nav>
    </>
  );
}
