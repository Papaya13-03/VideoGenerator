#!/usr/bin/env sh
# Run the render worker locally, pointing at the dockerized infra.
# Restart this after changing engine/worker code (arq has no auto-reload).
cd "$(dirname "$0")" || exit 1
set -a
. ./.env.dev
set +a
exec uv run arq app.queue.worker.WorkerSettings
