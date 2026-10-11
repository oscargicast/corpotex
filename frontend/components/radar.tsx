import { num } from "@/lib/format";
import type { SupplierListItem } from "@/lib/types";

// The five matching criteria, in the order they go around the chart (ADR 0024).
export const RADAR_AXES = [
  ["load", "Carga libre"],
  ["price", "Precio"],
  ["on_time", "Cumplimiento"],
  ["quality", "Calidad"],
  ["lead_time", "Plazo"],
] as const;

export type RadarKey = (typeof RADAR_AXES)[number][0];
export type RadarValues = Partial<Record<RadarKey, string | number | null | undefined>>;

const FILL = "#0062fa";
const COMPARE = "#12773d";

function point(center: number, radius: number, index: number, fraction: number): [number, number] {
  const angle = -Math.PI / 2 + (index * 2 * Math.PI) / RADAR_AXES.length;
  return [center + radius * fraction * Math.cos(angle), center + radius * fraction * Math.sin(angle)];
}

function fraction(value: string | number | null | undefined): number | null {
  const n = num(value);
  if (n === null) return null;
  // Scores come as 0 to 1; tolerate 0 to 100.
  return Math.max(0, Math.min(1, n > 1 ? n / 100 : n));
}

// Five-axis radar, plain SVG: filled polygon over a grid of rings, a label and
// the value (0 to 100) at every vertex. `compare` draws a second, dashed polygon.
export function Radar({
  values,
  compare,
  size = 220,
  showLabels = true,
  className = "",
  title,
}: {
  values: RadarValues;
  compare?: { values: RadarValues; label?: string };
  size?: number;
  showLabels?: boolean;
  className?: string;
  title?: string;
}) {
  const fontSize = size >= 200 ? 11 : 9;
  // Room for the longest label ("Cumplimiento") left and right of the chart.
  const extraX = showLabels ? Math.round(fontSize * 6.5) : 0;
  const pad = showLabels ? 34 : 8;
  const center = size / 2;
  const radius = size / 2 - pad;
  const rings = [0.25, 0.5, 0.75, 1];
  const fractions = RADAR_AXES.map(([key]) => fraction(values[key]));
  const polygon = fractions.map((f, i) => point(center, radius, i, f ?? 0).join(",")).join(" ");
  const comparePolygon = compare
    ? RADAR_AXES.map(([key], i) => point(center, radius, i, fraction(compare.values[key]) ?? 0).join(",")).join(" ")
    : null;

  return (
    <svg viewBox={`${-extraX} 0 ${size + 2 * extraX} ${size}`} width={size + 2 * extraX} height={size} role="img" aria-label={title ?? "Evaluación por criterio"} className={`max-w-full ${className}`}>
      {title && <title>{title}</title>}
      {rings.map((ring) => (
        <polygon
          key={ring}
          points={RADAR_AXES.map((_, i) => point(center, radius, i, ring).join(",")).join(" ")}
          fill={ring === 1 ? "#f5f5f7" : "none"}
          stroke="#e3e3e8"
          strokeWidth={1}
        />
      ))}
      {RADAR_AXES.map((_, i) => {
        const [x, y] = point(center, radius, i, 1);
        return <line key={i} x1={center} y1={center} x2={x} y2={y} stroke="#e3e3e8" strokeWidth={1} />;
      })}
      {comparePolygon && <polygon points={comparePolygon} fill={COMPARE} fillOpacity={0.12} stroke={COMPARE} strokeWidth={2} strokeDasharray="5 4" />}
      <polygon points={polygon} fill={FILL} fillOpacity={0.22} stroke={FILL} strokeWidth={2} strokeLinejoin="round" />
      {fractions.map((f, i) => {
        const [x, y] = point(center, radius, i, f ?? 0);
        return <circle key={i} cx={x} cy={y} r={size >= 200 ? 3.5 : 2.5} fill={FILL} stroke="#fff" strokeWidth={1.5} />;
      })}
      {showLabels &&
        RADAR_AXES.map(([key, label], i) => {
          const [x, y] = point(center, radius + (size >= 200 ? 18 : 12), i, 1);
          const anchor = Math.abs(x - center) < 4 ? "middle" : x > center ? "start" : "end";
          const f = fractions[i];
          return (
            <text key={key} x={x} y={y} textAnchor={anchor} dominantBaseline="middle" fontSize={fontSize} fill="#15141c" fontFamily="system-ui, sans-serif">
              <tspan>{label}</tspan>
              <tspan x={x} dy={fontSize + 1} fontWeight={700} fill={f === null ? "#5f5e6b" : "#15141c"}>
                {f === null ? "—" : Math.round(f * 100)}
              </tspan>
            </text>
          );
        })}
    </svg>
  );
}

// Supplier-level values when there is no matching run to show: on-time and
// quality come from deliveries, free load from the open purchase orders, lead
// time from the declared days (5 days is 100, 30 or more is 0). Price needs a
// matching run (a purchase order's scores), so it stays empty here.
export function radarFromSupplier(supplier: SupplierListItem): RadarValues {
  const quality = num(supplier.quality_score);
  const load = num(supplier.load_pct);
  const lead = supplier.lead_time_days;
  return {
    on_time: num(supplier.on_time_score),
    quality: quality === null ? null : quality / 5,
    load: load === null ? null : 1 - load / 100,
    lead_time: lead === null || lead === undefined ? null : Math.max(0, Math.min(1, 1 - (lead - 5) / 25)),
    price: null,
  };
}
