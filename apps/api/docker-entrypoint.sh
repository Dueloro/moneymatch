#!/bin/sh
# Reconcile the DB schema to head before starting whatever command was passed
# (the api, or a standalone worker). Baked into the image ENTRYPOINT so the
# migration runs no matter how the platform launches the container — a Render
# "Docker Command" override that starts uvicorn but forgets the migrate step is
# exactly what left beta stuck at migration 0010, which 500'd every authed
# request (`users.active_games` missing) including the demo-login button.
#
# `alembic upgrade head` is idempotent and the free tier runs a single instance,
# so there is no multi-instance migration race. If it fails the container exits
# (set -e) and the deploy fails loudly rather than serving a stale schema.
set -e
alembic upgrade head
exec "$@"
