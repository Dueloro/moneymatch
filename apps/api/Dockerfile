# MoneyMatch API image. Same codebase runs the api and (later) the worker via
# different entrypoints. Used by the docker-compose `full` profile and deploy.
FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app/apps/api

# Install deps + package. The editable install records module file locations at
# build time (PEP 660), so `src/` must be present before it runs — otherwise the
# redirector maps nothing and `import moneymatch_api` fails at runtime.
COPY apps/api/pyproject.toml ./
COPY apps/api/src ./src
RUN uv pip install --system --no-cache-dir -e .

# Remaining app files (alembic.ini, migrations, tests, docker-entrypoint.sh) —
# copied after install so edits here don't bust the dependency layer.
COPY apps/api/ ./
RUN chmod +x docker-entrypoint.sh

ENV PYTHONUNBUFFERED=1
EXPOSE 8000

# The entrypoint runs `alembic upgrade head` before exec'ing the command below,
# so the schema is always reconciled on start — regardless of any platform-level
# command override. CMD uses a shell so $PORT (Render injects it) is honoured,
# falling back to 8000 for local/compose runs.
ENTRYPOINT ["./docker-entrypoint.sh"]
CMD ["sh", "-c", "uvicorn moneymatch_api.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
