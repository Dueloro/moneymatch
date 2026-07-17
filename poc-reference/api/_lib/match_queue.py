"""In-memory matchmaking queue for real two-player head-to-head (roadmap Phase 1).

A single server process owns the queue and the live matches, so two browser
sessions hitting the same backend get paired against each other. State is
in-memory: it is intentionally simple for the demo and single-instance — the
production swap is Redis/Postgres, but the queue/pairing/lifecycle logic here is
exactly what that would run.

Flow: ``enqueue`` pairs a ticket with a compatible waiting one (same game /
format / entry, rating within a band that widens with wait time) into a PENDING
match. Both players ``confirm`` (escrow client-side); the route then brokers the
game (chess) or leaves it coordinated (CS2/Dota) and ``activate``s it. A poller
``finalize``s once the shared host match resolves.

The pairing + lifecycle functions are pure (no I/O) so they unit-test cleanly;
the network brokering + result grading live in the route + adapters.
"""

from __future__ import annotations

import time
import uuid
from typing import Optional

from _lib import skill_rating
from _lib.schemas import Match, MatchPlayer, QueueRequest, QueueResponse

# player_id -> waiting ticket (dict). One ticket per player.
_tickets: dict[str, dict] = {}
# match_id -> Match
_matches: dict[str, Match] = {}
# player_id -> match_id (their current PENDING/ACTIVE match)
_player_match: dict[str, str] = {}

# Rating band starts tight and widens with wait time (seconds) so a lonely queue
# still pairs eventually (roadmap: "tolerance that widens over time").
_BASE_BAND = 100
_BAND_GROWTH_PER_SEC = 12
_MAX_BAND = 800

_now = lambda: time.time()  # noqa: E731
_round2 = lambda x: round(x, 2)  # noqa: E731


def reset() -> None:
    """Clear all state (tests / demo reset)."""
    _tickets.clear()
    _matches.clear()
    _player_match.clear()


def _band(age_sec: float) -> int:
    return int(min(_MAX_BAND, _BASE_BAND + age_sec * _BAND_GROWTH_PER_SEC))


def _econ(entry: float) -> tuple[float, float, float, float]:
    rake_pct = skill_rating.rake_for("win_h2h")
    pot = _round2(entry * 2)
    rake = _round2(pot * rake_pct)
    prize = _round2(pot - rake)
    return rake_pct, pot, prize, rake


def _compatible(ticket: dict, req: QueueRequest, now: float) -> bool:
    """A waiting ticket is a match for the incoming request?"""
    if ticket["player_id"] == req.player_id:
        return False
    if (ticket["game"], ticket["speed"], ticket["format"]) != (req.game, req.speed, req.format):
        return False
    if _round2(ticket["entry"]) != _round2(req.entry):
        return False
    # Use the wider of the two players' bands (older ticket has grown its tolerance).
    band = max(_band(now - ticket["created_at"]), _band(0))
    return abs(ticket["rating"] - req.rating) <= band


def enqueue(req: QueueRequest) -> QueueResponse:
    """Pair with a compatible waiting player, else join the queue."""
    now = _now()

    # Already in a live match? Return it (idempotent re-poll).
    existing = _player_match.get(req.player_id)
    if existing and existing in _matches:
        return QueueResponse(status="matched", match=_matches[existing])

    # Try to pair with the oldest compatible waiting ticket.
    for tid, ticket in sorted(_tickets.items(), key=lambda kv: kv[1]["created_at"]):
        if _compatible(ticket, req, now):
            del _tickets[tid]
            _tickets.pop(req.player_id, None)
            match = _make_match(ticket, req, now)
            _matches[match.id] = match
            _player_match[ticket["player_id"]] = match.id
            _player_match[req.player_id] = match.id
            return QueueResponse(status="matched", match=match)

    # No match — (re)register this player's ticket.
    _tickets[req.player_id] = {
        "player_id": req.player_id,
        "display_name": req.display_name,
        "rating": req.rating,
        "game": req.game,
        "speed": req.speed,
        "format": req.format,
        "entry": _round2(req.entry),
        "created_at": _tickets.get(req.player_id, {}).get("created_at", now),
    }
    return QueueResponse(status="searching")


