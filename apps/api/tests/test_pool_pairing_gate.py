"""A pool must be able to match the players it agreed to let in.

Two floors disagreed. Pools admit you at `STAT_BASELINE_MIN_N` (1 sample),
because a pool is played against a bar quoted from your own history and a thin
history just makes for a wide bar. But room formation went through
`matchmaking.can_pair`, which carries the *head-to-head* rule: a stat duel is
decided by comparing two players' numbers, so it refuses a baseline under
`METRIC_PROVISIONAL_MIN_N` (10).

The overlap is the bug. Anyone holding 1 to 9 samples could join a pool queue
and never be matched into a room, waiting forever with a real ticket and a real
hold on their money. Every pool built during testing came out as a room of one
for exactly this reason.

The anti-collusion checks in `can_pair` are unaffected and must stay on.
"""

from __future__ import annotations

import ast
import inspect
import textwrap

import pytest

from moneymatch_api.constants import METRIC_PROVISIONAL_MIN_N, STAT_BASELINE_MIN_N
from moneymatch_api.services import matchmaking, pool_engine, tournament_engine

pytestmark = pytest.mark.nodb


def test_the_two_floors_really_do_disagree():
    """If these are ever reconciled, this whole file is obsolete."""
    assert STAT_BASELINE_MIN_N < METRIC_PROVISIONAL_MIN_N


def test_a_duel_still_refuses_a_provisional_baseline_by_default():
    """The head-to-head rule is the default, so no caller loses it silently."""
    sig = inspect.signature(matchmaking.can_pair)
    assert sig.parameters["require_established_metric"].default is True


@pytest.mark.parametrize("engine", [pool_engine, tournament_engine])
def test_a_bar_contest_opts_out_of_the_duel_floor(engine):
    """Pools and tournaments must both waive it, and only it."""
    src = inspect.getsource(engine._all_pairs_pairable)
    assert "require_established_metric=False" in src, engine.__name__


@pytest.mark.parametrize("engine", [pool_engine, tournament_engine])
def test_waiving_it_does_not_mean_skipping_the_check(engine):
    """The collusion guards live in the same call, so it must still be made."""
    src = inspect.getsource(engine._all_pairs_pairable)
    assert "matchmaking.can_pair" in src, engine.__name__


def test_the_anti_collusion_guards_are_not_behind_the_flag():
    """Same user, same host account and the re-pair cooldown always apply.

    Only the provisional-metric branch is allowed to read the new flag; if a
    future edit tucks another guard behind it, the pool surface would quietly
    become the collusion-friendly one.
    """
    src = textwrap.dedent(inspect.getsource(matchmaking.can_pair))
    assert src.count("if require_established_metric") == 1  # one branch, no more

    # Only the flag's own branch, taken from the parse tree rather than by
    # indentation, since the condition itself wraps over several lines.
    fn = ast.parse(src).body[0]
    assert isinstance(fn, ast.AsyncFunctionDef)
    branch = next(
        node
        for node in ast.walk(fn)
        if isinstance(node, ast.If)
        and "require_established_metric" in ast.unparse(node.test)
    )
    guarded = "\n".join(ast.unparse(stmt) for stmt in branch.body)

    assert "METRIC_PROVISIONAL_MIN_N" in guarded  # the one rule being waived
    for always_on in ("user_id", "host_account_id", "_recent_pair_exists"):
        assert always_on not in guarded, always_on
