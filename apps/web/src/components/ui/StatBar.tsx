import type { ReactNode } from 'react';

/**
 * Horizontal cells of tiny uppercase label over a bold value — the Wallet
 * stat bar (Available / In escrow / Lifetime) and stat grids (02-design §10).
 */
export function StatBar({ cells }: { cells: { label: string; value: ReactNode }[] }) {
  return (
    <div className="flex divide-x divide-hairline rounded-card border border-hairline">
      {cells.map((cell) => (
        <div key={cell.label} className="flex-1 px-4 py-3">
          <div className="text-[11px] uppercase tracking-wide text-text-secondary">
            {cell.label}
          </div>
          <div className="mt-1 text-lg font-bold tabular-nums">{cell.value}</div>
        </div>
      ))}
    </div>
  );
}
