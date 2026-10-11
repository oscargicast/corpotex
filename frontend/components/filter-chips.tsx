"use client";

// Single-choice filter chips with a count each, the same on every list. On
// the phone the row scrolls sideways and each chip is 44 px tall.
export interface ChipOption<K extends string> {
  key: K;
  label: string;
  count?: number;
}

export function FilterChips<K extends string>({ options, value, onChange, label }: { options: ChipOption<K>[]; value: K; onChange: (key: K) => void; label: string }) {
  return (
    <div className="-mx-4 overflow-x-auto px-4 sm:mx-0 sm:overflow-visible sm:px-0">
      <div className="flex w-max gap-2 sm:w-auto sm:flex-wrap" role="group" aria-label={label}>
        {options.map((option) => {
          const on = value === option.key;
          return (
            <button
              key={option.key}
              type="button"
              aria-pressed={on}
              onClick={() => onChange(option.key)}
              className={`inline-flex min-h-11 shrink-0 items-center gap-1.5 whitespace-nowrap rounded-full px-3 text-sm ring-1 transition-colors duration-150 sm:min-h-9 ${
                on ? "bg-ink text-white ring-ink" : "bg-surface ring-line hover:bg-canvas"
              }`}
            >
              {option.label}
              {option.count !== undefined && <span className={`rounded-full px-1.5 text-xs tabular-nums ${on ? "bg-white/20" : "bg-canvas text-muted"}`}>{option.count}</span>}
            </button>
          );
        })}
      </div>
    </div>
  );
}
