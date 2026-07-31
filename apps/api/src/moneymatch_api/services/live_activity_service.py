"""Best-effort *live* view for in-flight Activity cards (07-phase-4 follow-on).

The settlement worker computes a "what's happening right now" snapshot for each
in-flight pool and head-to-head match on a slow cadence and upserts it into
`live_snapshots`; the `/activity` request path only ever **reads** that cache, so
a page load never blocks on a host call (same posture as the tournament
`standings_cache`). Tournaments already cache live standings, so their live view
is derived from that cache at read time — no row is stored here for them.

Every value here is a server-fetched host read normalized through the adapter —
never client input, never money. Fidelity is whatever the host API allows: a
brokered chess game is genuinely live (plies played, whose turn); the stat-race
titles (CS2/Dota/PUBG) surface the latest in-window match, which is the same
evidence settlement will grade.

A stored snapshot is **participant-neutral** (it holds every member/seat keyed by
user id); `view_for` orients it to a single viewer — "you vs opp", "your bar",
"your colour" — so one cached row serves everyone in the contest.
"""

from __future__ import annotations

import uuid
from typing import Any

import structlog

from ..adapters import registry
from ..adapters.base import GameFilters, NormGame
from ..constants import metric_label
from ..models.play import Match, MatchPlayer
from ..models.pools import SoloEntry, SoloPool
from ..models.tournaments import Tournament, TournamentEntry
from ..services.hosts.errors import HostError
from . import markets

log = structlog.get_logger(__name__)


async def _window_games(
    game: str, host_account_id: str, starts_ms: int, ends_ms: int
) -> list[NormGame] | None:
    """The account's finished games inside `[starts_ms, ends_ms]`, in adapter order
    (oldest-first). `None` on a host outage or an unregistered game — the card
    then shows an honest "can't read right now" rather than a wrong number."""
    try:
        adapter = registry.get(game)
    except ValueError:
        return None
    try:
        games = await adapter.poll_eligible_games(
            host_account_id, starts_ms, GameFilters(rated_only=False)
        )
    except HostError:
        log.info("live.host_unavailable", game=game, host=host_account_id)
        return None
    return [g for g in games if starts_ms <= g.created_at_ms <= ends_ms]


def _ms(dt) -> int:
    return int(dt.timestamp() * 1000)


# ---------------------------------------------------------------------------
# Snapshot builders (worker side) — participant-neutral, cached as-is.
# ---------------------------------------------------------------------------


async def build_pool_snapshot(
    pool: SoloPool, entries: list[SoloEntry]
) -> dict[str, Any]:
    """Each member's progress toward the shared `room_bar`, keyed by user id.

    The qualifying match is the member's **first** in-window match (what grading
    uses), so once they've played, the card shows the value that will settle."""
    starts_ms, ends_ms = _ms(pool.window_starts_at), _ms(pool.window_ends_at)
    members: dict[str, Any] = {}
    for entry in entries:
        games = await _window_games(
            pool.game, entry.host_account_id, starts_ms, ends_ms
        )
        if games is None:
            members[str(entry.user_id)] = {"status": "unavailable"}
            continue
        qualifying = next((g for g in games if pool.metric in g.metrics), None)
        if qualifying is None:
            members[str(entry.user_id)] = {"status": "waiting", "matches": len(games)}
            continue
        value = qualifying.metrics[pool.metric]
        cleared = value >= pool.room_bar
        members[str(entry.user_id)] = {
            "status": "cleared" if cleared else "missed",
            "current": round(value, 2),
            "cleared": cleared,
            "matches": len(games),
        }
    return {
        "kind": "pool",
        "metric": pool.metric,
        "label": metric_label(pool.metric),
        "target": round(pool.room_bar, 2),
        "members": members,
    }


