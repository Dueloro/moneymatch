/** Shared inline stroke icons (currentColor). Kept tiny and dependency-free. */

export function BellIcon({ className = 'h-[18px] w-[18px]' }: { className?: string }) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.7}
      className={className}
      aria-hidden
    >
      <path
        d="M6 8a6 6 0 0 1 12 0c0 5 2 6 2 6H4s2-1 2-6Zm4 10a2 2 0 0 0 4 0"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}
