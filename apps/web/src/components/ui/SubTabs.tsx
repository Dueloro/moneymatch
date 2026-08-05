import { Badge } from './Badge';
import { Segmented } from './Segmented';

/**
 * Section sub-tabs. Now a thin wrapper over `Segmented` so the app has one
 * "pick one of a few" control instead of three lookalikes (the old underlined
 * tabs, the entry presets, and the mode switcher). The API is unchanged, so
 * every caller keeps working.
 */
export function SubTabs<T extends string>({
  tabs,
  active,
  onSelect,
}: {
  /** `badge` renders an unread count next to the label (0/undefined hides it). */
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
