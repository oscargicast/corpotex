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
  { href: "/style", label: "Estilo", icon: PenLine, roles: ["manager"] },
  { href: "/onboarding", label: "Onboarding", icon: ListChecks, roles: ["manager"] },
  { href: "/settings/claude", label: "Configuración", icon: Settings, roles: ["manager"] },
];

export function navFor(role: Role): NavItem[] {
  return NAV_ITEMS.filter((item) => !item.roles || item.roles.includes(role));
}

export function isActive(pathname: string, href: string): boolean {
  return href === "/" ? pathname === "/" : pathname === href || pathname.startsWith(`${href}/`);
}
