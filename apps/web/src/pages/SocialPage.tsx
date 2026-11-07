import { useEffect, useState } from 'react';
import { useSearchParams } from 'react-router-dom';

import { FriendsPanel } from '../components/FriendsPanel';
import { LeaderboardPanel } from '../components/LeaderboardPanel';
import { SubTabs } from '../components/ui/SubTabs';
import { useInboxUnread } from '../hooks/useChat';
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
