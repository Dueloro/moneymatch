// Inline styles for the admin surface. Deliberately plain and dense — the admin
// tools do NOT follow the consumer design system (09-phase-6 · deliverable 2).
import type { CSSProperties } from 'react';

export const styles: Record<string, CSSProperties> = {
  page: {
    padding: 16,
    fontFamily: 'ui-monospace, SFMono-Regular, Menlo, monospace',
    fontSize: 13,
  },
  h1: { fontSize: 16, fontWeight: 700, margin: '0 0 12px' },
  table: { width: '100%', borderCollapse: 'collapse' },
  th: {
    textAlign: 'left',
    borderBottom: '1px solid #999',
    padding: '4px 8px',
    background: '#f2f2f2',
    fontWeight: 600,
  },
  td: { borderBottom: '1px solid #ddd', padding: '4px 8px', verticalAlign: 'top' },
  button: {
    border: '1px solid #888',
    background: '#eee',
    padding: '2px 8px',
    cursor: 'pointer',
    fontSize: 12,
  },
  input: { border: '1px solid #888', padding: '3px 6px', fontSize: 13 },
  alert: { color: '#b00', fontWeight: 700 },
  ok: { color: '#080' },
  pre: {
    background: '#f7f7f7',
    border: '1px solid #ddd',
    padding: 8,
    overflow: 'auto',
    fontSize: 12,
  },
};
