import {
  ClipboardList,
  Factory,
  LayoutDashboard,
  ListChecks,
  Boxes,
  type LucideIcon,
  Map,
  MessagesSquare,
  Package,
  PenLine,
  Settings,
  ShoppingCart,
} from "lucide-react";
import type { Role } from "./types";

export interface NavItem {
  href: string;
  label: string;
  icon: LucideIcon;
  roles?: Role[]; // every role when absent
}

export const NAV_ITEMS: NavItem[] = [
  { href: "/", label: "Monitor", icon: LayoutDashboard },
  { href: "/orders", label: "Órdenes", icon: ClipboardList },
  { href: "/purchase-orders", label: "Pedidos", icon: Package },
  { href: "/purchase-orders/pending", label: "Por pedir", icon: ShoppingCart, roles: ["manager", "production"] },
  { href: "/inventory", label: "Inventario", icon: Boxes, roles: ["manager", "production"] },
  { href: "/suppliers", label: "Proveedores", icon: Factory, roles: ["manager"] },
  { href: "/routes", label: "Rutas", icon: Map, roles: ["manager", "production"] },
  { href: "/simulator", label: "Simulador", icon: MessagesSquare, roles: ["manager"] },
  { href: "/style", label: "Estilo", icon: PenLine, roles: ["manager"] },
  { href: "/onboarding", label: "Onboarding", icon: ListChecks, roles: ["manager"] },
  { href: "/settings/claude", label: "Configuración", icon: Settings, roles: ["manager"] },
];

export function navFor(role: Role): NavItem[] {
  return NAV_ITEMS.filter((item) => !item.roles || item.roles.includes(role));
}

function matches(pathname: string, href: string): boolean {
  return href === "/" ? pathname === "/" : pathname === href || pathname.startsWith(`${href}/`);
}

// The most specific item wins: /purchase-orders/pending lights "Por pedir", not "Pedidos".
export function isActive(pathname: string, href: string, items: NavItem[] = NAV_ITEMS): boolean {
  if (!matches(pathname, href)) return false;
  return !items.some((item) => item.href !== href && item.href.length > href.length && matches(pathname, item.href));
}
