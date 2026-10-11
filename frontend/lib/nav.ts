import {
  ClipboardList,
  Factory,
  LayoutDashboard,
  Boxes,
  type LucideIcon,
  Map,
  MessagesSquare,
  Package,
  Settings,
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
  { href: "/inventory", label: "Inventario", icon: Boxes, roles: ["manager", "production"] },
  { href: "/suppliers", label: "Proveedores", icon: Factory, roles: ["manager"] },
  { href: "/routes", label: "Rutas", icon: Map, roles: ["manager", "production"] },
  { href: "/simulator", label: "Simulador", icon: MessagesSquare, roles: ["manager"] },
  { href: "/settings", label: "Configuración", icon: Settings, roles: ["manager"] },
];

export function navFor(role: Role): NavItem[] {
  return NAV_ITEMS.filter((item) => !item.roles || item.roles.includes(role));
}

function matches(pathname: string, href: string): boolean {
  return href === "/" ? pathname === "/" : pathname === href || pathname.startsWith(`${href}/`);
}

// The most specific item wins when one menu path nests inside another.
export function isActive(pathname: string, href: string, items: NavItem[] = NAV_ITEMS): boolean {
  if (!matches(pathname, href)) return false;
  return !items.some((item) => item.href !== href && item.href.length > href.length && matches(pathname, item.href));
}
