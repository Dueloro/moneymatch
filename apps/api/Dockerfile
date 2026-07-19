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

# Remaining app files (alembic.ini, migrations, tests) — copied after install so
# edits here don't bust the dependency layer.
COPY apps/api/ ./

ENV PYTHONUNBUFFERED=1
EXPOSE 8000

CMD ["uvicorn", "moneymatch_api.main:app", "--host", "0.0.0.0", "--port", "8000"]
