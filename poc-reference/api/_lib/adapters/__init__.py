"""Game adapters.

money match is game-agnostic at the core (overview §6). Every supported title
implements :class:`GameAdapter`; the contract, odds, catalog, and settlement
layers go through :mod:`registry`, never importing a specific adapter directly.
Chess (Lichess) is the only real adapter in Phase 1; ``stub_cs2`` exists purely
to prove the seams compile against a second game.
"""
