import { Shirt } from "lucide-react";

// Product or material photo from /media/ (ADR 0021); an icon when there is none.
export function Thumb({ src, alt, size = 40 }: { src?: string | null; alt: string; size?: number }) {
  if (!src) {
    return (
      <span className="flex shrink-0 items-center justify-center rounded-md bg-canvas text-muted" style={{ width: size, height: size }} aria-hidden>
        <Shirt size={size * 0.5} />
      </span>
    );
  }
  // Plain <img>: /media/ is served by Django, outside Next's image optimizer.
  return <img src={src} alt={alt} width={size} height={size} loading="lazy" className="shrink-0 rounded-md object-cover" style={{ width: size, height: size }} />;
}
