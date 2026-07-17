"""Multi-entrant tournament engine — ranked prize pool (roadmap §3, Phase 2).

N players each pay an equal entry into a shared pool for a game + a ranking
standard. Everyone plays; the platform ranks entrants by an objective metric
(from API telemetry) and the **top finishers split the pool minus a fixed
platform rake** per a declared ``prize_split`` (e.g. 60/30/10). Out-of-the-money
entrants forfeit their entry into the prizes; an under-subscribed tournament
cancels and refunds everyone.

There is **no house**: the prize comes entirely from entrants' pooled fees, the
platform never funds a prize and holds no outcome position. Settlement invariant
``sum(payouts) + rake == sum(entries)`` — the same neutral-operator escrow/rake
model the head-to-head and solo sides use (overview §2 / §7.1). This generalizes
the pooled solo engine (``solo_challenge.py``) from clear/miss to ranked top-N.

Two load-bearing properties carry over from the solo engine:

1. **Pooled, rake-only.** Rake is taken *only* when real prizes are distributed.
   Under-subscribed or all-un-verifiable ⇒ full refund, zero rake — the platform
   never profits from a round it does not pay out.
2. **Geo-fence first.** ``enter_tournament`` runs the solo geo-fence
   (``assert_can_enter``) *before* any entry fee is escrowed.

Logic is pure (no I/O) so it is unit-testable exactly like the settlement code.
"""

from __future__ import annotations

import random
import time
import uuid
from typing import Optional

from _lib.schemas import (
    BracketMatch,
    MetricKind,
    SoloGame,
    TelemetrySample,
    Tournament,
    TournamentEntry,
    TournamentFormat,
)
# Reuse the solo restricted-state list — the geo-fence rules are identical and
# the list must stay in one place (overview §9.2 / §10). Only the user-facing
# copy differs, so we call the shared predicate and raise our own message.
from _lib.solo_challenge import RegionBlockedError, is_region_restricted

DEFAULT_RAKE_PCT = 0.10
DEFAULT_PRIZE_SPLIT = [0.6, 0.3, 0.1]

_round2 = lambda x: round(x, 2)  # noqa: E731


class TournamentFullError(Exception):
    """Raised when a tournament is already at ``max_entrants``."""


def assert_can_enter(state: Optional[str]) -> None:
    """Geo-fence guard. Raise before escrowing an entry in a blocked region."""
    if is_region_restricted(state):
        raise RegionBlockedError(
            f"Tournaments are not available in {state or 'an unspecified region'}."
        )


def _now_ms() -> int:
    return int(time.time() * 1000)


# ---------------------------------------------------------------------------
# Creation + entry
# ---------------------------------------------------------------------------


def create_tournament(
    game: SoloGame,
    name: str,
    ranking_metric: MetricKind,
    entry_fee: float,
    *,
    higher_is_better: bool = True,
    fmt: TournamentFormat = "leaderboard_pool",
    rake_pct: float = DEFAULT_RAKE_PCT,
    max_entrants: int = 8,
    min_entrants: int = 2,
    prize_split: Optional[list[float]] = None,
) -> Tournament:
    """Open an empty tournament for a game + ranking standard."""
    return Tournament(
        id=uuid.uuid4().hex,
        game=game,
        name=name,
        format=fmt,
        ranking_metric=ranking_metric,
        higher_is_better=higher_is_better,
        entry_fee=_round2(entry_fee),
        rake_pct=rake_pct,
        max_entrants=max_entrants,
        min_entrants=min_entrants,
        prize_split=prize_split or list(DEFAULT_PRIZE_SPLIT),
        status="OPEN",
        created_at=_now_ms(),
    )


def enter_tournament(t: Tournament, player_id: str, state: str) -> Tournament:
    """Escrow an entry. Geo-fence runs BEFORE the fee is taken (overview §10).

    Idempotent per player; raises ``TournamentFullError`` when the field is full.
    """
    assert_can_enter(state)  # geo-fence BEFORE charging
    if any(e.player_id == player_id for e in t.entrants):
        return t  # already entered; no double escrow
    if len(t.entrants) >= t.max_entrants:
        raise TournamentFullError(f"{t.name} is full ({t.max_entrants} entrants).")

    t.entrants.append(TournamentEntry(player_id=player_id, state=state, status="LOCKED"))
    t.pool = _round2(t.entry_fee * len(t.entrants))
    return t


# ---------------------------------------------------------------------------
# Demo lobby — seeded open tournaments with bot entrants
# ---------------------------------------------------------------------------

