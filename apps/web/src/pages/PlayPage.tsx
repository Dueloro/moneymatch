import { EmptyState } from '../components/ui/EmptyState';

export function PlayPage() {
  return (
    <div>
      <h1 className="mb-6 text-2xl font-bold">Play</h1>
      <EmptyState
        title="Pick a stat to start"
        subline="Markets, the wager slip, and matchmaking arrive in Phase 3."
      />
    </div>
  );
}
