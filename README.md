<div align="center">

# 🎬 VideoGenerator

### Turn a keyword into a beat-synced video — automatically.

Type a topic, pick a song, and get a short video where the clips and images
**cut on the beat**. AI writes the script and finds the footage; you stay in control
of every scene change.

*A multi-tenant video creation platform — Python render engine + FastAPI + Next.js.*

</div>

---

## ✨ What is this?

VideoGenerator is a self-hostable **SaaS platform** for making short-form videos
(Reels / Shorts / TikTok-style) from nothing but an idea.

You give it a **keyword** and a **music track**. It:

1. uses an **LLM** to draft a script and search terms (you can edit both),
2. pulls relevant **stock videos and photos** from Pexels / Pixabay,
3. detects the **beats** of your music, and
4. assembles a montage where **every scene change lands on a beat** — with an
   optional AI voiceover on top.

Unlike a one-shot generator, it's built as a real product: **user accounts, your own
API keys, a music library, a render queue, and a visual beat editor** so the result is
yours to shape — not a black box.

---

## 🌟 Features

### 🎵 Beat-synced editing
- **Automatic beat detection** (librosa) finds the rhythm of any track.
- **Visual beat editor** — a timeline where you can **add, drag, and delete** the exact
  scene-change points. Cuts land on *your* beats, not a fixed timer.
- **Trim your music** — drag handles to use just the chorus (or any slice) of a long song.
- Tune **beats-per-cut** for fast or slow pacing.

### 🖼️ Smart media sourcing
- Searches **both videos and images** from **Pexels** and **Pixabay** by keyword.
- Still images are turned into clips with a subtle **Ken-Burns zoom**.
- Portrait / landscape / square — clips are auto-resized and letterboxed to fit.

### 🧠 AI script & narration
- **One-click LLM generation** of the script and search terms — fully **editable**.
- **Optional voiceover**: music-only montage, or AI narration (TTS) mixed over the music.
- Works with **OpenAI, Groq, Gemini, Moonshot, DeepSeek, Qwen, Azure, OneAPI**.

### 🔑 Bring-your-own keys (per user)
- Each account stores its **own** Pexels / Pixabay / LLM / TTS keys — **encrypted at rest**.
- Renders use *your* keys, so cost and quota stay yours.
- Built-in **"get your API key"** links for every provider.

### 👥 Multi-tenant by design
- Email + password **accounts** (self-hosted JWT).
- Every render job, asset, and uploaded track is **owned and isolated** per user.
- Personal **music library** — upload your own `.mp3`s and reuse them.

### 🚀 Production-grade rendering
- Renders run on a **durable background queue** (Arq + Redis), not in the web request.
- Outputs land in **object storage** (S3 / MinIO / Cloudflare R2) with shareable links.
- **Live progress** in a render queue, a **library** of finished videos, and a
  **recover** action if a render finishes after a timeout.

---

## 🔁 How it works

```
   keyword ──▶ ① LLM script + terms (editable)
                     │
   music ─────▶ ② beat detection ──▶ ✎ you edit the cut points
                     │
                     ▼
   ③ fetch videos + images (Pexels / Pixabay)
                     │
                     ▼
   ④ cut & assemble on the beats  ──(+ optional voiceover, subtitles, BGM)
                     │
                     ▼
   ⑤ final video ──▶ object storage ──▶ your library
```

---

## 🧱 Architecture

A polyglot monorepo — one repo, cleanly separated services:

| Service | Stack | Role |
|---|---|---|
| **Engine** | Python · MoviePy · ffmpeg · librosa | Media search, beat detection, beat-sync assembly, TTS, compositing |
| **API** | FastAPI · SQLAlchemy | Auth, multi-tenant jobs & assets, enqueues renders |
| **Worker** | Arq | Pulls jobs, runs the engine, uploads results |
| **Frontend** | Next.js · TypeScript · Tailwind · React Query | Composer, beat editor, render queue, library, settings |
| **Data** | PostgreSQL · Redis | Users / jobs / assets · queue & live progress |
| **Storage** | S3 / MinIO / R2 | Rendered videos, uploaded music |

```
VideoGenerator/
├── backend/     # Python: engine + FastAPI API + Arq worker
└── frontend/    # Next.js web app
```

---

## 🖥️ The app

- **Composer** — keyword, AI script/terms, media source, aspect ratio, beat-sync, voiceover.
- **Beat editor** — waveform timeline with draggable beat markers + trim handles.
- **Render queue** — live progress for every job.
- **Library** — your finished videos, ready to preview and download.
- **Settings** — manage your provider API keys (masked, encrypted).

---

## 🚦 Getting started

The full stack (frontend, API, worker, Postgres, Redis, MinIO) runs with a single command:

```bash
docker compose up --build
# Frontend → http://localhost:3000
```

For local development without rebuilds, and full configuration details, see
**[backend/](backend/)**, **[frontend/](frontend/)**, and `docker-compose.yml`.

---

## 📦 Status

Built in phases — engine → durable queue & storage → multi-tenant accounts → web app →
per-user keys → music upload → beat editor. Billing/quotas are the planned next step
(see `PLAN.md`).

> Bring your own Pexels and LLM keys to generate. Beat detection and rendering run on CPU
> out of the box; GPU (NVENC) encoding is supported for faster renders.

<div align="center">
<sub>Made with FastAPI, Next.js, MoviePy &amp; librosa.</sub>
</div>
