import { useLocation, useNavigate } from 'react-router-dom';

import { Segmented } from './ui/Segmented';
import { PLAY_MODES } from './ui/nav';

/**
 * The contest-mode switcher at the top of the Play surface: Solo pools,
 * Tournament, Head-to-head. These used to be three separate nav entries, which
 * spent half the primary navigation on one act and left the mobile bar with six
 * cramped tabs (16-ui-revamp-plan §5).
 *
 * Routes are unchanged, so every deep link and redirect still resolves.
 */
export function ModeSwitcher() {
  const navigate = useNavigate();
  const { pathname } = useLocation();
  const value = PLAY_MODES.some((m) => m.to === pathname) ? pathname : PLAY_MODES[0].to;

  return (
    <Segmented
      ariaLabel="Contest type"
      options={PLAY_MODES.map((m) => ({ value: m.to, label: m.label }))}
      value={value}
      onChange={(to) => navigate(to)}
    />
  );
}
