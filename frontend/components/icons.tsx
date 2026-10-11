// Icons Lucide does not have, drawn to match it: 24 px box, 1.5 stroke,
// round caps and joins, currentColor.

type IconProps = { size?: number; className?: string; "aria-label"?: string; "aria-hidden"?: boolean };

function Svg({ size = 24, className = "", children, ...aria }: IconProps & { children: React.ReactNode }) {
  const label = aria["aria-label"];
  return (
    <svg
      viewBox="0 0 24 24"
      width={size}
      height={size}
      fill="none"
      stroke="currentColor"
      strokeWidth={1.5}
      strokeLinecap="round"
      strokeLinejoin="round"
      className={className}
      role={label ? "img" : undefined}
      aria-label={label}
      aria-hidden={label ? undefined : true}
    >
      {label && <title>{label}</title>}
      {children}
    </svg>
  );
}

// Workshop (taller): a sewing machine, pillar on the right, needle on the left.
export function SewingMachine(props: IconProps) {
  return (
    <Svg {...props}>
      <rect x="2.5" y="17.5" width="19" height="3" rx="1" />
      <path d="M17 17.5V9a3 3 0 0 0-3-3H7a2 2 0 0 0-2 2v1.5a1 1 0 0 0 1 1h4.5" />
      <path d="M17 11h-6.5v2.5" />
      <path d="M7.5 10.5v4" />
      <path d="M6 14.5h3" />
      <circle cx="19.5" cy="9.5" r="1.5" />
      <path d="M11 6V4M9.5 4h3" />
    </Svg>
  );
}
