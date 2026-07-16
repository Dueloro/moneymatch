"""Thin entrypoint for the settlement worker (deploys as its own process).

The loop lives in `apps/api` (`moneymatch_api.workers.settlement_worker`) so it
shares the exact adapters, services, and models the API uses (00-README §2 ·
"separate process, same codebase"). Locally, `make worker` runs the module in the
api venv; in deploy this file is the process command with the api package on the
path.
"""

from __future__ import annotations

from moneymatch_api.workers.settlement_worker import main

if __name__ == "__main__":
    main()