# Clearly-bot handles (shared spirit with the solo/h2h bot pools). The demo has
# no second real player, so tournaments are pre-seeded with bots — and left ONE
# slot short of full so the player can take the last seat (overview §8.1).
_BOT_HANDLES = [
    "knightfork", "enpassant", "pawnstorm", "zugzwanger", "aerialace",
    "elixirgod", "boostking", "skywarden", "tiltproof", "cleansheet",
    "rookrunner", "ohko",
]


def _seed_bots(t: Tournament, n: int, rng: random.Random) -> None:
    """Pre-enter ``n`` bot entrants (bots bypass the human geo-fence)."""
    for _ in range(n):
        handle = f"{rng.choice(_BOT_HANDLES)}{rng.randint(10, 99)}"
        t.entrants.append(TournamentEntry(player_id=f"bot_{handle}", state="bot", status="LOCKED"))
    t.pool = _round2(t.entry_fee * len(t.entrants))


# (game, name, ranking_metric, entry_fee, max_entrants, prize_split, format) —
# varied across the three titles, entry tiers, and both formats.
_LOBBY_SEEDS: list[tuple[SoloGame, str, MetricKind, float, int, list[float], TournamentFormat]] = [
    # Two per game — one leaderboard pool + one single-elim bracket each.
    ("chess.lichess", "Blitz Accuracy Open", "chess_accuracy_pct", 5.0, 8, [0.6, 0.3, 0.1], "leaderboard_pool"),
    ("chess.lichess", "Knockout Blitz Cup", "chess_accuracy_pct", 10.0, 8, [0.6, 0.3, 0.1], "single_elim"),
    ("cs2.faceit", "Headshot Open", "cs2_kd_ratio", 10.0, 8, [0.5, 0.3, 0.2], "leaderboard_pool"),
    ("cs2.faceit", "Clutch Knockout", "cs2_kd_ratio", 5.0, 8, [0.6, 0.3, 0.1], "single_elim"),
    ("dota2.opendota", "GPM Grind Open", "dota2_gpm", 10.0, 8, [0.5, 0.3, 0.2], "leaderboard_pool"),
    ("dota2.opendota", "KDA Knockout", "dota2_kda_ratio", 5.0, 8, [0.6, 0.3, 0.1], "single_elim"),
    ("rocketleague.psyonix", "Score Attack Cup", "rl_match_score", 10.0, 8, [0.5, 0.3, 0.2], "leaderboard_pool"),
    ("rocketleague.psyonix", "Aerial Ace Knockout", "rl_aerial_accuracy_pct", 5.0, 8, [0.6, 0.3, 0.1], "single_elim"),
    ("clashroyale.supercell", "Crown Tower Clash", "cr_crown_tower_damage", 10.0, 8, [0.5, 0.3, 0.2], "leaderboard_pool"),
    ("clashroyale.supercell", "Crown Tower Knockout", "cr_crown_tower_damage", 10.0, 8, [0.6, 0.3, 0.1], "single_elim"),
]


def generate_tournament_lobby(rng: random.Random | None = None) -> list[Tournament]:
    """Build a set of OPEN tournaments, each seeded one slot short of full."""
    r = rng or random
    out: list[Tournament] = []
    for game, name, metric, entry, cap, split, fmt in _LOBBY_SEEDS:
        t = create_tournament(
            game, name, metric, entry_fee=entry, fmt=fmt,
            rake_pct=DEFAULT_RAKE_PCT, max_entrants=cap, min_entrants=2, prize_split=split,
        )
        _seed_bots(t, cap - 1, r)  # leave the last seat open for the player
        out.append(t)
    return out


# ---------------------------------------------------------------------------
# Ranking + settlement
# ---------------------------------------------------------------------------


def _score_entry(t: Tournament, telemetry: Optional[TelemetrySample]) -> tuple[Optional[float], str]:
    """Pull the ranking-metric value from an entrant's telemetry.

    Returns ``(score, detail)``; ``score`` is ``None`` when the result cannot be
    verified (missing telemetry / metric / game mismatch) — un-verifiable entries
    are refunded at settlement, never ranked.
    """
    if telemetry is None:
        return None, "No telemetry reported — entry refunded."
    if telemetry.game != t.game:
        return None, "Telemetry game mismatch — entry refunded."
    if t.ranking_metric not in telemetry.metrics:
        return None, f"Metric '{t.ranking_metric}' not reported — entry refunded."
    value = telemetry.metrics[t.ranking_metric]
    return value, f"{t.ranking_metric}={value:g}"


