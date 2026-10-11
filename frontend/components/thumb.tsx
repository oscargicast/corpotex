import { Package, Shirt } from "lucide-react";
import { SewingMachine } from "./icons";
import { ZoomableImage } from "./zoomable-image";

type Kind = "material" | "workshop" | "finished" | string;

// The kind of a line at a glance: a workshop (sewing) is never a garment photo.
export function KindIcon({ kind, size = 16, className = "" }: { kind?: Kind | null; size?: number; className?: string }) {
  if (kind === "workshop") return <SewingMachine size={size} className={className} aria-label="Taller" />;
  if (kind === "material") return <Package size={size} className={className} aria-label="Insumo" role="img" />;
  return <Shirt size={size} className={className} aria-label="Producto terminado" role="img" />;
}

// Product or material photo from /media/ (ADR 0021), full size on click; an
// icon when there is none. A workshop line always shows the sewing machine.
export function Thumb({ src, alt, size = 40, kind }: { src?: string | null; alt: string; size?: number; kind?: Kind | null }) {
  if (kind === "workshop") {
    return (
      <span className="flex shrink-0 items-center justify-center rounded-md bg-accent/10 text-accent" style={{ width: size, height: size }} title="Taller">
        <SewingMachine size={Math.round(size * 0.6)} aria-label="Taller" />
      </span>
    );
  }
  if (!src) {
    const Icon = kind === "material" ? Package : Shirt;
    return (
      <span className="flex shrink-0 items-center justify-center rounded-md bg-canvas text-muted" style={{ width: size, height: size }} aria-hidden>
        <Icon size={size * 0.5} />
      </span>
    );
  }
  // Plain <img>: /media/ is served by Django, outside Next's image optimizer.
  return <ZoomableImage src={src} alt={alt} className="shrink-0 rounded-md object-cover" style={{ width: size, height: size }} />;
}
