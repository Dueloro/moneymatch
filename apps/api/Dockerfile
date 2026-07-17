# MoneyMatch API image. Same codebase runs the api and (later) the worker via
# different entrypoints. Used by the docker-compose `full` profile and deploy.
FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app/apps/api

# Install dependencies first for layer caching.
COPY apps/api/pyproject.toml ./
RUN uv pip install --system --no-cache-dir -e .

COPY apps/api/ ./

ENV PYTHONUNBUFFERED=1
EXPOSE 8000

CMD ["uvicorn", "moneymatch_api.main:app", "--host", "0.0.0.0", "--port", "8000"]
