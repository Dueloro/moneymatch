"""A stand-in for the GC sidecar, speaking the same protocol.

The real sidecar needs a Steam login. This one needs nothing, so the rest of the
CS2 path — the client, the fraud checks, storage, the adapter and settlement —
can be exercised end to end before anyone has a refresh token.

It is a *protocol* double, not a stub of our own code: it answers on the same
endpoints with the same shapes, so the Python client is under test too. The one
thing it cannot prove is that Valve's Game Coordinator returns what we think it
does.

    python scripts/demo/mock_gc_sidecar.py --steam-id 76561198748110372
"""

from __future__ import annotations

import argparse
import json
import time
from http.server import BaseHTTPRequestHandler, HTTPServer

CONFIG: dict[str, object] = {}


def scoreboard(share_code: str) -> dict:
    """A realistic 5v5 scoreboard with the caller's SteamID in the roster."""
    you = str(CONFIG["steam_id"])
    others = [str(76561198000000000 + i) for i in range(1, 10)]
    roster = [you, *others]

    def line(i: int, steam_id: str) -> dict:
        return {
            "steamid": steam_id,
            "team": "a" if i < 5 else "b",
            "kills": int(CONFIG["kills"]) if i == 0 else 14 + (i % 5),
            "deaths": int(CONFIG["deaths"]) if i == 0 else 15 + (i % 4),
            "assists": 4 + (i % 3),
            "headshots": int(CONFIG["headshots"]) if i == 0 else 6 + (i % 4),
            "mvps": 3 if i == 0 else i % 3,
            "score": 60 - i,
        }

    return {
        "matchId": "3836574891868422813",
        # Now, not earlier. A wager grades the matches played *inside* its
        # window, so a match stamped before the pool opened is correctly
        # ignored, and a fixture that does that only proves the window works.
        "matchTime": int(time.time()),
        "scores": {"a": int(CONFIG["score_a"]), "b": int(CONFIG["score_b"])},
        "players": [line(i, sid) for i, sid in enumerate(roster)],
        # Absent is the normal case after about a month, and does not block
        # settlement: the scoreboard is what a wager grades on.
        "demoUrl": None,
        "expired": True,
    }


class Handler(BaseHTTPRequestHandler):
    def _send(self, status: int, body: dict) -> None:
        payload = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/health":
            self._send(200, {"ready": True, "queueDepth": 0})
        else:
            self._send(404, {"error": "not_found"})

    def do_POST(self) -> None:  # noqa: N802
        secret = CONFIG.get("secret")
        if secret and self.headers.get("X-GC-Secret") != secret:
            self._send(401, {"error": "unauthorized"})
            return

        length = int(self.headers.get("Content-Length") or 0)
        body = json.loads(self.rfile.read(length) or b"{}")

        if self.path == "/resolve":
            code = str(body.get("shareCode") or "")
            if not code:
                self._send(400, {"error": "shareCode is required"})
                return
            self._send(200, scoreboard(code))
        elif self.path == "/recent":
            self._send(200, {"matches": []})
        else:
            self._send(404, {"error": "not_found"})

    def log_message(self, fmt: str, *args) -> None:  # keep the output readable
        print(f"[mock-gc] {fmt % args}", flush=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8787)
    parser.add_argument("--steam-id", required=True)
    parser.add_argument("--secret", default="")
    parser.add_argument("--kills", type=int, default=24)
    parser.add_argument("--deaths", type=int, default=16)
    parser.add_argument("--headshots", type=int, default=12)
    parser.add_argument("--score-a", type=int, default=13)
    parser.add_argument("--score-b", type=int, default=9)
    args = parser.parse_args()

    CONFIG.update(vars(args))
    server = HTTPServer(("127.0.0.1", args.port), Handler)
    print(
        f"[mock-gc] listening on 127.0.0.1:{args.port} for {args.steam_id} "
        f"({args.kills}/{args.deaths}, {args.headshots} hs)",
        flush=True,
    )
    server.serve_forever()


if __name__ == "__main__":
    main()
