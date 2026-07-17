"""Game adapters: the platform's core asset (05-phase-2).

All host-API access goes through a `GameAdapter` resolved from `registry.get`;
settlement/metric code sees `NormGame` / `TelemetrySample`, never raw host JSON.
"""

from .base import GameAdapter, GameFilters, NormGame, TelemetrySample

__all__ = ["GameAdapter", "GameFilters", "NormGame", "TelemetrySample"]
