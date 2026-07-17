"""Seeded competitive leaderboard (roadmap §3 — Phase 2 retention surface).

Ranked by **ROI / record, never raw dollars won** (overview/roadmap §3.1): a
big bankroll grinding break-even contests should not top the board. In the demo
there is only one real player, so the server seeds a field of bot competitors
with plausible records; the client merges in the signed-in user's own demo
record (computed from their local history) and re-ranks the whole field by ROI.

Pure + deterministic (fixed seed) so the board is stable across refreshes.
"""

from __future__ import annotations

import random

from _lib.schemas import LeaderboardEntry

# Stable handles for the seeded field (shared spirit with the bot pools).
_BOT_HANDLES = [
    "knightfork", "enpassant", "pawnstorm", "zugzwanger", "aerialace",
    "elixirgod", "boostking", "skywarden", "tiltproof", "cleansheet",
    "rookrunner", "ohko", "deepfianchetto", "timescramble", "luftbahn",
]

_SEED = 20260629  # fixed → the board doesn't reshuffle on every refresh

_round2 = lambda x: round(x, 2)  # noqa: E731


def _make_entry(handle: str, rng: random.Random) -> LeaderboardEntry:
    contests = rng.randint(12, 90)
    win_rate = round(rng.uniform(0.38, 0.66), 3)
    wins = round(contests * win_rate)
    avg_entry = rng.choice([5.0, 10.0, 25.0])
    staked = _round2(contests * avg_entry)
    # ROI centered slightly negative (the rake is a headwind) with real spread.
    roi = round(rng.uniform(-0.25, 0.45), 3)
    net = _round2(staked * roi)
    return LeaderboardEntry(
        player_id=f"bot_{handle}",
        display_name=handle,
        is_bot=True,
        contests=contests,
        wins=wins,
        win_rate=round(wins / contests, 3) if contests else 0.0,
        staked=staked,
        net=net,
        roi=roi,
    )


def generate_leaderboard(rng: random.Random | None = None) -> list[LeaderboardEntry]:
    """Seeded bot field, best ROI first. The client adds the user + re-ranks."""
    r = rng or random.Random(_SEED)
    entries = [_make_entry(h, r) for h in _BOT_HANDLES]
    entries.sort(key=lambda e: e.roi, reverse=True)
    return entries
