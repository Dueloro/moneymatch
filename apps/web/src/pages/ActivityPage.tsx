import { EmptyState } from '../components/ui/EmptyState';

export function ActivityPage() {
  return (
    <div>
      <h1 className="mb-6 text-2xl font-bold">Activity</h1>
      <EmptyState
        title="Nothing here yet"
        subline="Your matches, pools, and tournaments will show up here."
      />
    </div>
  );
}
