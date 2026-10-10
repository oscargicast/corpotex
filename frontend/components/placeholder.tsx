// Stand-in for views that land in F2 and F3.
export function Placeholder({ title, phase }: { title: string; phase: string }) {
  return (
    <section>
      <h1 className="text-2xl font-bold tracking-tight">{title}</h1>
      <p className="mt-6 rounded-lg border border-dashed border-line bg-surface p-8 text-center text-muted">
        Esta vista llega en {phase}.
      </p>
    </section>
  );
}
