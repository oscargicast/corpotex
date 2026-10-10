import Link from "next/link";
import { formatDay } from "@/lib/format";
import type { CriticalStep } from "@/lib/types";

const DAY = 86_400_000;
const STATUS_COLOR: Record<CriticalStep["status"], string> = {
  done: "bg-success",
  in_progress: "bg-accent",
  pending: "bg-muted/25",
  late: "bg-danger",
};
const STATUS_LABEL: Record<CriticalStep["status"], string> = {
  done: "Hecho",
  in_progress: "En curso",
  pending: "Pendiente",
  late: "Atrasado",
};

function time(day: string) {
  return new Date(`${day}T12:00:00-05:00`).getTime();
}

// Gantt in CSS: one row per step, with the promised date as a red line.
// It shows the cushion: suppliers get an internal date well before the customer's.
export function CriticalPath({ steps, promisedOn }: { steps: CriticalStep[]; promisedOn: string }) {
  if (!steps.length) return <p className="text-sm text-muted">Sin ruta crítica todavía.</p>;

  const start = Math.min(...steps.map((s) => time(s.start)));
  const end = Math.max(time(promisedOn), ...steps.map((s) => time(s.end))) + DAY;
  const span = end - start;
  const pct = (t: number) => ((t - start) / span) * 100;

  return (
    <div>
      <div className="relative space-y-2">
        {/* Over the rows; offset = label column + gap. */}
        <div className="pointer-events-none absolute inset-y-0 left-[9.5rem] right-0 z-10 sm:left-[13.5rem]">
          <span className="absolute inset-y-0 border-l-2 border-dashed border-danger" style={{ left: `${pct(time(promisedOn))}%` }}>
            <span className="absolute -top-5 -translate-x-1/2 whitespace-nowrap text-[11px] font-medium text-danger">
              Prometido {formatDay(promisedOn)}
            </span>
          </span>
        </div>
        <div className="h-3" />
        {steps.map((step) => {
          const left = pct(time(step.start));
          const width = Math.max(pct(time(step.end) + DAY) - left, 2);
          const label = step.purchase_order_id ? (
            <Link href={`/purchase-orders/${step.purchase_order_id}`} className="text-accent hover:underline">
              {step.name}
            </Link>
          ) : (
            step.name
          );
          return (
            <div key={step.id} className="grid grid-cols-[9rem_1fr] items-center gap-2 sm:grid-cols-[13rem_1fr]">
              <span className="truncate text-xs sm:text-sm" title={step.name}>
                {step.critical && <span className="mr-1 text-danger" title="Paso crítico">●</span>}
                {label}
              </span>
              <span className="relative h-6 rounded bg-canvas">
                <span
                  className={`absolute inset-y-0 rounded ${STATUS_COLOR[step.status]} ${step.critical ? "ring-2 ring-ink/70" : ""}`}
                  style={{ left: `${left}%`, width: `${width}%` }}
                  title={`${formatDay(step.start)} → ${formatDay(step.end)} · ${STATUS_LABEL[step.status]}`}
                />
              </span>
            </div>
          );
        })}
      </div>
      <ul className="mt-3 flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted">
        {Object.entries(STATUS_LABEL).map(([key, label]) => (
          <li key={key} className="flex items-center gap-1">
            <span className={`inline-block size-2.5 rounded-sm ${STATUS_COLOR[key as CriticalStep["status"]]}`} />
            {label}
          </li>
        ))}
        <li className="flex items-center gap-1">
          <span className="text-danger">●</span> Crítico
        </li>
      </ul>
    </div>
  );
}
