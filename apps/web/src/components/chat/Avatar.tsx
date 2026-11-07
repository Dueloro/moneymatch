const ACCENTS = ['#7fd4ff', '#f0a5ff', '#ffc46b', '#8ef0b0', '#ff9c8a'] as const;

function accentFor(name: string): string {
  let hash = 0;
  for (let i = 0; i < name.length; i += 1) {
    hash = (hash * 31 + name.charCodeAt(i)) >>> 0;
  }
  return ACCENTS[hash % ACCENTS.length];
}

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
  const accent = brand ? 'var(--green)' : accentFor(name);
  const box = size === 'sm' ? 'h-10 w-10 text-xs' : 'h-10 w-10 text-sm';

  return (
    <span className="relative inline-flex shrink-0">
      <span
        aria-hidden
        className={[
          box,
          'inline-flex items-center justify-center rounded-full border font-bold tracking-wide',
        ].join(' ')}
        style={{
          color: accent,
          borderColor: `color-mix(in srgb, ${accent} 55%, transparent)`,
          background: `radial-gradient(120% 120% at 30% 20%, color-mix(in srgb, ${accent} 22%, var(--panel-raised)), var(--panel-raised))`,
          boxShadow: `0 0 0 1px color-mix(in srgb, ${accent} 14%, transparent), 0 6px 18px -10px ${accent}`,
        }}
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
