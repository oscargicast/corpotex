// Loading placeholders with the shape of what is coming (rule: every async
// call shows a skeleton or a spinner, never an empty screen).

export function Skeleton({ className = "" }: { className?: string }) {
  return <div className={`animate-pulse rounded-md bg-line ${className}`} aria-hidden />;
}

function Frame({ children, label = "Cargando" }: { children: React.ReactNode; label?: string }) {
  return (
    <div role="status" aria-label={label} aria-busy="true" className="space-y-4">
      {children}
    </div>
  );
}

export function SkeletonLines({ lines = 3, className = "" }: { lines?: number; className?: string }) {
  return (
    <div className={`space-y-2 ${className}`} aria-hidden>
      {Array.from({ length: lines }, (_, i) => (
        <Skeleton key={i} className={`h-3.5 ${i === lines - 1 ? "w-2/3" : "w-full"}`} />
      ))}
    </div>
  );
}

// A table: header row and `rows` rows of `cols` cells.
export function SkeletonTable({ rows = 6, cols = 5 }: { rows?: number; cols?: number }) {
  return (
    <Frame>
      <div className="rounded-xl bg-surface p-4 ring-1 ring-line sm:p-5">
        <div className="grid gap-3" style={{ gridTemplateColumns: `repeat(${cols}, minmax(0, 1fr))` }}>
          {Array.from({ length: cols }, (_, i) => (
            <Skeleton key={`h${i}`} className="h-3 w-2/3" />
          ))}
          {Array.from({ length: rows * cols }, (_, i) => (
            <Skeleton key={i} className={`h-4 ${i % cols === 0 ? "w-full" : "w-3/4"}`} />
          ))}
        </div>
      </div>
    </Frame>
  );
}

// A grid of cards (suppliers, onboarding lists).
export function SkeletonCards({ count = 4, lines = 3 }: { count?: number; lines?: number }) {
  return (
    <Frame>
      <div className="grid gap-3 md:grid-cols-2">
        {Array.from({ length: count }, (_, i) => (
          <div key={i} className="rounded-xl bg-surface p-4 ring-1 ring-line sm:p-5">
            <Skeleton className="mb-3 h-5 w-1/2" />
            <SkeletonLines lines={lines} />
          </div>
        ))}
      </div>
    </Frame>
  );
}

// A detail page: title, a row of facts, two cards.
export function SkeletonDetail() {
  return (
    <Frame>
      <Skeleton className="h-4 w-24" />
      <Skeleton className="h-8 w-56" />
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        {Array.from({ length: 4 }, (_, i) => (
          <div key={i} className="rounded-xl bg-surface p-4 ring-1 ring-line">
            <Skeleton className="mb-2 h-3 w-20" />
            <Skeleton className="h-6 w-24" />
          </div>
        ))}
      </div>
      <div className="grid gap-4 xl:grid-cols-2">
        {Array.from({ length: 2 }, (_, i) => (
          <div key={i} className="rounded-xl bg-surface p-4 ring-1 ring-line sm:p-5">
            <Skeleton className="mb-3 h-5 w-40" />
            <SkeletonLines lines={5} />
          </div>
        ))}
      </div>
    </Frame>
  );
}

// The Monitor: four KPIs and two columns of cards.
export function SkeletonMonitor() {
  return (
    <Frame>
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        {Array.from({ length: 4 }, (_, i) => (
          <div key={i} className="rounded-xl bg-surface p-4 ring-1 ring-line">
            <Skeleton className="mb-2 h-3 w-24" />
            <Skeleton className="h-8 w-10" />
          </div>
        ))}
      </div>
      <div className="grid gap-4 xl:grid-cols-2">
        {Array.from({ length: 2 }, (_, i) => (
          <div key={i} className="rounded-xl bg-surface p-4 ring-1 ring-line sm:p-5">
            <Skeleton className="mb-3 h-5 w-44" />
            <div className="rounded-lg p-3 ring-1 ring-line">
              <SkeletonLines lines={4} />
            </div>
          </div>
        ))}
      </div>
    </Frame>
  );
}

// A card body (one section loading inside a page that already rendered).
export function SkeletonCard({ lines = 4 }: { lines?: number }) {
  return (
    <div role="status" aria-label="Cargando" aria-busy="true" className="rounded-xl bg-surface p-4 ring-1 ring-line sm:p-5">
      <Skeleton className="mb-3 h-5 w-40" />
      <SkeletonLines lines={lines} />
    </div>
  );
}
