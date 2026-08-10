"""Aggregate tournament metrics: scored over a whole window, not per match.

The tournament engine's original scoring is "mean of your first N qualifying
matches" of a **rate** metric (K/D, ADR, moves per game). Some contests are not
shaped like that: "most wins this window" and "longest win streak" are functions
of the *sequence* of results, and "fastest win" is a minimum rather than a mean.

A metric registered here supplies its own `score()` over the entrant's full
in-window game list, plus the direction that wins. Everything else in the engine
(field formation, ties, prize splitting, refunds on host outage, forfeits) is
unchanged, so these ride the same settlement path as every other contest.

Chess is the first user: the Lichess game record gives `won` and `moves` on
every game, so all three are real, no extra host call, nothing self-reported.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from ..adapters.base import NormGame

# Skill spread assumed for an Elo-formed field, in rating points. Aggregate
# metrics have no per-match rate model to take a σ from, so fields form on the
# host's own rating instead (see `tournament_engine._build_baseline`).
ELO_SIGMA = 150.0


@dataclass(frozen=True)
class AggregateMetric:
    key: str
    label: str
    #: True ⇒ a bigger number ranks higher. False ⇒ smaller wins (fastest win).
    higher_is_better: bool
    #: Score the entrant's whole in-window history. `None` ⇒ no qualifying
    #: result, which the engine treats as a forfeit (ranked last, paid nothing).
    score: Callable[[list[NormGame]], float | None]
    #: How many games actually contributed, for the standings subline.
    counted: Callable[[list[NormGame]], int]


def _is_win(g: NormGame) -> bool:
    # A won record with no move list (moves == 0) is an aborted/empty game, not
    # a real win. Excluded everywhere so wins, streak and fastest-win agree.
    return g.won is True and g.moves > 0


def _wins(games: list[NormGame]) -> list[NormGame]:
    return [g for g in games if _is_win(g)]


def _total_wins(games: list[NormGame]) -> float | None:
    return float(len(_wins(games))) if games else None


def _longest_streak(games: list[NormGame]) -> float | None:
    """Longest unbroken run of wins, in play order.

    A draw breaks the streak. `poll_eligible_games` returns newest-first, so the
    list is reversed to walk it chronologically. Direction does not change the
    longest run, but it keeps the intent obvious.
    """
    if not games:
        return None
    best = run = 0
    for g in reversed(games):
        if _is_win(g):
            run += 1
            best = max(best, run)
        else:
            run = 0
    return float(best)


def _fastest_win(games: list[NormGame]) -> float | None:
    """Fewest moves in a game you **won**.

    Deliberately not "fewest moves in any game". A plain minimum over all games
    is won by resigning on move one, which would make the contest a race to
    forfeit. Requiring the win makes it what it sounds like: quickest checkmate.
    """
    won = _wins(games)
    return float(min(g.moves for g in won)) if won else None


REGISTRY: dict[str, AggregateMetric] = {
    "chess_win_streak": AggregateMetric(
        key="chess_win_streak",
        label="Longest win streak",
        higher_is_better=True,
        score=_longest_streak,
        counted=lambda games: len(games),
    ),
    "chess_wins": AggregateMetric(
        key="chess_wins",
        label="Total wins",
        higher_is_better=True,
        score=_total_wins,
        counted=lambda games: len(games),
    ),
    "chess_fastest_win": AggregateMetric(
        key="chess_fastest_win",
        label="Fastest win",
        higher_is_better=False,  # fewer moves wins
        score=_fastest_win,
        counted=lambda games: len(_wins(games)),
    ),
}


def get(metric: str) -> AggregateMetric | None:
    return REGISTRY.get(metric)


def is_aggregate(metric: str) -> bool:
    return metric in REGISTRY


def higher_is_better(metric: str) -> bool:
    """Ranking direction. Rate metrics (the default) always rank higher-first."""
    spec = REGISTRY.get(metric)
    return spec.higher_is_better if spec else True


__all__ = [
    "ELO_SIGMA",
    "AggregateMetric",
    "REGISTRY",
    "get",
    "higher_is_better",
    "is_aggregate",
]
