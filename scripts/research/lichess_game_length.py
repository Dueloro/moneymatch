"""Measure how long a chess game runs, by rating band.

This produces the numbers hard-coded in
`apps/api/src/moneymatch_api/services/skill_prior.py`. Run it to refresh them,
or to check they still hold:

    python scripts/research/lichess_game_length.py

Why sample arena tournaments rather than individual players: an arena puts a
wide rating spread into one place, already finished, and exposes every game
through a single public endpoint. Sampling players instead means choosing
players, and any such choice is a bias you then have to argue about.

Only standard chess counts. Variants (three-check, atomic, crazyhouse) have
different game lengths and are not what we quote a bar on.

Draws are excluded. `chess_moves` only counts matches you won, so the quantity
being modelled is the length of a game somebody won, and every decisive game is
a win for exactly one of its two players.

No authentication needed. Lichess asks for a descriptive User-Agent, which is
set below. Be considerate about how often this runs.
"""

from __future__ import annotations

import collections
import json
import math
import statistics
import urllib.request

API = "https://lichess.org"
STANDARD = {"bullet", "blitz", "rapid", "classical"}
TOURNAMENTS = 8
GAMES_PER_TOURNAMENT = 400
UA = "matchbook-research (game-length study)"


def _get(url: str, ndjson: bool = False):
    accept = "application/x-ndjson" if ndjson else "application/json"
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": accept})
    with urllib.request.urlopen(req, timeout=120) as resp:
        raw = resp.read().decode("utf-8", "replace")
    if ndjson:
        return [json.loads(line) for line in raw.splitlines() if line.strip()]
    return json.loads(raw)


def collect() -> list[tuple[int, int]]:
    """Return (mean rating of the two players, full moves) for each decisive game."""
    listing = _get(f"{API}/api/tournament")
    finished = [
        t
        for t in listing.get("finished", [])
        if (t.get("perf") or {}).get("key") in STANDARD
    ][:TOURNAMENTS]

    rows: list[tuple[int, int]] = []
    for tour in finished:
        url = (
            f"{API}/api/tournament/{tour['id']}/games"
            f"?max={GAMES_PER_TOURNAMENT}&moves=true"
            "&clocks=false&evals=false&opening=false"
        )
        try:
            games = _get(url, ndjson=True)
        except Exception as exc:  # noqa: BLE001 - a skipped arena is not fatal
            print(f"  skipped {tour['id']}: {exc}")
            continue
        for game in games:
            plies = len((game.get("moves") or "").split())
            if plies < 2:
                continue
            if game.get("winner") not in ("white", "black"):
                continue  # a draw is nobody's win
            try:
                players = game["players"]
                rating = (players["white"]["rating"] + players["black"]["rating"]) // 2
            except (KeyError, TypeError):
                continue
            # A "move" is White and Black together, which is how move counts are
            # quoted in chess and how the adapter records `chess_moves`.
            rows.append((rating, (plies + 1) // 2))
    return rows


def report(rows: list[tuple[int, int]]) -> None:
    bands: dict[int, list[int]] = collections.defaultdict(list)
    for rating, moves in rows:
        bands[min(2600, max(800, (rating // 200) * 200))].append(moves)

    everything = [m for _, m in rows]
    print(f"\ngames sampled: {len(everything)}")
    print(
        f"overall: mean {statistics.mean(everything):.1f}  "
        f"median {statistics.median(everything):.0f}  "
        f"sd {statistics.pstdev(everything):.1f}\n"
    )

    header = f"{'band':>6} {'n':>6} {'mean':>7} {'median':>7} {'sd':>6} {'sd/mean':>8}"
    print(header)
    print("-" * len(header))
    usable = []
    for band in sorted(bands):
        values = bands[band]
        if len(values) < 100:
            continue
        mean = statistics.mean(values)
        sd = statistics.pstdev(values)
        usable.append((band, mean, len(values), sd))
        print(
            f"{band:>6} {len(values):>6} {mean:>7.1f} "
            f"{statistics.median(values):>7.0f} {sd:>6.1f} {sd / mean:>8.2f}"
        )

    if len(usable) < 2:
        print("\nnot enough data to fit")
        return

    # Weighted least squares of mean moves on rating.
    weight = sum(n for _, _, n, _ in usable)
    mean_x = sum(b * n for b, _, n, _ in usable) / weight
    mean_y = sum(m * n for _, m, n, _ in usable) / weight
    cov = sum(n * (b - mean_x) * (m - mean_y) for b, m, n, _ in usable)
    var = sum(n * (b - mean_x) ** 2 for b, _, n, _ in usable)
    slope = cov / var
    intercept = mean_y - slope * mean_x
    sigma = sum(s * n for _, _, n, s in usable) / weight

    print("\nskill_prior.py should carry:")
    print(f"  _MOVES_INTERCEPT = {intercept:.2f}")
    print(f"  _MOVES_PER_ELO   = {slope:.5f}")
    print(f"  _MOVES_SIGMA     = {sigma:.2f}")
    print(f"\n  i.e. {intercept + slope * 1000:.0f} moves at 1000 Elo, ")
    print(f"       {intercept + slope * 2000:.0f} moves at 2000 Elo")

    # The bar sits in the left tail, so that is the fit worth checking.
    print("\nlow-tail check (predicted vs observed quantile):")
    print(f"{'band':>6} {'rate':>6} {'observed':>9} {'lognormal':>10} {'normal':>8}")
    for band, mean, _, sd in usable:
        values = sorted(bands[band])
        s2 = math.log(1 + (sd / mean) ** 2)
        m = math.log(mean) - s2 / 2
        for z, rate in ((0.385, 0.35), (0.842, 0.20), (1.282, 0.10)):
            observed = values[int(rate * (len(values) - 1))]
            print(
                f"{band:>6} {rate:>6.0%} {observed:>9} "
                f"{math.exp(m - z * math.sqrt(s2)):>10.1f} {mean - z * sd:>8.1f}"
            )


if __name__ == "__main__":
    print("sampling finished Lichess arenas (standard chess only)...")
    report(collect())
