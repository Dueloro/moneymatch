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
  tabs: { key: T; label: string }[];
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
            '-mb-px border-b-2 pb-2 text-sm font-semibold transition',
            tab.key === active
              ? 'border-green text-text'
              : 'border-transparent text-text-secondary hover:text-text',
          ].join(' ')}
        >
          {tab.label}
        </button>
      ))}
    </div>
  );
}
