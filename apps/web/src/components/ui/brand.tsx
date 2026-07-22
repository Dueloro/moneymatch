/** Dueloro brand mark + wordmark, and the ambient glow backdrop. */

export function TriangleMark({ className = 'h-7 w-7' }: { className?: string }) {
  return (
    <span
      className={`grid place-items-center rounded-lg bg-panel-raised ring-1 ring-hairline ${className}`}
    >
      <svg
        viewBox="0 0 24 24"
        className="h-[56%] w-[56%] text-green"
        fill="currentColor"
        aria-hidden
      >
        <path d="M12 4.2 20.5 19.2a1 1 0 0 1-.87 1.5H4.37a1 1 0 0 1-.87-1.5L12 4.2Z" />
      </svg>
    </span>
  );
}

export function Logo({
  markClassName = 'h-7 w-7',
  wordClassName = 'text-sm font-semibold tracking-tight',
}: {
  markClassName?: string;
  wordClassName?: string;
}) {
  return (
    <div className="flex items-center gap-2">
      <TriangleMark className={markClassName} />
      <span className={wordClassName}>Dueloro</span>
    </div>
  );
}

/** Ambient lime glow painted behind content. Drop as the first child of a
 * `relative` container that has the base background; content paints on top. */
export function GlowBackdrop({ className = '' }: { className?: string }) {
  return (
    <div
      aria-hidden
      className={`pointer-events-none absolute inset-0 overflow-hidden ${className}`}
      style={{
        background:
          'radial-gradient(55% 40% at 85% -10%, rgba(198,244,64,0.12), transparent 60%), radial-gradient(45% 30% at -5% -5%, rgba(198,244,64,0.06), transparent 60%)',
      }}
    />
  );
}
