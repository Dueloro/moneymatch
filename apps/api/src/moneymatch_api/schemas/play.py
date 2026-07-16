"""Play schemas that carry across services + the API.

`Bracket` and `Forecast` are the honest, no-odds pairing disclosures shown on the
matched card ("Even duel — model gives you 52%"), the P2P analog of rake
disclosure (06-phase-3 · deliverable 2). Request/response models for the
`/play/*` endpoints are added in the endpoints commit; these two live here now
because the matchmaking math produces them.
"""

from __future__ import annotations

from pydantic import BaseModel


class Bracket(BaseModel):
    """How fair a chess pairing is, for honest pre-match disclosure (Elo-based)."""

    your_rating: int
    band_low: int
    band_high: int
    match_quality: float  # 1.0 at a coin-flip, decays as the matchup gets lopsided
    label: str


class Forecast(BaseModel):
    """The duel-forecast disclosure for a stat/chess pairing.

    `you_win_prob` is `P(you beat opponent)` from the model (held near 0.50 by
    the eligibility window); `label` is the honest one-liner for the matched card.
    """

    you_win_prob: float
    label: str
