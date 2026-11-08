"""The match state machine — one place, explicit legal transitions."""

from __future__ import annotations

from ..errors import APIError

PENDING = "PENDING"
ACTIVE = "ACTIVE"
AWAITING_RESULT = "AWAITING_RESULT"
SETTLED = "SETTLED"
PUSHED = "PUSHED"
CANCELED = "CANCELED"

TERMINAL_STATES = frozenset({SETTLED, PUSHED, CANCELED})

LEGAL_TRANSITIONS: dict[str, frozenset[str]] = {
    PENDING: frozenset({ACTIVE, CANCELED}),
    ACTIVE: frozenset({AWAITING_RESULT, SETTLED, PUSHED, CANCELED}),
    AWAITING_RESULT: frozenset({SETTLED, PUSHED, CANCELED}),
    SETTLED: frozenset(),
    PUSHED: frozenset(),
    CANCELED: frozenset(),
}


class IllegalTransitionError(APIError):
    """A transition not permitted by the state machine (RFC-7807 via APIError)."""

    def __init__(self, current: str, target: str) -> None:
        super().__init__(
            "illegal_match_transition",
            f"Cannot move a match from {current} to {target}.",
            status_code=409,
            detail={"current": current, "target": target},
        )


def is_terminal(state: str) -> bool:
    return state in TERMINAL_STATES


def can_transition(current: str, target: str) -> bool:
    return target in LEGAL_TRANSITIONS.get(current, frozenset())


def assert_transition(current: str, target: str) -> None:
    """Raise `IllegalTransitionError` unless `current → target` is legal."""
    if not can_transition(current, target):
        raise IllegalTransitionError(current, target)
