import { EmptyState } from '../components/ui/EmptyState';

export function TournamentPage() {
  return (
    <div>
      <h1 className="mb-6 text-2xl font-bold">Tournament</h1>
      <EmptyState
        title="No tournaments yet"
        subline="Matchmade tournaments arrive in Phase 4."
      />
    </div>
  );
}
