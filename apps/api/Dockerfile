# One image for the API (default CMD) and the settlement worker (command override).
# Migrations run elsewhere (compose `migrate` service, deploy command).
FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app/apps/api

# The editable install needs `src/` present, or `import moneymatch_api` fails at runtime.
COPY apps/api/pyproject.toml ./
COPY apps/api/src ./src
RUN uv pip install --system --no-cache-dir -e .

# alembic.ini and migrations, copied after install so edits don't bust the deps layer.
COPY apps/api/ ./

ENV PYTHONUNBUFFERED=1
EXPOSE 8000

# Render services are reachable only through Render's proxy, so trust its X-Forwarded-For.
CMD ["sh", "-c", "uvicorn moneymatch_api.main:app --host 0.0.0.0 --port ${PORT:-8000} --proxy-headers --forwarded-allow-ips='*'"]
