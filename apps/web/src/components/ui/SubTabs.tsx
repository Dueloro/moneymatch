/**
 * Section sub-tabs (02-design §5): the Tournament section's
 * Tournaments / Leaderboard / Friends switcher (design p.6, p.7). Active tab
 * gets a green underline.
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
    <div className="flex gap-6 border-b border-hairline" role="tablist">
      {tabs.map((tab) => (
        <button
          key={tab.key}
          role="tab"
          aria-selected={tab.key === active}
          onClick={() => onSelect(tab.key)}
          className={[
            '-mb-px flex items-center gap-2 border-b-2 pb-2 text-sm font-semibold transition',
            tab.key === active
              ? 'border-green text-text'
              : 'border-transparent text-text-secondary hover:text-text',
          ].join(' ')}
        >
          {tab.label}
          {!!tab.badge && (
            <span className="min-w-[1.25rem] rounded-pill bg-green px-1.5 py-0.5 text-center text-[10px] font-bold text-black">
              {tab.badge > 99 ? '99+' : tab.badge}
            </span>
          )}
        </button>
      ))}
    </div>
  );
}
