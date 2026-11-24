#!/bin/sh
# Container entrypoint for the API. Migrations and seeding are idempotent, so running them
# on every start is safe; with more than one API instance, run them as a release step instead.
set -e
alembic upgrade head
python -m app.seed
# --proxy-headers: trust X-Forwarded-For from the platform's proxy so rate limits see the
# real client IP. Restrict FORWARDED_ALLOW_IPS to your proxy where the platform allows it.
exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}" \
  --proxy-headers --forwarded-allow-ips "${FORWARDED_ALLOW_IPS:-*}"
