import { Link } from 'react-router-dom';

import { EmptyState } from './EmptyState';
import { PillButton } from './PillButton';

/** Shown on Play / Pools / Tournament when the selected game is in the catalog
 * but not yet playable (no adapter). Keeps the game in the switcher while it's
 * "coming soon", and points elsewhere so the screen isn't a dead end. */
export function ComingSoonPanel({ name }: { name: string }) {
  return (
    <EmptyState
      title={`${name} is coming soon`}
      subline={`We're building ${name} matches. It's in your bar so you're ready the moment it goes live. We will let you know.`}
      action={
        <Link to="/pools">
          <PillButton>Back to your games</PillButton>
        </Link>
      }
    />
  );
}
