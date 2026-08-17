"""Golden-snapshot harness for bar-setting mathematics (Phase 0.2).

`IMPLEMENTATION_STATUS.md` §5 claims an "audit replay guarantee": every number a
player sees re-derives byte-for-byte from stored inputs. That claim was not
machine-checked. This file makes it so, and is the regression net for every
Phase 2 change to the maths.

For a fixed corpus of (game, metric, μ, σ, n) it records, per difficulty:
`σ_effective`, `n_eff`, `bar`, `p_quoted`, `room_bar` and the display
`multiplier`, and diffs the whole thing against a frozen JSON file.

**Any change that moves a number must move it in the golden file, deliberately,
with the diff reviewed in the commit.** Regenerate with:

    UPDATE_BAR_GOLDEN=1 pytest tests/test_bar_golden.py

The corpus is seeded with the four cases in `IMPLEMENTATION_STATUS.md` §5.4 that
are known to reproduce deployed behaviour exactly; `test_known_deployed_bars`
asserts those independently of the golden file, so a careless regeneration
cannot silently bless a regression against real observed output.
"""

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

#: (label, game, metric, μ, σ, n). Seeded with the four §5.4 cases that match
#: deployed behaviour, plus coverage of the lognormal branch and every other
#: shipped pool metric so a change cannot move a number unnoticed.
CORPUS: list[tuple[str, str, str, float, float, int]] = [
    # --- known to match deployed behaviour (IMPLEMENTATION_STATUS.md §5.4) ---
    ("cs2_kd_private_prior", "cs2.steam", "cs2_kd_ratio", 1.00, 0.25, 3),
    ("cs2_kd_public_lifetime", "cs2.steam", "cs2_kd_ratio", 0.606, 0.25, 3),
    ("cs2_kills_seeded", "cs2.steam", "cs2_kills", 10.92, 6.0, 3),
    ("cs2_headshot_seeded", "cs2.steam", "cs2_headshot_pct", 42.34, 12.0, 3),
    # --- established players, larger samples ---
    ("cs2_kd_established", "cs2.steam", "cs2_kd_ratio", 1.18, 0.31, 40),
    ("cs2_kills_established", "cs2.steam", "cs2_kills", 17.0, 5.5, 50),
    ("cs2_headshot_established", "cs2.steam", "cs2_headshot_pct", 43.5, 13.2, 50),
    # --- lognormal branch (positive support + lower-is-better) ---
    ("chess_moves_1000", "chess.lichess", "chess_moves", 26.8, 11.94, 20),
    ("chess_moves_2000", "chess.lichess", "chess_moves", 36.9, 11.94, 60),
    ("chess_moves_tight", "chess.lichess", "chess_moves", 25.7, 2.0, 9),
    # --- other shipped pool metrics ---
    ("dota2_kda", "dota2.opendota", "dota2_kda_ratio", 3.2, 0.8, 30),
    ("dota2_gpm", "dota2.opendota", "dota2_gpm", 520.0, 90.0, 30),
    ("pubg_kills", "pubg.steam", "pubg_kills", 4.5, 2.0, 25),
    ("pubg_damage", "pubg.steam", "pubg_damage", 380.0, 120.0, 25),
    ("pubg_headshot", "pubg.steam", "pubg_headshot_pct", 22.0, 8.0, 25),
]


def ewma_n_eff(n: int, half_life: int = METRIC_EWMA_HALF_LIFE) -> float:
    """Kish effective sample size of the EWMA window: ``(Σw)² / Σw²``.

    `compute_ewma` reports the *raw* count `n`, which overstates how much
    evidence a recency-weighted mean actually carries. Recorded here from Phase
    0 so the Student-t work in Phase 2.3 has a baseline to move against.
    """
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
        # A room of identical members is the deterministic reference shape: the
        # room bar must equal the personal bar, which is itself a useful check.
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


def build_snapshot() -> dict:
    return {label: _snapshot_case(label, *rest) for label, *rest in CORPUS}


def test_bar_golden_snapshot():
    """The whole bar surface, frozen. A diff here is a deliberate maths change."""
    current = build_snapshot()

    if os.environ.get("UPDATE_BAR_GOLDEN"):
        GOLDEN_PATH.parent.mkdir(parents=True, exist_ok=True)
        GOLDEN_PATH.write_text(json.dumps(current, indent=2, sort_keys=True) + "\n")
        pytest.skip("golden file regenerated")

    assert GOLDEN_PATH.exists(), (
        f"missing golden file {GOLDEN_PATH}; regenerate with UPDATE_BAR_GOLDEN=1"
    )
    expected = json.loads(GOLDEN_PATH.read_text())

    assert set(current) == set(expected), "corpus membership changed"
    for label in sorted(expected):
        assert current[label] == expected[label], (
            f"bar maths moved for {label!r}. If deliberate, regenerate the golden "
            "file and explain the diff in the commit message."
        )


@pytest.mark.parametrize(
    ("label", "expected"),
    [
        # IMPLEMENTATION_STATUS.md §5.4 — verified against the deployed app.
        ("cs2_kd_private_prior", {"easy": 1.10, "medium": 1.20, "hard": 1.30}),
        ("cs2_kd_public_lifetime", {"easy": 0.70, "medium": 0.80, "hard": 0.95}),
        ("cs2_kills_seeded", {"easy": 13.0, "medium": 16.0, "hard": 19.0}),
        ("cs2_headshot_seeded", {"easy": 47.0, "medium": 52.0, "hard": 58.0}),
    ],
)
def test_known_deployed_bars(label: str, expected: dict[str, float]):
    """The four cases observed in production, asserted independently.

    These are the anchor: they were read off the deployed app, so they pin the
    maths to reality rather than to whatever the golden file happens to hold.
    """
    case = _snapshot_case(label, *next(rest for lbl, *rest in CORPUS if lbl == label))
    actual = {d: case["difficulties"][d]["bar"] for d in expected}
    assert actual == pytest.approx(expected)


def test_n_eff_matches_published_values():
    """`n_eff` for known windows (MONEYMATCH_RESEARCH.md §2.6)."""
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
