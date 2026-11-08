/** The lime ring + check that marks points won (decorative). */
export function WinMark({ className = '' }: { className?: string }) {
  return (
    <span
      aria-hidden
      className={`grid h-12 w-12 place-items-center rounded-full bg-green/10 ring-1 ring-inset ring-green/50 ${className}`}
    >
      <svg viewBox="0 0 24 24" className="h-6 w-6" fill="none">
        <path
          d="M5 12.5 10 17l9-10"
          stroke="var(--green)"
          strokeWidth={2.5}
          strokeLinecap="round"
          strokeLinejoin="round"
          className="mm-draw-check"
        />
      </svg>
    </span>
  );
}

/** A neutral bar for a loss, draw or refund: no red wash, nothing to celebrate. */
export function QuietMark({ className = '' }: { className?: string }) {
  return (
    <span
      aria-hidden
      className={`grid h-12 w-12 place-items-center rounded-full border border-hairline bg-panel-raised ${className}`}
    >
      <span className="h-0.5 w-5 rounded-full bg-text-tertiary" />
    </span>
  );
}
