# Two targets:
#   runtime (default, last stage): the slim image CI pushes and the homelab runs.
#   test: runtime + pytest and tests/, used by the local compose.yaml.

# ---- base: app code and runtime deps only
FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    KCX_DATA_DIR=/app \
    KCX_DB_PATH=/data/kcx.db

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY kcx/ kcx/
COPY certs/ certs/
COPY questions/ questions/
COPY scripts/ scripts/

# Non-root user. /data must exist and be owned by kcx BEFORE switching user,
# otherwise a fresh named volume mounted there is root-owned and SQLite can't write.
RUN useradd --create-home --uid 1000 kcx \
    && mkdir -p /data \
    && chown kcx:kcx /data
USER kcx

EXPOSE 8080
CMD ["gunicorn", "--bind", "0.0.0.0:8080", "--workers", "2", "kcx:create_app()"]

# ---- test: adds pytest and the tests so `docker compose run --rm kcx pytest` works
FROM base AS test
USER root
COPY requirements-dev.txt ./
RUN pip install --no-cache-dir -r requirements-dev.txt
COPY tests/ tests/
COPY pytest.ini ./
USER kcx

# ---- runtime: last stage, so a plain `docker build .` produces it
FROM base AS runtime
