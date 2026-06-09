#!/usr/bin/env sh
# Run the API locally with hot-reload, pointing at the dockerized infra.
# Infra must be up first: docker compose up -d redis postgres minio
cd "$(dirname "$0")" || exit 1
set -a
. ./.env.dev
set +a
exec uv run uvicorn app.asgi:app --host 127.0.0.1 --port 8080 --reload
