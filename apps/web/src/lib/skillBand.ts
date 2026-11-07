// Mirror of the server's pairing band (apps/api constants.py: CHESS_BASE_BAND,
// CHESS_BAND_GROWTH_PER_SEC, CHESS_MAX_BAND; services/matchmaking.py: _chess_band).
export const BASE_BAND = 100;
export const BAND_GROWTH_PER_SEC = 12;
export const MAX_BAND = 800;

/** Half-width of the Elo band after `seconds` in the queue. */
export function bandAt(seconds: number): number {
  return Math.floor(
    Math.min(MAX_BAND, BASE_BAND + Math.max(0, seconds) * BAND_GROWTH_PER_SEC),
  );
}

export function bandRange(rating: number, seconds: number): [number, number] {
  const band = bandAt(seconds);
  return [rating - band, rating + band];
}

/** "0:07", "1:32", "12:00". */
export function formatWaited(seconds: number): string {
  const s = Math.max(0, Math.floor(seconds));
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`;
}