def _refund_all(t: Tournament, status: str, now: int) -> Tournament:
    for e in t.entrants:
        e.status = "REFUNDED"
        e.payout = t.entry_fee
        e.rank = None
    t.rake = 0.0
    t.prize_pool = 0.0
    t.status = status  # "CANCELED" or "SETTLED" (no verifiable results)
    t.resolved_at = now
    return t


def settle_tournament(
    t: Tournament,
    telemetry: dict[str, TelemetrySample],
    rng: random.Random | None = None,
) -> Tournament:
    """Resolve a tournament and pay the top finishers, minus rake.

    ``leaderboard_pool`` ranks entrants by the objective metric directly.
    ``single_elim`` plays out a bracket (head-to-head games, rematch-on-draw)
    using each entrant's metric as their match strength, then ranks by finish.
    Either way the same payout rules apply (no house, neutral operator):

      * Under ``min_entrants`` → CANCELED, every entry refunded, zero rake.
      * Too few verifiable results to resolve → SETTLED, all refunded, zero rake.
      * Otherwise → un-verifiable entries are refunded out of the pool first; the
        rake comes off the remaining pool; the top ``len(prize_split)`` finishers
        split ``pool − rake`` by weight; everyone below the cut gets 0.

    Invariant in all cases: ``sum(payouts) + rake == sum(entries)``.
    """
    now = _now_ms()
    t.pool = _round2(t.entry_fee * len(t.entrants))

    if len(t.entrants) < t.min_entrants:
        return _refund_all(t, "CANCELED", now)

    verifiable: list[TournamentEntry] = []
    unverifiable: list[TournamentEntry] = []
    for e in t.entrants:
        score, detail = _score_entry(t, telemetry.get(e.player_id))
        e.detail = detail
        if score is None:
            e.score = None
            unverifiable.append(e)
        else:
            e.score = score
            verifiable.append(e)

    # A bracket needs at least two players to produce a match; a leaderboard
    # needs at least one ranked result.
    min_verifiable = 2 if t.format == "single_elim" else 1
    if len(verifiable) < min_verifiable:
        return _refund_all(t, "SETTLED", now)

    if t.format == "single_elim":
        strengths = {e.player_id: float(e.score) for e in verifiable}
        t.rounds = _simulate_bracket(t, strengths, rng or random)
        order_ids = _final_ranking(t.rounds, strengths)
        by_id = {e.player_id: e for e in verifiable}
        ranked = [by_id[pid] for pid in order_ids if pid in by_id]
        # Defensive: append any verifiable player the bracket somehow missed.
        ranked += [e for e in verifiable if e not in ranked]
    else:
        ranked = sorted(verifiable, key=lambda e: e.score, reverse=t.higher_is_better)

    _distribute_prizes(t, ranked, unverifiable, now)

    if t.format == "single_elim":
        for e in ranked:
            e.detail = _placement_label(e.rank)
    return t


def _distribute_prizes(
    t: Tournament,
    ranked: list[TournamentEntry],
    unverifiable: list[TournamentEntry],
    now: int,
) -> Tournament:
    """Apply the rake + ``prize_split`` to an already-ordered finish list.

    ``ranked`` is best-first. Un-verifiable entries are refunded out of the pool
    first; the rake comes off the rest; the top ``len(prize_split)`` finishers
    split ``pool − rake`` by weight (renormalized if fewer ranked than places).
    Rounding remainder is absorbed into the rake so the invariant holds exactly.
    """
    refunds_total = _round2(t.entry_fee * len(unverifiable))
    distributable = _round2(t.pool - refunds_total)
    rake = _round2(distributable * t.rake_pct)
    net = _round2(distributable - rake)

    places = min(len(t.prize_split), len(ranked))
    weights = t.prize_split[:places]
    wsum = sum(weights) or 1.0
    shares = [_round2(net * w / wsum) for w in weights]

    distributed = 0.0
    for i, e in enumerate(ranked):
        e.rank = i + 1
        if i < places:
            e.status = "PAID"
            e.payout = shares[i]
            distributed = _round2(distributed + shares[i])
        else:
            e.status = "OUT"
            e.payout = 0.0          # entry funds the top finishers' prizes
    for e in unverifiable:
        e.status = "REFUNDED"
        e.payout = t.entry_fee
        e.rank = None

    t.rake = _round2(t.pool - distributed - refunds_total)
    t.prize_pool = distributed
    t.status = "SETTLED"
    t.resolved_at = now
    return t


