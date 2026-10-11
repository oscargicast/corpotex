// Three bouncing dots: the agent or the assistant is writing.
export function TypingDots({ label = "Escribiendo", className = "" }: { label?: string; className?: string }) {
  return (
    <span className={`inline-flex items-center gap-1 ${className}`} role="status" aria-label={`${label}…`}>
      {[0, 150, 300].map((delay) => (
        <span key={delay} className="size-1.5 animate-bounce rounded-full bg-current" style={{ animationDelay: `${delay}ms` }} aria-hidden />
      ))}
    </span>
  );
}
