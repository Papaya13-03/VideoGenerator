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

## Run locally (without docker)
Backend:
```bash
cd backend
uv sync --frozen
uv pip install '.[beatsync]'          # optional: real beat detection
uv run python main.py                  # API on :8080
uv run arq app.queue.worker.WorkerSettings   # worker (needs Redis + use_arq=true)
```
Frontend:
```bash
cd frontend && npm install && npm run dev   # :3000
```

## Tests
```bash
cd backend && uv run --with pytest python -m pytest test/ -q
```

See `PLAN.md` for the full phased roadmap (Phase 4 = quotas/billing, not yet built).
