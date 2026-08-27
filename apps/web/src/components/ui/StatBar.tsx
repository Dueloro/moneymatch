import type { ReactNode } from 'react';

/**
 * Horizontal cells of a small label over a bold value. Uses the one card radius
 * and border rule so it sits in the same system as everything else.
 */
export function StatBar({ cells }: { cells: { label: string; value: ReactNode }[] }) {
  return (
    <div className="flex divide-x divide-hairline rounded-card border border-hairline">
      {cells.map((cell) => (
        <div key={cell.label} className="flex-1 px-4 py-3">
          <div className="label-money">{cell.label}</div>
          <div className="mt-1 text-lg font-semibold tabular-nums">{cell.value}</div>
        </div>
      ))}
    </div>
  );
}