# ---------------------------------------------------------------------------
# Single-elimination bracket (draw policy: rematch until decisive)
# ---------------------------------------------------------------------------

# How heavily a strength edge favors a player in a single game (0 = coin-flip,
# 1 = deterministic). Kept < 1 so upsets happen — it's a contest, not a sort.
_FAVORED_WEIGHT = 0.8
# Per-game draw probability; a draw forces a rematch of the same pairing.
_DRAW_PROB = 0.15
# Safety cap on rematches so a pathological RNG run can't loop forever.
_MAX_GAMES = 12


def _seed_order(n: int) -> list[int]:
    """Standard single-elimination seed positions for a bracket of size ``n``
    (a power of two). Ensures the top seeds are spread across the bracket and
    meet as late as possible. Returns 0-indexed seed numbers."""
    res = [1, 2]
    while len(res) < n:
        m = len(res) * 2 + 1
        res = [x for s in res for x in (s, m - s)]
    return [r - 1 for r in res]


def _play_match(a: str, b: str, strengths: dict[str, float], rng: random.Random) -> tuple[str, int]:
    """Play one head-to-head match; a drawn game is replayed until decisive.

    Returns ``(winner_id, games_played)``. The stronger entrant is favored but
    not guaranteed (``_FAVORED_WEIGHT``); draws (``_DRAW_PROB``) force a rematch.
    """
    sa, sb = strengths[a], strengths[b]
    denom = sa + sb or 1.0
    diff = (sa - sb) / denom                      # in [-1, 1]
    p_a = min(0.95, max(0.05, 0.5 + 0.5 * diff * _FAVORED_WEIGHT))
    games = 0
    while games < _MAX_GAMES:
        games += 1
        if rng.random() < _DRAW_PROB:
            continue                              # draw → rematch (same pairing)
        return (a if rng.random() < p_a else b), games
    # Cap hit (extremely unlikely): the stronger entrant takes it.
    return (a if sa >= sb else b), games


def _simulate_bracket(
    t: Tournament, strengths: dict[str, float], rng: random.Random
) -> list[list[BracketMatch]]:
    """Seed the verifiable entrants and play the bracket out round by round.

    Non-power-of-two fields get byes, handed to the top seeds (overview §3.2
    edge-case handling).
    """
    players = sorted(strengths, key=lambda p: strengths[p], reverse=True)  # seed 0 = strongest
    size = 1
    while size < len(players):
        size *= 2
    seeded = players + [None] * (size - len(players))      # pad with byes
    slots = [seeded[s] for s in _seed_order(size)]          # arrange by seed position

    rounds: list[list[BracketMatch]] = []
    current = slots
    rnd = 0
    while len(current) > 1:
        matches: list[BracketMatch] = []
        advancing: list[Optional[str]] = []
        for i in range(0, len(current), 2):
            a, b = current[i], current[i + 1]
            m = BracketMatch(round=rnd, slot=i // 2, player_a=a, player_b=b)
            if a is not None and b is not None:
                winner, games = _play_match(a, b, strengths, rng)
                m.winner = winner
                m.games = games
                m.detail = f"{games} game{'s' if games != 1 else ''}" + (" (rematch)" if games > 1 else "")
            elif a is not None or b is not None:
                m.winner = a if a is not None else b        # bye
                m.detail = "bye"
            matches.append(m)
            advancing.append(m.winner)
        rounds.append(matches)
        current = advancing
        rnd += 1
    return rounds


def _final_ranking(rounds: list[list[BracketMatch]], strengths: dict[str, float]) -> list[str]:
    """Derive a full best-first finish order from a played-out bracket.

    Champion first, then the loser of the final (runner-up), then the losers of
    each earlier round (latest first), ordered within a round by strength so
    prize places are unambiguous.
    """
    if not rounds:
        return []
    order: list[str] = []
    champ = rounds[-1][0].winner
    if champ is not None:
        order.append(champ)
    for matches in reversed(rounds):
        losers: list[str] = []
        for m in matches:
            if m.player_a is None or m.player_b is None:
                continue                                    # bye — no loser
            loser = m.player_a if m.winner == m.player_b else m.player_b
            if loser is not None and loser not in order and loser not in losers:
                losers.append(loser)
        losers.sort(key=lambda p: strengths.get(p, 0.0), reverse=True)
        order += losers
    return order


def _placement_label(rank: Optional[int]) -> str:
    if rank == 1:
        return "Champion"
    if rank == 2:
        return "Runner-up"
    if rank in (3, 4):
        return "Semi-finalist"
    return f"Finished #{rank}" if rank else "Out"
