# VideoGenerator

Turn a keyword into a beat-synced video montage: search related videos + images
(Pexels/Pixabay), cut them in sync with a music track, with optional AI voiceover.
A multi-user platform built as a polyglot monorepo.

```
VideoGenerator/
  backend/     # Python: render engine + FastAPI API + Arq worker (one package, two entrypoints)
  frontend/    # Next.js web app
  docker-compose.yml
```

## Architecture
- **Engine** (`backend/app/services`): material search/download, beat detection (librosa,
  optional), beat-sync assembly, TTS, subtitles, ffmpeg compose.
- **API** (`backend/app/controllers`, FastAPI): auth (JWT), multi-tenant `/jobs`, enqueues renders.
- **Worker** (`backend/app/queue`, Arq): pulls jobs from Redis, runs the engine, uploads
  outputs to object storage.
- **State/DB**: Postgres (users/jobs/assets) + Redis (queue + live progress).
- **Storage**: S3-compatible (MinIO/R2/S3) or local disk.

## Run the full stack (docker-compose)
```bash
docker compose up --build
```
- Frontend: http://localhost:3000
- API docs: http://localhost:8080/docs
- MinIO console: http://localhost:9001 (minioadmin / minioadmin)

Set `pexels_api_keys` / an LLM provider in `backend/config.toml`, and a real
`MPT_JWT_SECRET`, before generating videos.

## Fast local dev (recommended — no Docker rebuilds)

Run only the infra in Docker (pulled images, no build); run API + worker + frontend on the
host with hot-reload. You almost never need `docker compose build` this way.

```bash
# 1. Infra only (Postgres + Redis + MinIO) — fast, no rebuild
./scripts/infra.sh                 # = docker compose up -d redis postgres minio

# 2. Backend API (hot-reload) — reads backend/.env.dev (points at the dockerized infra)
cd backend && uv sync && ./run-api.sh

# 3. Render worker (separate terminal; restart after engine/worker code changes)
cd backend && ./run-worker.sh

# 4. Frontend (hot-reload)
cd frontend && npm install && npm run dev    # http://localhost:3000
```

API on http://localhost:8080, MinIO console http://localhost:9001.

**Tip:** code is volume-mounted into the Docker `api`/`worker` containers too, so even when
using the full stack you only need `docker compose restart api worker` after code changes —
`--build` is only needed when dependencies (requirements) change.

## Tests
```bash
cd backend && uv run --with pytest python -m pytest test/ -q
```

See `PLAN.md` for the full phased roadmap (Phase 4 = quotas/billing, not yet built).
