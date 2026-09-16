# syntax=docker/dockerfile:1
# ------------------------------------------------------------------
# AI Vendor Outreach Platform - backend image
# Serves the FastAPI application with gunicorn + uvicorn workers.
# The same image runs the queue worker and the maintenance scheduler
# via alternate commands (see docker-compose.yml).
# No secrets are baked in: every secret comes from the environment.
# ------------------------------------------------------------------
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /srv/app

# curl is used by debugging healthchecks; kept small and non-recursive.
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY alembic.ini ./
COPY alembic ./alembic
COPY app ./app

EXPOSE 8000

# Auto-migrate once on start (idempotent). Set SKIP_AUTO_MIGRATE=1 to run
# `alembic upgrade head` manually (rolling multi-host deploys).
CMD ["sh", "-c", "if [ \"${SKIP_AUTO_MIGRATE:-0}\" != \"1\" ]; then alembic upgrade head; fi; exec gunicorn app.main:app -k uvicorn.workers.UvicornWorker -w \"${GUNICORN_WORKERS:-2}\" -b 0.0.0.0:8000 --access-logfile - --error-logfile -"]