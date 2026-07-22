import { useState } from 'react';
import { useSearchParams } from 'react-router-dom';

import { FriendsPanel } from '../components/FriendsPanel';
import { LeaderboardPanel } from '../components/LeaderboardPanel';
import { SubTabs } from '../components/ui/SubTabs';
import { InboxPage } from './InboxPage';

type SocialTab = 'leaderboard' | 'friends' | 'inbox';
const TABS: SocialTab[] = ['leaderboard', 'friends', 'inbox'];

/** The Social section: Leaderboard, Friends, and Inbox under one nav entry. The
 * notification bell deep-links here via `?tab=inbox`. */
export function SocialPage() {
  const [params] = useSearchParams();
  const initial = params.get('tab');
  const [tab, setTab] = useState<SocialTab>(
    TABS.includes(initial as SocialTab) ? (initial as SocialTab) : 'leaderboard',
  );

  return (
    <div>
      <div className="mb-6">
        <SubTabs<SocialTab>
          tabs={[
            { key: 'leaderboard', label: 'Leaderboard' },
            { key: 'friends', label: 'Friends' },
            { key: 'inbox', label: 'Inbox' },
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
