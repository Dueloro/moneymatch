import { useLocation, useNavigate } from 'react-router-dom';

import { Segmented } from './ui/Segmented';
import { PLAY_MODES } from './ui/nav';

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
