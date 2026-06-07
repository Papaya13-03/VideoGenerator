# Frontend (Next.js)

Web app for VideoGenerator — Next.js 14 (App Router) + TypeScript + Tailwind + React Query.
Talks to the backend over REST (`/api/v1`) using a JWT stored in localStorage.

## Screens
- `/login`, `/register` — self-hosted JWT auth
- `/composer` — the composable create-video flow (keyword, source, media types, aspect, beat-sync, voiceover)
- `/jobs` — render queue with live progress polling
- `/jobs/[id]` — job detail, live progress, video preview + download
- `/library` — finished videos

## Dev
```bash
npm install
NEXT_PUBLIC_API_BASE=http://localhost:8080/api/v1 npm run dev   # http://localhost:3000
```

`NEXT_PUBLIC_API_BASE` defaults to `http://localhost:8080/api/v1`.

## Build
```bash
npm run build
```
