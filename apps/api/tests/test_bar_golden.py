"""Golden-snapshot harness for bar-setting mathematics."""

from __future__ import annotations

import json
import os
import pathlib

import pytest

from moneymatch_api.constants import (
    METRIC_BAR_INCREMENT,
    METRIC_EWMA_HALF_LIFE,
    POOL_DIFFICULTY_K,
    POOL_ROOM_SIZE,
    lower_is_better,
    metric_floor,
    positive_support,
)
from moneymatch_api.services import fairness, money_math

pytestmark = pytest.mark.nodb

GOLDEN_PATH = pathlib.Path(__file__).parent / "golden" / "bar_snapshots.json"

CORPUS: list[tuple[str, str, str, float, float, int]] = [
    ("chess_moves_1000", "chess.lichess", "chess_moves", 26.8, 11.94, 20),
    ("chess_moves_2000", "chess.lichess", "chess_moves", 36.9, 11.94, 60),
    ("chess_moves_tight", "chess.lichess", "chess_moves", 25.7, 2.0, 9),
]


def ewma_n_eff(n: int, half_life: int = METRIC_EWMA_HALF_LIFE) -> float:
    if n <= 0:
        return 0.0
    weights = [0.5 ** ((n - 1 - i) / half_life) for i in range(n)]
    total = sum(weights)
    return (total * total) / sum(w * w for w in weights)


def _snapshot_case(
    label: str, game: str, metric: str, mu: float, sigma: float, n: int
) -> dict:
    increment = METRIC_BAR_INCREMENT[metric]
    sigma_eff = fairness.effective_sigma(sigma, increment)
    shape = {
        "increment": increment,
        "lower_is_better": lower_is_better(metric),
        "positive": positive_support(metric),
        "floor": metric_floor(metric),
    }

    difficulties: dict[str, dict] = {}
    for difficulty, k in POOL_DIFFICULTY_K.items():
        bar = fairness.personal_bar(mu, sigma_eff, k, **shape)
        p_quoted = fairness.clear_prob(
            bar,
            mu,
            sigma_eff,
            shape["lower_is_better"],
            positive=shape["positive"],
        )
        p_target = fairness.p_target_for_k(k)
        room_bar = fairness.room_bar([bar] * POOL_ROOM_SIZE, increment)
        multiplier_bps = money_math.pool_multiplier_estimate_bps(
            p_target, POOL_ROOM_SIZE
        )
        difficulties[difficulty] = {
            "k": round(k, 6),
            "bar": round(bar, 6),
            "p_quoted": round(p_quoted, 6),
            "p_target": round(p_target, 6),
            "room_bar": round(room_bar, 6),
            "multiplier_bps": multiplier_bps,
        }

    return {
        "game": game,
        "metric": metric,
        "mu": round(mu, 6),
        "sigma": round(sigma, 6),
        "sigma_effective": round(sigma_eff, 6),
        "n": n,
        "n_eff": round(ewma_n_eff(n), 6),
        "shape": shape,
        "difficulties": difficulties,
    }


def _numerics_meta() -> dict:
    import scipy

    return {"scipy": scipy.__version__}


def build_snapshot() -> dict:
    return {
        "meta": _numerics_meta(),
        "cases": {label: _snapshot_case(label, *rest) for label, *rest in CORPUS},
    }


def test_bar_golden_snapshot():
    current = build_snapshot()

    if os.environ.get("UPDATE_BAR_GOLDEN"):
        GOLDEN_PATH.parent.mkdir(parents=True, exist_ok=True)
        GOLDEN_PATH.write_text(json.dumps(current, indent=2, sort_keys=True) + "\n")
        pytest.skip("golden file regenerated")

    assert GOLDEN_PATH.exists(), (
        f"missing golden file {GOLDEN_PATH}; regenerate with UPDATE_BAR_GOLDEN=1"
    )
    stored = json.loads(GOLDEN_PATH.read_text())
    expected_cases = stored["cases"]
    current_cases = current["cases"]

    assert set(current_cases) == set(expected_cases), "corpus membership changed"
    for label in sorted(expected_cases):
        assert current_cases[label] == expected_cases[label], (
            f"bar maths moved for {label!r}. If deliberate, regenerate the golden "
            "file and explain the diff in the commit message."
            + (
                "\n\nNOTE: the numerics library version ALSO changed "
                f"({stored['meta']} -> {current['meta']}), so this diff may be "
                "the upgrade rather than your change. Separate them before "
                "attributing it."
                if stored["meta"] != current["meta"]
                else ""
            )
        )


def test_numerics_version_is_recorded_and_unchanged():
    if os.environ.get("UPDATE_BAR_GOLDEN"):
        pytest.skip("regenerating")
    stored = json.loads(GOLDEN_PATH.read_text())["meta"]
    assert stored == _numerics_meta(), (
        f"numerics library changed: golden={stored}, current={_numerics_meta()}. "
        "Re-run the golden harness, review whether any bar moved, and re-bless "
        "the file in a commit that says so."
    )


@pytest.mark.parametrize(
    ("label", "expected"),
    [
        ("chess_moves_1000", {"easy": 21.0, "medium": 17.0, "hard": 14.0}),
        ("chess_moves_2000", {"easy": 31.0, "medium": 27.0, "hard": 23.0}),
        ("chess_moves_tight", {"easy": 25.0, "medium": 24.0, "hard": 23.0}),
    ],
)
def test_known_bars(label: str, expected: dict[str, float]):
    case = _snapshot_case(label, *next(rest for lbl, *rest in CORPUS if lbl == label))
    actual = {d: case["difficulties"][d]["bar"] for d in expected}
    assert actual == pytest.approx(expected)


def test_n_eff_matches_published_values():
    assert ewma_n_eff(20, 10) == pytest.approx(17.3, abs=0.1)
    assert ewma_n_eff(50, 10) == pytest.approx(27.1, abs=0.1)
    assert ewma_n_eff(50, 20) == pytest.approx(40.4, abs=0.1)


def test_room_of_identical_members_reproduces_the_personal_bar():
    """The audit-replay property, in its simplest form."""
    for label, *rest in CORPUS:
        case = _snapshot_case(label, *rest)
        for difficulty, row in case["difficulties"].items():
            assert row["room_bar"] == row["bar"], (
                f"{label}/{difficulty}: identical members must produce a room bar "
                "equal to the shared personal bar"
            )
