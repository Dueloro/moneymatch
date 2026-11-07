import type { ProfileSnapshot } from '../hooks/useLinks';

// Mirror of the clock the server creates the Lichess game with
// (apps/api adapters/chess_lichess.py: _CLOCK_FOR_SPEED, no increment).
const CLOCK_SECONDS: Record<string, number> = {
  bullet: 60,
  blitz: 300,
  rapid: 600,
  classical: 1800,
};

export function speedName(speed: string): string {
  return speed.charAt(0).toUpperCase() + speed.slice(1);
}

/** "5+0", or null when the server's clock for this speed isn't known. */
export function clockLabel(speed: string): string | null {
  const s = CLOCK_SECONDS[speed];
  return s ? `${s / 60}+0` : null;
}

/** "Blitz 5+0". */
export function timeControlLabel(speed: string | null | undefined): string {
  if (!speed) return '';
  const clock = clockLabel(speed);
  return clock ? `${speedName(speed)} ${clock}` : speedName(speed);
}

export function defaultSpeed(speeds: string[]): string | undefined {
  return speeds.includes('blitz') ? 'blitz' : (speeds[1] ?? speeds[0]);
}

export interface SpeedRating {
  rating: number;
  /** The speed the rating actually comes from (differs when there are no games at `speed`). */
  from: string | null;
  provisional: boolean;
}

/** Mirror of the server's pairing rating (services/skill_rating.py: rating_for_speed). */
export function ratingForSpeed(
  profile: ProfileSnapshot | null | undefined,
  speed: string | undefined,
): SpeedRating | null {
  if (!profile) return null;
  const formats = profile.formats ?? [];
  const exact = formats.find((f) => f.speed === speed);
  const pick =
    exact ??
    (formats.length ? formats.reduce((a, b) => (b.games > a.games ? b : a)) : null);
  if (pick)
    return { rating: pick.rating, from: pick.speed, provisional: pick.provisional };
  return profile.rating != null
    ? { rating: profile.rating, from: null, provisional: false }
    : null;
}
