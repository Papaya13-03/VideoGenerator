#!/usr/bin/env sh
# Start only the infrastructure (Postgres, Redis, MinIO) in Docker.
# These images are pulled, not built, so there is no slow rebuild.
cd "$(dirname "$0")/.." || exit 1
exec docker compose up -d redis postgres minio
