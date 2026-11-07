import { Badge } from './Badge';
import { Segmented } from './Segmented';

export function SubTabs<T extends string>({
  tabs,
  active,
  onSelect,
}: {
  tabs: { key: T; label: string; badge?: number }[];
  active: T;
  onSelect: (key: T) => void;
}) {
  return (
    <Segmented
      options={tabs.map((t) => ({ value: t.key, label: t.label, badge: t.badge }))}
      value={active}
      onChange={onSelect}
      renderBadge={(count) => <Badge count={count} />}
    />
  );
}
