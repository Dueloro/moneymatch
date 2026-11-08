function initials(name: string): string {
  const words = name
    .trim()
    .split(/[\s_.-]+/)
    .filter(Boolean);
  if (words.length === 0) return '?';
  if (words.length === 1) return words[0].slice(0, 2).toUpperCase();
  return (words[0][0] + words[1][0]).toUpperCase();
}

export function Avatar({
  name,
  online = false,
  showPresence = false,
  brand = false,
  size = 'md',
}: {
  name: string;
  online?: boolean;
  showPresence?: boolean;
  brand?: boolean;
  size?: 'sm' | 'md';
}) {
  const box = size === 'sm' ? 'h-10 w-10 text-xs' : 'h-10 w-10 text-sm';

  return (
    <span className="relative inline-flex shrink-0">
      <span
        aria-hidden
        className={[
          box,
          'inline-flex items-center justify-center rounded-full border font-bold tracking-wide',
          brand
            ? 'border-line-strong bg-action text-bg'
            : 'border-hairline bg-panel-raised text-text-secondary',
        ].join(' ')}
      >
        {initials(name)}
      </span>
      {showPresence && (
        <span
          aria-label={online ? 'online' : 'offline'}
          className={[
            'absolute -bottom-0.5 -right-0.5 h-3.5 w-3.5 rounded-full border-2 border-bg',
            online ? 'bg-live' : 'bg-hairline',
          ].join(' ')}
        />
      )}
    </span>
  );
}