async def build_match_snapshot(
    match: Match, seats: list[MatchPlayer]
) -> dict[str, Any] | None:
    """A neutral H2H snapshot: chess board state, or both seats' stat/result.

    `None` while the match has no live window yet (not paired). Chess is truly
    live; the coordinated titles surface each seat's first in-window match."""
    if match.matched_at is None or match.window_ends_at is None:
        return None
    market = markets.get(match.game, match.market)
    kind = market.kind if market else ""
    label = metric_label(market.metric) if (market and market.metric) else match.market

    # Brokered chess: a single live board covers both seats.
    if match.brokered and match.host_game_id:
        adapter = registry.get(match.game)
        handles = [s.host_account_id for s in seats]
        try:
            live = await adapter.live_match(match.host_game_id, handles)
        except HostError:
            live = None
        if not live:
            return {"kind": "match", "format": "chess", "status": "waiting"}
        colors = {str(s.user_id): (s.color or "") for s in seats}
        return {
            "kind": "match",
            "format": "chess",
            "status": "finished" if live["finished"] else "live",
            "moves": live["moves"],
            "plies": live["plies"],
            "turn": live["turn"],  # "white" | "black" | null
            "winner": live["winner"],  # "white" | "black" | "draw" | null
            "colors": colors,
        }

    # Coordinated titles: each seat's first in-window match (what grading reads).
    starts_ms, ends_ms = _ms(match.matched_at), _ms(match.window_ends_at)
    metric = market.metric if market else None
    seat_views: dict[str, Any] = {}
    any_data = False
    for seat in seats:
        games = await _window_games(
            match.game, seat.host_account_id, starts_ms, ends_ms
        )
        if games is None:
            seat_views[str(seat.user_id)] = {"status": "unavailable"}
            continue
        first = games[0] if games else None
        if first is not None:
            any_data = True
        value = first.metrics.get(metric) if (first and metric) else None
        result = None
        if first is not None:
            if first.won:
                result = "won"
            else:
                result = "pending" if first.won is None else "lost"
        seat_views[str(seat.user_id)] = {
            "matches": len(games),
            "value": round(value, 2) if value is not None else None,
            "result": result,
        }
    fmt = "stat_race" if kind == "stat_race" else "win_next"
    return {
        "kind": "match",
        "format": fmt,
        "label": label,
        "status": "live" if any_data else "waiting",
        "seats": seat_views,
    }


# ---------------------------------------------------------------------------
# Read side — orient a stored/derived snapshot to one viewer.
# ---------------------------------------------------------------------------


def _pool_view(snapshot: dict[str, Any], viewer: uuid.UUID) -> dict[str, Any] | None:
    me = (snapshot.get("members") or {}).get(str(viewer))
    if not me:
        return None
    return {
        "kind": "pool",
        "label": snapshot.get("label"),
        "target": snapshot.get("target"),
        "status": me.get("status", "waiting"),
        "current": me.get("current"),
        "cleared": me.get("cleared"),
        "matches": me.get("matches", 0),
    }


def _match_view(snapshot: dict[str, Any], viewer: uuid.UUID) -> dict[str, Any] | None:
    fmt = snapshot.get("format")
    vid = str(viewer)
    if fmt == "chess":
        if snapshot.get("status") == "waiting":
            return {"kind": "match", "format": "chess", "status": "waiting"}
        colors = snapshot.get("colors") or {}
        your_color = colors.get(vid)
        turn = snapshot.get("turn")
        winner = snapshot.get("winner")
        result = None
        if winner == "draw":
            result = "draw"
        elif winner:
            result = "you" if winner == your_color else "opp"
        if turn is None:
            your_turn = None
        else:
            your_turn = "you" if turn == your_color else "opp"
        return {
            "kind": "match",
            "format": "chess",
            "status": snapshot.get("status"),
            "moves": snapshot.get("moves"),
            "your_color": your_color,
            "turn": your_turn,
            "result": result,
        }

    # stat_race / win_next
    seats = snapshot.get("seats") or {}
    you = seats.get(vid) or {}
    opp = next((v for k, v in seats.items() if k != vid), {}) or {}
    view: dict[str, Any] = {
        "kind": "match",
        "format": fmt,
        "label": snapshot.get("label"),
        "status": snapshot.get("status", "waiting"),
    }
    if fmt == "stat_race":
        yv, ov = you.get("value"), opp.get("value")
        leader = None
        if yv is not None and ov is not None:
            leader = "you" if yv > ov else ("opp" if ov > yv else "tie")
        view.update({"you": yv, "opp": ov, "leader": leader})
    else:  # win_next
        view.update({"you": you.get("result"), "opp": opp.get("result")})
    return view


def tournament_view(
    tournament: Tournament, entry: TournamentEntry
) -> dict[str, Any] | None:
    """The viewer's live standings row, derived from `standings_cache`."""
    rows = (tournament.standings_cache or {}).get("rows") or []
    me = next((r for r in rows if r.get("user_id") == str(entry.user_id)), None)
    label = metric_label(tournament.ranking_metric)
    if not me or me.get("score") is None:
        return {
            "kind": "tournament",
            "label": label,
            "status": "waiting",
            "score": None,
            "rank": None,
            "matches": me.get("matches", 0) if me else 0,
            "field": len(rows) or tournament.field_size,
        }
    return {
        "kind": "tournament",
        "label": label,
        "status": "scoring",
        "score": round(me["score"], 2),
        "rank": me.get("rank"),
        "matches": me.get("matches", 0),
        "field": len(rows),
        "score_matches": tournament.score_matches,
    }


def view_for(
    ref_type: str, snapshot: dict[str, Any], viewer: uuid.UUID
) -> dict[str, Any] | None:
    """Orient a stored neutral snapshot (`pool` | `match`) to one viewer."""
    if not snapshot:
        return None
    if ref_type == "pool":
        return _pool_view(snapshot, viewer)
    if ref_type == "match":
        return _match_view(snapshot, viewer)
    return None
