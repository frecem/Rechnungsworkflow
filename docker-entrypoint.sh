#!/bin/sh
set -e

# Migrationen laufen bei jedem Start - idempotent (alembic macht nichts, wenn
# die DB schon auf dem aktuellen Stand ist), damit ein "docker compose up"
# nach einem Update automatisch das Schema mitzieht statt manuell exec'en zu muessen.
alembic upgrade head

exec uvicorn app.main:app \
    --host 0.0.0.0 \
    --port 8000 \
    --proxy-headers \
    --forwarded-allow-ips="${FORWARDED_ALLOW_IPS:-*}"
