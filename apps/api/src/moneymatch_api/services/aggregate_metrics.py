"""Everything else in the engine (field formation, ties, prize splitting, refunds on
host outage, forfeits) is unchanged, so these ride the same settlement path as
every other contest.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from ..adapters.base import NormGame

ELO_SIGMA = 150.0


@dataclass(frozen=True)
class AggregateMetric:
    key: str
    label: str
    higher_is_better: bool
    score: Callable[[list[NormGame]], float | None]
    counted: Callable[[list[NormGame]], int]


def _is_win(g: NormGame) -> bool:
    return g.won is True and g.moves > 0


def _wins(games: list[NormGame]) -> list[NormGame]:
    return [g for g in games if _is_win(g)]


def _total_wins(games: list[NormGame]) -> float | None:
    return float(len(_wins(games))) if games else None


def _longest_streak(games: list[NormGame]) -> float | None:
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
    """Fewest moves in a game you **won**. A plain minimum over all games is won by
    resigning on move one, which would make the contest a race to forfeit.
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
        higher_is_better=False,
        score=_fastest_win,
        counted=lambda games: len(_wins(games)),
    ),
}


def get(metric: str) -> AggregateMetric | None:
    return REGISTRY.get(metric)


def is_aggregate(metric: str) -> bool:
    return metric in REGISTRY


def higher_is_better(metric: str) -> bool:
    """Ranking direction."""
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
