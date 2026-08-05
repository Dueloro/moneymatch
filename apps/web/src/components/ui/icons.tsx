/** Shared inline stroke icons (currentColor). Kept tiny and dependency-free. */

/** One glyph per primary destination, shared by the sidebar and the mobile tab
 * bar so the two navigations read as the same thing at both sizes. */
const NAV_GLYPHS: Record<string, JSX.Element> = {
  '/pools': (
    <path
      d="M13 2 4 14h7l-1 8 9-12h-7l1-8Z"
      strokeLinejoin="round"
      strokeLinecap="round"
    />
  ),
  '/activity': (
    <path d="M3 12h4l2 6 4-14 2 8h6" strokeLinejoin="round" strokeLinecap="round" />
  ),
  '/social': (
    <path
      d="M8.5 11a3 3 0 1 0 0-6 3 3 0 0 0 0 6Zm7.5 0a2.5 2.5 0 1 0 0-5 2.5 2.5 0 0 0 0 5ZM3 19v-1a4 4 0 0 1 4-4h3a4 4 0 0 1 4 4v1m1-5h1a4 4 0 0 1 4 4v1"
      strokeLinejoin="round"
      strokeLinecap="round"
    />
  ),
  '/wallet': (
    <path
      d="M3 7a2 2 0 0 1 2-2h12a2 2 0 0 1 2 2v10a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V7Zm14 4h-3a2 2 0 0 0 0 4h3"
      strokeLinejoin="round"
      strokeLinecap="round"
    />
  ),
  '/admin': (
    <path
      d="M12 3l7 3v5.5c0 4-2.9 6.8-7 8.5-4.1-1.7-7-4.5-7-8.5V6l7-3Z"
      strokeLinejoin="round"
      strokeLinecap="round"
    />
  ),
};

export function NavIcon({
  to,
  className = 'h-[22px] w-[22px]',
}: {
  to: string;
  className?: string;
}) {
  const glyph = NAV_GLYPHS[to];
  if (!glyph) return null;
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.7}
      className={className}
      aria-hidden
    >
      {glyph}
    </svg>
  );
}

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

export function MenuIcon({ className = 'h-4 w-4' }: { className?: string }) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.7}
      className={className}
      aria-hidden
    >
      <path d="M4 7h16M4 12h16M4 17h16" strokeLinecap="round" />
    </svg>
  );
}

export function ChevronDownIcon({ className = 'h-4 w-4' }: { className?: string }) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.8}
      className={className}
      aria-hidden
    >
      <path d="M6 9l6 6 6-6" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}
