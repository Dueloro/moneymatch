"""Runtime knobs for the bucketing contest flow (Phases 5, 7).

Kept in one place (ground rule: "all constants in config, never inline"). These
govern room formation and the settlement window; the fairness/skill constants
live in `index.py` / `reference.py` next to the maths they tune.
"""

from __future__ import annotations

# A full room; at the fill-window's end we form down to BUCKET_MIN_ROOM.
BUCKET_ROOM_SIZE = 4
BUCKET_MIN_ROOM = 3

# How long a queued entry waits for a room before the matchmaker forms a
# short room (>= BUCKET_MIN_ROOM) or, failing that, refunds and cancels it.
BUCKET_FILL_WINDOW_SECONDS = 10 * 60

# Once matched, each member's qualifying match must land inside this window;
# past it a member with no result forfeits (refunded — never graded on a guess).
BUCKET_SETTLE_WINDOW_SECONDS = 24 * 3600

# Engine-version stamp on every bucket settlement (dispute replay).
BUCKET_ENGINE_VERSION = "bucket-1"

# Contest lifecycle states.
STATUS_QUEUED = "queued"
STATUS_MATCHED = "matched"
STATUS_AWAITING_RESULT = "awaiting_result"
STATUS_SETTLED = "settled"
STATUS_REFUNDED = "refunded"
STATUS_CANCELED = "canceled"

# Room lifecycle states.
ROOM_OPEN = "open"
ROOM_AWAITING_RESULT = "awaiting_result"
ROOM_SETTLED = "settled"
ROOM_REFUNDED = "refunded"
