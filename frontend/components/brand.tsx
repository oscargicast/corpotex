import Image from "next/image";

// Corpotex lockup (isotipo + CORPOTEX) from the brand kit, for light
// backgrounds. The 800 px source keeps it sharp on retina at 28–32 px tall,
// so it skips the image optimizer.
export function Lockup({ height = 28, className = "", priority = false }: { height?: number; className?: string; priority?: boolean }) {
  return <Image src="/brand/lockup-800.png" alt="Corpotex" width={Math.round(height * 6.25)} height={height} unoptimized priority={priority} className={className} />;
}

// Isotipo alone, for the icon-only sidebar.
export function Isotipo({ size = 28, className = "" }: { size?: number; className?: string }) {
  return <Image src="/brand/isotipo-64.png" alt="Corpotex" width={size} height={size} unoptimized className={className} />;
}
