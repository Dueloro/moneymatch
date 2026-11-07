import type { ReactNode } from 'react';

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
