export function TriangleMark({ className = 'h-7 w-7' }: { className?: string }) {
  return (
    <span
      className={`grid place-items-center rounded-inset bg-panel-raised ring-1 ring-hairline ${className}`}
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
      <span className={wordClassName}>Money Match</span>
    </div>
  );
}
