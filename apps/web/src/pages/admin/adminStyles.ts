import type { CSSProperties } from 'react';

// Self-contained light theme: admin sits outside the consumer design system,
// so every colour is explicit and nothing inherits from the dark app body.
export const INK = '#111';
export const PAPER = '#fff';

export const styles: Record<string, CSSProperties> = {
  root: {
    minHeight: '100vh',
    background: PAPER,
    color: INK,
    colorScheme: 'light',
    fontFamily: 'ui-monospace, SFMono-Regular, Menlo, monospace',
  },
  page: { padding: 16, fontSize: 13 },
  h1: { fontSize: 16, fontWeight: 700, margin: '0 0 12px', color: INK },
  scroll: { overflowX: 'auto', maxWidth: '100%' },
  table: { width: '100%', borderCollapse: 'collapse', color: INK },
  th: {
    textAlign: 'left',
    borderBottom: '1px solid #71717a',
    padding: '4px 8px',
    background: '#f4f4f5',
    color: INK,
    fontWeight: 700,
    whiteSpace: 'nowrap',
  },
  td: { borderBottom: '1px solid #e4e4e7', padding: '4px 8px', verticalAlign: 'top' },
  button: {
    border: '1px solid #52525b',
    background: PAPER,
    color: INK,
    padding: '3px 10px',
    cursor: 'pointer',
    fontFamily: 'inherit',
    fontSize: 12,
    whiteSpace: 'nowrap',
  },
  input: {
    border: '1px solid #71717a',
    background: PAPER,
    color: INK,
    padding: '3px 6px',
    fontFamily: 'inherit',
    fontSize: 13,
    maxWidth: '100%',
    boxSizing: 'border-box',
  },
  alert: { color: '#b00', fontWeight: 700 },
  ok: { color: '#080' },
  pre: {
    background: '#f4f4f5',
    color: INK,
    border: '1px solid #e4e4e7',
    padding: 8,
    overflow: 'auto',
    fontSize: 12,
  },
};
