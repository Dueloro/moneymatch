"""Live match tracker for CS2 (FaceIt) and Dota 2 (OpenDota).

FaceIt and OpenDota have no move-by-move stream like Lichess, so the spectator
analog here is a compact summary of the player's current / most-recent match:
the result headline, status, a link to the live match room, and a few stat
rows. Pure parsing (no I/O); the route does the fetch.
"""

from __future__ import annotations

from typing import Optional

from _lib.schemas import MatchStat, MatchTrackerResponse


def unavailable(message: str) -> MatchTrackerResponse:
    return MatchTrackerResponse(available=False, message=message)


def _mmss(seconds: int) -> str:
    return f"{seconds // 60}:{seconds % 60:02d}"


def parse_faceit(player_id: str, item: Optional[dict]) -> MatchTrackerResponse:
    """Summarize a FaceIt CS2 match-history item for ``player_id``."""
    if not item:
        return unavailable("No recent CS2 match to track yet — play one on FaceIt.")

    teams = item.get("teams") or {}
    my_faction: Optional[str] = None
    for faction, info in teams.items():
        if any(p.get("player_id") == player_id for p in (info or {}).get("players") or []):
            my_faction = faction
            break

    results = item.get("results") or {}
    winner = results.get("winner")
    score = results.get("score") or {}
    finished = item.get("status") == "finished"

    result: Optional[str] = None
    if my_faction and winner:
        result = "won" if winner == my_faction else "lost"

    other = "faction2" if my_faction == "faction1" else "faction1"
    my_score = score.get(my_faction)
    opp_score = score.get(other)
    headline = f"{my_score} – {opp_score}" if my_score is not None and opp_score is not None else "CS2 match"

    stats = []
    if result:
        stats.append(MatchStat(label="Result", value="Win" if result == "won" else "Loss"))
    if my_score is not None:
        stats.append(MatchStat(label="Score", value=f"{my_score}–{opp_score}"))
    region = item.get("region")
    if region:
        stats.append(MatchStat(label="Region", value=region))

    return MatchTrackerResponse(
        available=True,
        headline=headline,
        subtitle="Counter-Strike 2 · " + ("Final" if finished else "Live"),
        status="Final" if finished else "Live",
        result=result,
        url=item.get("faceit_url", "").replace("{lang}", "en") or None,
        stats=stats,
    )


def parse_dota(item: Optional[dict]) -> MatchTrackerResponse:
    """Summarize an OpenDota recent-match row for the linked player."""
    if not item:
        return unavailable("No recent Dota 2 match to track yet — play one to see it here.")

    slot = item.get("player_slot")
    radiant_win = item.get("radiant_win")
    is_radiant = slot is not None and slot < 128
    side = "Radiant" if is_radiant else "Dire"
    result: Optional[str] = None
    if radiant_win is not None and slot is not None:
        result = "won" if is_radiant == bool(radiant_win) else "lost"

    k = item.get("kills", 0); d = item.get("deaths", 0); a = item.get("assists", 0)
    kda = f"{k}/{d}/{a}"
    dur = _mmss(int(item.get("duration", 0)))
    match_id = item.get("match_id")

    headline = "Victory" if result == "won" else "Defeat" if result == "lost" else "Dota 2 match"
    return MatchTrackerResponse(
        available=True,
        headline=headline,
        subtitle=f"{side} · {kda} · {dur}",
        status="Final",
        result=result,
        url=f"https://www.opendota.com/matches/{match_id}" if match_id else None,
        stats=[
            MatchStat(label="Side", value=side),
            MatchStat(label="K/D/A", value=kda),
            MatchStat(label="Duration", value=dur),
        ],
    )
