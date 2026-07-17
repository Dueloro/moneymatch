"""The match state machine — one place, explicit legal transitions (00-README §3.4).

Every match transition happens in exactly one lifecycle-service function inside a
DB transaction; this module only declares which moves are legal and raises on an
illegal one, so a double-fire or out-of-order worker pass is a clean no-op/error
rather than silent money movement.

    PENDING ──confirm(both)──► ACTIVE ──begin grading──► AWAITING_RESULT
       │                          │                            │
       │ decline/expire           └──────────┬─────────────────┘
       ▼                                      ▼
    CANCELED                      SETTLED · PUSHED · CANCELED
"""

from __future__ import annotations

from ..errors import APIError

PENDING = "PENDING"
ACTIVE = "ACTIVE"
AWAITING_RESULT = "AWAITING_RESULT"
SETTLED = "SETTLED"
PUSHED = "PUSHED"
CANCELED = "CANCELED"

TERMINAL_STATES = frozenset({SETTLED, PUSHED, CANCELED})

# Legal transitions. A settlement can resolve from either ACTIVE (fast host) or
# AWAITING_RESULT; expiry/cancel can fire from any non-terminal state.
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
