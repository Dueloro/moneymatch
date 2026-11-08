import type { ProfileSnapshot } from '../hooks/useLinks';

/** The clock a speed's games are created with (the server publishes it per market). */
export interface SpeedClock {
  speed: string;
  limit_seconds: number;
  increment_seconds: number;
}

export function speedName(speed: string): string {
  return speed.charAt(0).toUpperCase() + speed.slice(1);
}

function minutes(seconds: number): string {
  return seconds % 60 === 0 ? String(seconds / 60) : (seconds / 60).toFixed(1);
}

/** "5+0", or null when the clock isn't known. */
export function clockLabel(clock: SpeedClock | null | undefined): string | null {
  return clock ? `${minutes(clock.limit_seconds)}+${clock.increment_seconds}` : null;
}

export function clockFor(
  speed: string | null | undefined,
  clocks: SpeedClock[] | null | undefined,
): SpeedClock | null {
  return clocks?.find((c) => c.speed === speed) ?? null;
}

/** "Blitz 5+0" (or just "Blitz" when the clock isn't known). */
export function timeControlLabel(
  speed: string | null | undefined,
  clock?: SpeedClock | null,
): string {
  if (!speed) return '';
  const label = clockLabel(clock);
  return label ? `${speedName(speed)} ${label}` : speedName(speed);
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
