"""Same-human / collusion detection for co-entry (IMPLEMENTATION_PHASES.md Phase 6).

Pure predicates over **identity fingerprints** — the signals that suggest two
accounts are one human: a shared device id, IP, or payment instrument. The rule
the phase asks for:

- Two accounts that **share any fingerprint signal cannot co-enter the same
  contest or 1v1** (blocked at entry) and are **flagged** for review.
- Everything else (win-dumping patterns, etc.) is a *flag → human review*, never
  an auto-ban — improvement and cheating can look alike.

A signal is a normalized `"kind:value"` token (e.g. `"device:abc123"`,
`"ip:1.2.3.4"`). **Unknown/empty signals never match** — two accounts we know
nothing about are not "the same human" by default (fail-open on absence of
evidence, so we never block a legitimate player for lacking a fingerprint; the
*positive* match is what blocks).

The fingerprint *source* (capturing device/IP/payment at request time) is an
integration concern wired in the entry path; this module is the decision, kept
pure so it unit-tests without a DB.
"""

from __future__ import annotations

from collections.abc import Iterable

# A fingerprint is the set of signal tokens known for an account right now.
Fingerprint = frozenset[str]


def make_fingerprint(
    *,
    device_id: str | None = None,
    ip: str | None = None,
    payment_id: str | None = None,
    extra: Iterable[str] = (),
) -> Fingerprint:
    """Build a fingerprint from the known signals, dropping blanks. Values are
    namespaced by kind so a device id can never collide with an IP."""
    tokens: set[str] = set()
    if device_id:
        tokens.add(f"device:{device_id.strip().lower()}")
    if ip:
        tokens.add(f"ip:{ip.strip().lower()}")
    if payment_id:
        tokens.add(f"payment:{payment_id.strip().lower()}")
    for e in extra:
        if e and e.strip():
            tokens.add(e.strip().lower())
    return frozenset(tokens)


def shares_signal(a: Fingerprint, b: Fingerprint) -> bool:
    """True iff the two fingerprints overlap on any known signal → likely the same
    human. Empty fingerprints (no known signals) never match."""
    return bool(a & b)


def can_co_enter(candidate: Fingerprint, existing: Iterable[Fingerprint]) -> bool:
    """Whether `candidate` may join a contest whose current entrants have the given
    fingerprints — i.e. it shares no signal with any of them."""
    return not any(shares_signal(candidate, e) for e in existing)


def colluding_players(
    fingerprints: dict[str, Fingerprint],
) -> list[tuple[str, str]]:
    """Every pair of player ids that share a signal (for a review flag). Sorted,
    each unordered pair once, deterministic."""
    ids = sorted(fingerprints)
    pairs: list[tuple[str, str]] = []
    for i, a in enumerate(ids):
        for b in ids[i + 1 :]:
            if shares_signal(fingerprints[a], fingerprints[b]):
                pairs.append((a, b))
    return pairs
