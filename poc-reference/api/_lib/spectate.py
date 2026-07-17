"""Parse a Lichess game JSON into the spectator view shape (roadmap §3).

Pure (no I/O): the network fetch lives in ``lichess_service.get_current_game``;
this turns its raw payload into a :class:`SpectateResponse` — a move list, the
players, whose turn it is, and the clocks. The §3.4 decision is move-list +
clock fidelity rather than a full board stream, so that is all we extract.
"""

from __future__ import annotations

from typing import Optional

from _lib.schemas import SpectatePlayer, SpectateResponse

# Lichess statuses that mean the game is over (mirrors the adapter's list).
_FINISHED = {
    "mate", "resign", "stalemate", "timeout", "draw", "outoftime",
    "cheat", "noStart", "unknownFinish", "variantEnd",
}


def _player(side: dict) -> Optional[SpectatePlayer]:
    user = (side or {}).get("user") or {}
    name = user.get("name") or side.get("aiLevel") and f"Stockfish level {side['aiLevel']}"
    if not name:
        return None
    return SpectatePlayer(name=name, rating=side.get("rating"))


def unavailable(message: str) -> SpectateResponse:
    return SpectateResponse(available=False, message=message)


def parse_current_game(raw: Optional[dict]) -> SpectateResponse:
    """Build a SpectateResponse from a Lichess current-game payload."""
    if not raw or not raw.get("id"):
        return unavailable("No live game right now — start one on Lichess to watch it here.")

    moves_str = raw.get("moves") or ""
    moves = moves_str.split() if moves_str else []
    status = raw.get("status")
    finished = status in _FINISHED

    players = raw.get("players") or {}
    white = _player(players.get("white") or {})
    black = _player(players.get("black") or {})

    # Whose turn: white moves on even ply counts (0, 2, 4 …).
    turn: Optional[str] = None if finished else ("white" if len(moves) % 2 == 0 else "black")

    # Clocks arrive as centiseconds remaining after each ply (white, black, …).
    white_clock = black_clock = None
    clocks = raw.get("clocks")
    if isinstance(clocks, list) and clocks:
        whites = [c for i, c in enumerate(clocks) if i % 2 == 0]
        blacks = [c for i, c in enumerate(clocks) if i % 2 == 1]
        if whites:
            white_clock = max(0, whites[-1] // 100)
        if blacks:
            black_clock = max(0, blacks[-1] // 100)

    return SpectateResponse(
        available=True,
        game_id=raw.get("id"),
        url=f"https://lichess.org/{raw['id']}",
        speed=raw.get("speed"),
        white=white,
        black=black,
        moves=moves,
        turn=turn,
        white_clock=white_clock,
        black_clock=black_clock,
        finished=finished,
        status=status,
        winner=raw.get("winner"),
    )
