"""scipy adoption guard rails. scipy is now a runtime dependency because the bar-
setting roadmap needs several pieces of specialist numerics in the code path that
decides where money goes.
"""

from __future__ import annotations

import math

import pytest
from scipy import stats

from moneymatch_api.services.fairness import normal_cdf

pytestmark = pytest.mark.nodb

# `math.erf` is correctly rounded to : within an ulp, so agreement should be near
# machine precision; 1e-12 leaves : room for the final multiply/add without hiding a
# real divergence.
PHI_TOLERANCE = 1e-12


@pytest.mark.parametrize(
    "z",
    [
        -3.0,
        -2.0,
        -1.282,
        -0.842,
        -0.385,
        0.0,
        0.385,
        0.842,
        1.282,
        2.0,
        3.0,
        -6.0,
        -5.0,
        -4.0,
        4.0,
        5.0,
        6.0,
        -37.0,
        -10.0,
        10.0,
        37.0,
        1e-8,
        -1e-8,
        0.5000001,
        -0.4999999,
    ],
)
def test_hand_rolled_phi_agrees_with_scipy(z: float):
    ours = normal_cdf(z)
    theirs = float(stats.norm.cdf(z))
    assert ours == pytest.approx(theirs, abs=PHI_TOLERANCE), (
        f"normal_cdf({z}) = {ours!r} but scipy says {theirs!r}. This is a "
        "finding, not something to patch quietly — every quoted clear "
        "probability depends on it."
    )


def test_phi_agrees_with_scipy_across_a_dense_grid():
    worst_z, worst_err = 0.0, 0.0
    z = -8.0
    while z <= 8.0:
        err = abs(normal_cdf(z) - float(stats.norm.cdf(z)))
        if err > worst_err:
            worst_z, worst_err = z, err
        z += 0.01
    assert worst_err < PHI_TOLERANCE, (
        f"largest Φ disagreement {worst_err:.3e} at z={worst_z:.2f}"
    )


def test_phi_boundary_behaviour_matches():
    assert normal_cdf(-40.0) == pytest.approx(0.0, abs=1e-300)
    assert normal_cdf(40.0) == pytest.approx(1.0, abs=1e-15)
    assert normal_cdf(0.0) == 0.5
    assert math.isclose(normal_cdf(1.0) + normal_cdf(-1.0), 1.0, rel_tol=1e-15)


@pytest.mark.parametrize(
    ("df", "q"),
    [(2, 0.9), (5, 0.65), (17.3, 0.8), (27.1, 0.9), (40.4, 0.99), (1000, 0.5)],
)
def test_student_t_quantile_is_deterministic(df: float, q: float):
    first = float(stats.t.ppf(q, df=df))
    for _ in range(50):
        assert float(stats.t.ppf(q, df=df)) == first
    assert math.isfinite(first)


def test_student_t_matches_published_quantiles():
    assert float(stats.t.ppf(0.975, df=1)) == pytest.approx(12.706, abs=0.001)
    assert float(stats.t.ppf(0.975, df=10)) == pytest.approx(2.228, abs=0.001)
    assert float(stats.t.ppf(0.975, df=30)) == pytest.approx(2.042, abs=0.001)
    assert float(stats.t.ppf(0.975, df=10_000_000)) == pytest.approx(1.96, abs=0.001)


def test_discrete_distributions_are_deterministic():
    nb_first = float(stats.nbinom.sf(24, 8.0, 0.32))
    bb_first = float(stats.betabinom.sf(9, 17, 4.2, 5.8))
    for _ in range(50):
        assert float(stats.nbinom.sf(24, 8.0, 0.32)) == nb_first
        assert float(stats.betabinom.sf(9, 17, 4.2, 5.8)) == bb_first


def test_scipy_version_is_inside_the_pinned_range():
    import scipy

    major, minor = (int(p) for p in scipy.__version__.split(".")[:2])
    assert major == 1 and minor >= 14, (
        f"scipy {scipy.__version__} is outside the pinned range >=1.14,<2. If "
        "this is a deliberate upgrade, re-run the golden harness and review the "
        "diff as a maths change."
    )
