import { styles } from './adminStyles';

const BAR = { background: '#e4e4e7', borderRadius: 3, height: 14 } as const;

export function AdminLoading({ bare = false }: { bare?: boolean }) {
  return (
    <div
      style={bare ? { marginTop: 16 } : styles.page}
      aria-busy
      data-testid="admin-skeleton"
    >
      <span className="sr-only">Loading</span>
      <div className="animate-pulse" style={{ display: 'grid', gap: 8, maxWidth: 480 }}>
        <div style={{ ...BAR, width: '40%' }} />
        <div style={BAR} />
        <div style={BAR} />
      </div>
    </div>
  );
}

export function AdminError({
  what,
  onRetry,
  bare = false,
}: {
  what: string;
  onRetry: () => void;
  bare?: boolean;
}) {
  return (
    <div style={bare ? { marginTop: 16 } : styles.page} role="alert">
      <p style={styles.alert}>Failed to load {what}.</p>
      <button style={styles.button} onClick={onRetry}>
        Retry
      </button>
    </div>
  );
}
