import { useEffect, useState } from 'react';
import { useSearchParams } from 'react-router-dom';

import { FriendsPanel } from '../components/FriendsPanel';
import { LeaderboardPanel } from '../components/LeaderboardPanel';
import { SubTabs } from '../components/ui/SubTabs';
import { useInboxUnread } from '../hooks/useChat';
import { InboxPage } from './InboxPage';

type SocialTab = 'inbox' | 'leaderboard' | 'friends';
const TABS: SocialTab[] = ['inbox', 'leaderboard', 'friends'];

/** The Social section: Inbox, Leaderboard, and Friends under one nav entry.
 * Inbox leads and is the default tab — messages and notifications are what you
 * come here to check; the leaderboard is a browse. The notification bell
 * deep-links here via `?tab=inbox`; Friends' Message button adds
 * `&dm=<user_id>` to land in a specific thread. */
export function SocialPage() {
  const [params] = useSearchParams();
  const initial = params.get('tab');
  const [tab, setTab] = useState<SocialTab>(
    TABS.includes(initial as SocialTab) ? (initial as SocialTab) : 'inbox',
  );
  const inboxUnread = useInboxUnread();

  // Follow later `?tab=` changes too (the page stays mounted when another
  // surface links across, e.g. Friends → Message).
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
