FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    KCX_DATA_DIR=/app \
    KCX_DB_PATH=/data/kcx.db

WORKDIR /app

# Dev requirements (pytest) are installed too so `docker compose run --rm kcx pytest` works.
COPY requirements.txt requirements-dev.txt ./
RUN pip install --no-cache-dir -r requirements.txt -r requirements-dev.txt

COPY kcx/ kcx/
COPY certs/ certs/
COPY questions/ questions/
COPY scripts/ scripts/
COPY tests/ tests/
COPY pytest.ini ./

# Non-root user. /data must exist and be owned by kcx BEFORE switching user,
# otherwise a fresh named volume mounted there is root-owned and SQLite can't write.
RUN useradd --create-home --uid 1000 kcx \
    && mkdir -p /data \
    && chown kcx:kcx /data
USER kcx

EXPOSE 8080
CMD ["gunicorn", "--bind", "0.0.0.0:8080", "--workers", "2", "kcx:create_app()"]
