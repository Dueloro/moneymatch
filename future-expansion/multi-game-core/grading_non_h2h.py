# Snapshot from apps/api/src/moneymatch_api/services/grading.py at tag pre-chess-only. Not imported or tested.

# Excerpts: win_next / stat_race branches. Related call sites (matchmaking.py,
# challenge_service.py, admin_risk_service.py, live_activity_service.py) are at the tag.


@dataclass
class _PlayerResult:
    """One seat's qualifying-match result, or the absence of one."""

    found: bool
    won: bool = False
    stat: float | None = None
    game_id: str | None = None


def _matched_ms(match: Match) -> int:
    assert match.matched_at is not None
    return int(match.matched_at.timestamp() * 1000)


def _first_qualifying_game(games: list[NormGame], matched_ms: int) -> NormGame | None:
    """The earliest finished game at/after `matched_at` (games arrive oldest-first)."""
    cutoff = matched_ms - GRADE_MATCH_SKEW_MS
    for game in games:
        if game.created_at_ms >= cutoff:
            return game
    return None


async def _player_result(
    match: Match, market: MarketDef, seat: MatchPlayer, rated_only: bool = True
) -> _PlayerResult:
    """Fetch this seat's first qualifying match after `matched_at` (win + stat)."""
    adapter = registry.get(match.game)
    games = await adapter.poll_eligible_games(
        # Rated only for real accounts: a casual game should not settle a money
        # duel. Brokered chess is unaffected, since it grades the exact game id
        # it created rather than scanning history.
        seat.host_account_id,
        _matched_ms(match),
        GameFilters(rated_only=rated_only),
    )
    game = _first_qualifying_game(games, _matched_ms(match))
    if game is None:
        return _PlayerResult(found=False)
    stat: float | None = None
    if market.kind == KIND_STAT_RACE and market.metric is not None:
        stat = game.metrics.get(market.metric)
        if stat is None:
            # Match played but the graded stat wasn't readable → not a result yet.
            return _PlayerResult(found=False, game_id=game.id)
    return _PlayerResult(found=True, won=game.won is True, stat=stat, game_id=game.id)


async def _grade_coordinated(
    match: Match,
    market: MarketDef,
    seats: list[MatchPlayer],
    now: datetime,
    rated_only: bool = True,
) -> GradeOutcome:
    """CS2/Dota: grade each seat's first finished match after `matched_at`."""
    a, b = seats
    ra = await _player_result(match, market, a, rated_only)
    rb = await _player_result(match, market, b, rated_only)

    stat_lines: dict[uuid.UUID, dict[str, Any]] = {}
    if market.kind == KIND_STAT_RACE and market.metric is not None:
        if ra.found:
            stat_lines[a.user_id] = {market.metric: ra.stat, "game_id": ra.game_id}
        if rb.found:
            stat_lines[b.user_id] = {market.metric: rb.stat, "game_id": rb.game_id}

    if ra.found and rb.found:
        return _decide(market, a, ra, b, rb, stat_lines)

    # Exactly one played → forfeit win, but only after window + grace.
    if ra.found or rb.found:
        if _grace_passed(match, now):
            winner = a if ra.found else b
            return GradeOutcome(
                WIN,
                winner_user_id=winner.user_id,
                stat_lines=stat_lines,
                detail={"reason": "forfeit"},
            )
        return GradeOutcome(PENDING, stat_lines=stat_lines)

    # Neither played.
    if _deadline_passed(match, now):
        return GradeOutcome(CANCEL, detail={"reason": "no_qualifying_game"})
    return GradeOutcome(PENDING)


def _decide(
    market: MarketDef,
    a: MatchPlayer,
    ra: _PlayerResult,
    b: MatchPlayer,
    rb: _PlayerResult,
    stat_lines: dict[uuid.UUID, dict[str, Any]],
) -> GradeOutcome:
    """Both seats produced a result → decide win/push per the market kind."""
    if market.kind == KIND_STAT_RACE:
        if ra.stat == rb.stat:
            return GradeOutcome(
                PUSH, stat_lines=stat_lines, detail={"reason": "equal_stat"}
            )
        winner = a if (ra.stat or 0) > (rb.stat or 0) else b
        return GradeOutcome(WIN, winner_user_id=winner.user_id, stat_lines=stat_lines)
    # win_next: win beats loss; both-win / both-lose → push.
    if ra.won == rb.won:
        return GradeOutcome(PUSH, detail={"reason": "both_same_result"})
    winner = a if ra.won else b
    return GradeOutcome(WIN, winner_user_id=winner.user_id)

# Dispatch inside grade():
#   if market.kind in (KIND_WIN_NEXT, KIND_STAT_RACE):
#       return await _grade_coordinated(match, market, seats, now, rated_only)