def _make_match(ticket: dict, req: QueueRequest, now: float) -> Match:
    rake_pct, pot, prize, rake = _econ(req.entry)
    brokered = req.game == "chess.lichess"
    # Brokered chess assigns colors (ticket = white, requester = black).
    players = [
        MatchPlayer(
            player_id=ticket["player_id"], display_name=ticket["display_name"],
            rating=ticket["rating"], color="white" if brokered else None,
        ),
        MatchPlayer(
            player_id=req.player_id, display_name=req.display_name,
            rating=req.rating, color="black" if brokered else None,
        ),
    ]
    return Match(
        id=uuid.uuid4().hex, game=req.game, speed=req.speed, format=req.format,
        entry=_round2(req.entry), rake_pct=rake_pct, pot=pot, prize=prize, rake=rake,
        brokered=brokered, players=players, state="PENDING", created_at=now,
    )


def poll(player_id: str) -> QueueResponse:
    """Where does this player stand — matched, still searching, or idle?"""
    mid = _player_match.get(player_id)
    if mid and mid in _matches:
        return QueueResponse(status="matched", match=_matches[mid])
    if player_id in _tickets:
        return QueueResponse(status="searching")
    return QueueResponse(status="idle")


def get(match_id: str) -> Optional[Match]:
    return _matches.get(match_id)


def confirm(match_id: str, player_id: str) -> Optional[Match]:
    m = _matches.get(match_id)
    if not m or m.state != "PENDING":
        return m
    for p in m.players:
        if p.player_id == player_id:
            p.confirmed = True
    return m


def both_confirmed(m: Match) -> bool:
    return all(p.confirmed for p in m.players)


def activate(m: Match, broker: Optional[dict], now: Optional[float] = None) -> Match:
    """Move a fully-confirmed match to ACTIVE, wiring in the brokered game if any.

    ``broker`` (chess): ``{"game_id": str, "urls": {"white": url, "black": url}}``.
    """
    if broker:
        m.host_game_id = broker.get("game_id")
        urls = broker.get("urls") or {}
        for p in m.players:
            p.play_url = urls.get(p.color or "")
    m.state = "ACTIVE"
    m.matched_at = now or _now()
    m.progress = "Game on — play your match." if m.brokered else "Add your opponent and start a match."
    return m


def cancel(player_id: str) -> Optional[Match]:
    """Leave the queue, or decline / abort a pending match (refund both)."""
    _tickets.pop(player_id, None)
    mid = _player_match.get(player_id)
    if not mid or mid not in _matches:
        return None
    m = _matches[mid]
    if m.state in ("PENDING", "ACTIVE"):
        m.state = "CANCELED"
        m.outcome = "refunded"
        m.resolved_at = _now()
        m.progress = "Match canceled — entries refunded."
        for p in m.players:
            p.payout = m.entry
    for p in m.players:
        _player_match.pop(p.player_id, None)
    return m


def finalize(m: Match, winner_id: Optional[str], now: Optional[float] = None) -> Match:
    """Settle a resolved match. ``winner_id`` None ⇒ draw/void → refund both."""
    ts = now or _now()
    if winner_id is None:  # draw or unverifiable → refund, no rake
        m.state = "CANCELED"
        m.outcome = "refunded"
        for p in m.players:
            p.payout = m.entry
        m.progress = "Drawn — entries refunded."
    else:
        m.state = "SETTLED"
        m.outcome = "settled"
        m.winner_id = winner_id
        for p in m.players:
            p.payout = m.prize if p.player_id == winner_id else 0.0
        m.progress = "Settled."
    m.resolved_at = ts
    for p in m.players:
        _player_match.pop(p.player_id, None)
    return m
