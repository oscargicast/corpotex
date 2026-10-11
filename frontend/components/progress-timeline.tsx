import { formatDay, formatDayTime } from "@/lib/format";
import type { ProgressReport } from "@/lib/types";
import { Pill } from "./ui";
import { ZoomableImage } from "./zoomable-image";

const SOURCE: Record<string, string> = { whatsapp: "WhatsApp", web: "Web", manual: "Dashboard", simulator: "Simulador" };

// Progress of a purchase order: one bar from 0 to the total with a mark per
// report (cumulative units), then a row of compact cards with the photo.
export function ProgressTimeline({ reports, total }: { reports: ProgressReport[]; total: number }) {
  const ordered = [...reports].sort((a, b) => a.reported_at.localeCompare(b.reported_at));
  const latest = ordered.at(-1)?.units_done ?? 0;
  const pct = (units: number) => (total > 0 ? Math.max(0, Math.min(100, (units / total) * 100)) : 0);

  return (
    <div>
      <div className="flex items-baseline justify-between text-sm">
        <span className="font-semibold tabular-nums">
          {latest} de {total}
        </span>
        <span className="text-xs text-muted tabular-nums">{Math.round(pct(latest))} %</span>
      </div>
      <div className="relative mt-2 h-3 rounded-full bg-canvas" role="progressbar" aria-valuenow={latest} aria-valuemin={0} aria-valuemax={total}>
        <div className="h-full rounded-full bg-accent transition-[width] duration-500" style={{ width: `${pct(latest)}%` }} />
        {ordered.map((report, i) => (
          <span
            key={report.id}
            className="absolute top-1/2 size-3.5 -translate-x-1/2 -translate-y-1/2 rounded-full border-2 border-accent bg-surface"
            style={{ left: `${pct(report.units_done)}%` }}
            title={`${report.units_done} · ${formatDayTime(report.reported_at)}`}
            aria-hidden={i < ordered.length ? undefined : true}
          />
        ))}
      </div>
      {/* Marks: date and cumulative units under each report, two rows so close ones do not overlap. */}
      <div className="relative mt-1 h-9 text-[10px] text-muted tabular-nums">
        {ordered.map((report, i) => {
          const left = pct(report.units_done);
          return (
            <span
              key={report.id}
              className={`absolute whitespace-nowrap ${i % 2 ? "top-4" : "top-0"} ${left > 85 ? "-translate-x-full" : left < 15 ? "" : "-translate-x-1/2"}`}
              style={{ left: `${left}%` }}
            >
              <strong className="text-ink">{report.units_done}</strong> · {formatDay(report.reported_at)}
            </span>
          );
        })}
      </div>

      <ol className="-mx-1 mt-2 flex gap-3 overflow-x-auto px-1 pb-1">
        {[...ordered].reverse().map((report) => {
          const index = ordered.indexOf(report);
          const previous = index > 0 ? ordered[index - 1].units_done : 0;
          return (
            <li key={report.id} className="flex w-56 shrink-0 gap-3 rounded-lg p-3 ring-1 ring-line">
              {report.photo && (
                <ZoomableImage src={report.photo} alt={`Avance: ${report.units_done} de ${total}`} className="size-14 shrink-0 rounded-md object-cover" />
              )}
              <div className="min-w-0 text-sm">
                <p className="font-semibold tabular-nums">
                  {previous} → {report.units_done} <span className="font-normal text-muted">de {total}</span>
                </p>
                {report.note && <p className="line-clamp-2 text-xs">{report.note}</p>}
                <p className="mt-1 flex flex-wrap items-center gap-1.5 text-xs text-muted">
                  {formatDayTime(report.reported_at)}
                  <Pill>{SOURCE[report.source] ?? report.source}</Pill>
                </p>
              </div>
            </li>
          );
        })}
      </ol>
    </div>
  );
}
