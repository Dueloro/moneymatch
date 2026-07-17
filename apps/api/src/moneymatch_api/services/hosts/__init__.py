"""Async host-game API clients (Lichess, FaceIt, OpenDota).

Accessed only through the game adapters (05-phase-2 · adapters, not imports);
never call these directly from routers/services. Each provides retries, typed
`HostUnavailable`/`HostNotFound` errors, and latency logging via `_client`.
"""
