"""The match state machine: legal transitions and clean rejection of illegal ones."""

from __future__ import annotations

import pytest

from moneymatch_api.services import match_states as ms
from moneymatch_api.services.match_states import IllegalTransitionError


def test_happy_path_transitions_are_legal():
    assert ms.can_transition(ms.PENDING, ms.ACTIVE)
    assert ms.can_transition(ms.ACTIVE, ms.AWAITING_RESULT)
    assert ms.can_transition(ms.AWAITING_RESULT, ms.SETTLED)
    assert ms.can_transition(ms.AWAITING_RESULT, ms.PUSHED)


def test_cancel_paths_are_legal_from_every_non_terminal_state():
    assert ms.can_transition(ms.PENDING, ms.CANCELED)
    assert ms.can_transition(ms.ACTIVE, ms.CANCELED)
    assert ms.can_transition(ms.AWAITING_RESULT, ms.CANCELED)


def test_fast_host_can_settle_straight_from_active():
    assert ms.can_transition(ms.ACTIVE, ms.SETTLED)
    assert ms.can_transition(ms.ACTIVE, ms.PUSHED)


def test_terminal_states_have_no_exits():
    for terminal in (ms.SETTLED, ms.PUSHED, ms.CANCELED):
        assert ms.is_terminal(terminal)
        assert not ms.can_transition(terminal, ms.ACTIVE)
        assert not ms.can_transition(terminal, ms.SETTLED)


def test_illegal_transitions_rejected():
    # Can't skip confirmation, can't reopen a settled match, can't rewind.
    assert not ms.can_transition(ms.PENDING, ms.SETTLED)
    assert not ms.can_transition(ms.ACTIVE, ms.PENDING)
    with pytest.raises(IllegalTransitionError):
        ms.assert_transition(ms.SETTLED, ms.ACTIVE)
    with pytest.raises(IllegalTransitionError):
        ms.assert_transition(ms.PENDING, ms.SETTLED)


def test_assert_transition_passes_on_legal_move():
    ms.assert_transition(ms.PENDING, ms.ACTIVE)  # no raise
