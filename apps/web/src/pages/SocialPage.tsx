import { useEffect, useRef, useState } from 'react';
import { useSearchParams } from 'react-router-dom';

import { FriendsPanel } from '../components/FriendsPanel';
import { LeaderboardPanel } from '../components/LeaderboardPanel';
import { SubTabs } from '../components/ui/SubTabs';
import { useInboxUnread } from '../hooks/useChat';
import { useInboxBadge, useMarkInboxSeen } from '../hooks/useInbox';
import { usePageTitle } from '../hooks/usePageTitle';
import { InboxPage } from './InboxPage';

type SocialTab = 'inbox' | 'leaderboard' | 'friends';
const TABS: SocialTab[] = ['inbox', 'leaderboard', 'friends'];

export function SocialPage() {
  usePageTitle('Social');
  const [params] = useSearchParams();
  const initial = params.get('tab');
  const [tab, setTab] = useState<SocialTab>(
    TABS.includes(initial as SocialTab) ? (initial as SocialTab) : 'inbox',
  );
  const inboxUnread = useInboxUnread();
  const badge = useInboxBadge();
  const seen = useMarkInboxSeen();
  const stamped = useRef(false);

  // Being on Social is "seen": stamp on mount, and again if something new arrives
  // while the page is open. Per-item unread dots stay until each item is opened.
  useEffect(() => {
    if (stamped.current && badge === 0) return;
    stamped.current = true;
    seen.mutate();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [badge]);

  useEffect(() => {
    if (TABS.includes(initial as SocialTab)) setTab(initial as SocialTab);
  }, [initial]);

  return (
    <div>
      <div className="mb-6">
        <SubTabs<SocialTab>
          tabs={[
            { key: 'inbox', label: 'Inbox', badge: inboxUnread },
            { key: 'leaderboard', label: 'Leaderboard' },
            { key: 'friends', label: 'Friends' },
          ]}
          active={tab}
          onSelect={setTab}
        />
      </div>
      {tab === 'leaderboard' && <LeaderboardPanel />}
      {tab === 'friends' && <FriendsPanel />}
      {tab === 'inbox' && <InboxPage />}
    </div>
  );
}
