# Kế hoạch: Platform tạo video beat-sync từ keyword (ảnh + video + nhạc)

## Context (vì sao làm việc này)

Người dùng muốn xây một **SaaS đa người dùng**: nhập keyword → hệ thống tự tìm **video + ảnh** liên quan (Pexels/Pixabay) → **cắt ghép đồng bộ theo nhịp nhạc (beat-sync)**, với **voiceover tùy chọn** (UX kiểu "composable flow" — người dùng tự bật/tắt từng thành phần). Frontend là **web app mới riêng (Next.js)**, không dùng Streamlit hiện tại.

Khác biệt cốt lõi so với MoneyPrinterTurbo gốc: app gốc lấy **giọng đọc làm trục thời gian** và cắt clip theo độ dài cố định (5s). Sản phẩm mới lấy **nhạc làm trục thời gian** và cắt theo beat. Code hiện tại đã có sẵn nhiều thứ tái dùng được (search Pexels/Pixabay, ảnh→clip zoom, ghép ffmpeg, mix BGM), nhưng **chưa có**: search ảnh, beat detection, multi-tenant, DB, queue bền, object storage.

> **Mô hình repo:** **MONOREPO duy nhất** tại `Personal/VideoGenerator`. Copy toàn bộ code MoneyPrinterTurbo vào đây, từ giờ chỉ làm việc trong repo này (bỏ repo cũ). Một repo, nhiều service (engine / api / worker / frontend tách logic nhưng cùng repo). Các tham chiếu `app/services/...` + số dòng bên dưới là vị trí code **sau khi copy vào VideoGenerator**.

Kế hoạch chia làm **2 phần**: (A) Engine lõi — tính năng beat-sync + ảnh, làm trước để kiểm chứng chất lượng; (B) Hạ tầng SaaS — bọc engine thành nền tảng đa người dùng. Phân pha để ship dần.

---

## Cấu trúc monorepo (đích đến)

```
VideoGenerator/
  engine/        # = app/services + app/models + app/config + app/utils copy sang
                 #   (material, video, audio_analysis, task, voice, subtitle, llm...)
  api/           # FastAPI tier: controllers, router, asgi — chỉ HTTP/auth/DB/enqueue
  worker/        # Arq worker: pull job → gọi engine.task.start (cùng image với engine)
  frontend/      # Next.js app
  resource/      # fonts, songs (copy sang)
  storage/       # scratch dir cho ffmpeg (dev); prod dùng object storage
  migrations/    # Alembic
  pyproject.toml
  docker-compose.yml
```

**Chiến lược copy (Pha 0):** copy nguyên `app/` của MoneyPrinterTurbo vào VideoGenerator giữ nguyên cấu trúc để chạy được ngay, làm Phần A trên đó. Việc **tách `app/` → engine/api/worker** để ở Pha 1 (refactor có chủ đích, không làm cùng lúc với beat-sync để giảm rủi ro).

---

## PHẦN A — Engine lõi (làm trước, single-tenant)

Mục tiêu: copy code MoneyPrinterTurbo vào `VideoGenerator/` rồi tạo ra video montage beat-sync hoạt động được, test qua API/Streamlit cũ trước khi xây SaaS.

### A0. Copy engine vào monorepo
- Copy `app/`, `resource/`, `webui/`, `pyproject.toml`, `Dockerfile*`, `config.example.toml` từ MoneyPrinterTurbo sang `VideoGenerator/`.
- Khởi tạo git mới trong `VideoGenerator/`, chạy thử `uv sync --frozen` + `uv run python main.py` để xác nhận engine chạy được trước khi sửa.
- Bỏ repo MoneyPrinterTurbo cũ khỏi quy trình (chỉ giữ làm tham khảo nếu cần).

### A1. Search + tải ẢNH (Pexels + Pixabay)

File: `app/services/material.py`, `app/models/schema.py`

- Thêm `MaterialType` enum (`video`|`image`) và field `type: str = "video"` vào `MaterialInfo` (schema.py:51-56). Giữ kiểu `str` để không vỡ `utils.to_json()`.
- `search_images_pexels()` — `GET https://api.pexels.com/v1/search`, params `{query, per_page:30, orientation: aspect.name}`, parse key `photos`, lấy `src.large2x → original → large`, lọc theo width/height (sàn 480x480 như `preprocess_video`).
- `search_images_pixabay()` — `GET https://pixabay.com/api/`, params `{q, image_type:"photo", per_page:50, key, orientation, min_width, min_height}`, parse key `hits`, lấy `largeImageURL`.
- `save_image()` — song song với `save_video()` (material.py:168-225) nhưng validate bằng `PIL.Image.open().verify()`, lưu vào `cache_images/`.
- `download_materials()` — entry point mới (giữ `download_videos()` cũ để tương thích). Nhận `material_types=["video","image"]`, gọi cả 2 loại search, dedup theo url, tải về, trả về **list đường dẫn `.mp4` đã sẵn sàng** (ảnh được convert sang clip). Dùng round-robin key rotation `get_api_key()` có sẵn.
- Dùng lại `try/except` + `_get_tls_verify()` + `config.proxy` để 1 provider lỗi thì degrade về video-only thay vì fail job.

### A2. Tách helper ảnh→clip (tái dùng)

File: `app/services/video.py`

- Trích phần thân ảnh→clip (video.py:1048-1077, hiệu ứng Ken-Burns zoom) thành helper riêng:
  `image_to_clip_file(image_path, clip_duration, video_aspect, zoom=True) -> str`.
- Refactor `preprocess_video()` để gọi helper này (giữ nguyên hành vi). `material.py` import `video.image_to_clip_file` (không gây vòng lặp import vì `video.py` không import `material.py`).

### A3. Beat detection (thư viện tùy chọn)

File mới: `app/services/audio_analysis.py`; `pyproject.toml`

- Thêm `librosa` vào **optional extra** (không phải core dep, vì kéo theo numpy/scipy/numba nặng):
  `[project.optional-dependencies] beatsync = ["librosa==0.10.2", "soundfile>=0.12.1"]`
- `_import_librosa()` — lazy import, báo lỗi rõ nếu thiếu.
- `detect_beats(audio_file) -> (tempo_bpm, beat_times)` — dùng `librosa.beat.beat_track` + `frames_to_time`.
- `compute_segment_boundaries(beat_times, total_duration, beats_per_segment=4, min_segment=0.4, max_segment=8.0)` — gom mỗi N beat thành 1 mốc cắt; gộp segment quá ngắn (BPM cao/double-tempo); chẻ đôi segment quá dài (nhạc ambient ít beat); đảm bảo phủ kín `[0, total_duration]`.
- **Degrade graceful**: nếu thiếu librosa hoặc nhạc không có beat rõ → fallback cắt theo khoảng cố định, không crash job.

### A4. Hàm ghép beat-sync

File: `app/services/video.py`, `app/models/schema.py`

- Thêm `VideoConcatMode.beat_sync`. Thêm vào `VideoParams`: `material_types`, `beat_sync_enabled`, `beats_per_segment`, `music_file`, `image_clip_duration`, `voiceover_enabled`.
- Thêm hàm anh em `combine_videos_beatsync(combined_video_path, material_paths, music_file, audio_file=None, video_aspect, video_transition_mode, beats_per_segment, threads)` — **không** sửa đè `combine_videos()` vì chiến lược fill khác hẳn.
- Thuật toán (pseudocode):
  - `total_duration = max(music_duration, voiceover_duration nếu có)`.
  - `segments = compute_segment_boundaries(detect_beats(music_file), total_duration, beats_per_segment)`.
  - Cycle qua `material_paths`; mỗi segment cắt/loop/hold clip cho khớp đúng `seg_dur`:
    - video dài hơn segment → subclip; ngắn hơn → loop.
    - ảnh → re-render zoom đúng độ dài beat (hoặc dùng bản đã convert).
  - Resize về canvas (dùng lại block video.py:586-604).
  - Transition **rơi đúng vào beat**: anchor ở mép segment, độ dài clamp `min(1.0, seg_dur/2)`.
  - Ghép bằng `concat_video_clips_with_ffmpeg()` (có sẵn).

### A5. Voiceover tùy chọn (nhạc là trục chính)

File: `app/services/task.py`, `app/services/video.py`

- Thêm `voiceover_enabled` (master switch). Khi `False`: bỏ TTS + phụ đề, lấy `audio_duration` từ **độ dài nhạc** (theo tiền lệ nhánh `custom_audio_file` ở task.py:119-126).
- `get_video_materials()` (task.py:166-197): khi có ảnh hoặc beat-sync → gọi `download_materials()` thay vì `download_videos()`.
- `generate_final_videos()` (task.py:199-247): khi `beat_sync_enabled` → gọi `combine_videos_beatsync(...)`.
- Tổng quát hóa khối mix audio trong `generate_video()` (video.py:936-972): build layers = [voiceover nếu bật] + [music], `CompositeAudioClip` linh hoạt. Khi music-only nên nâng volume nhạc (bỏ mặc định 0.2).
- `music_file` resolve qua `get_bgm_file()`/`_resolve_bgm_file_path()` để sandbox path trong `resource/songs`.

### Files Phần A
- `app/services/material.py` — search/tải ảnh + `download_materials`
- `app/services/video.py` — `image_to_clip_file`, `combine_videos_beatsync`, mix audio
- `app/services/audio_analysis.py` (mới) — beat detection
- `app/services/task.py` — nhánh materials + final video + music-only
- `app/models/schema.py` — enum + params mới
- `pyproject.toml` — extra `beatsync`

---

## PHẦN B — Hạ tầng SaaS (bọc engine)

Nguyên tắc: **mở rộng repo này thành 1 codebase, 2 entrypoint** (api nhẹ + worker nặng), không viết lại, không bọc qua RPC ngoài.

### B1. Tách "seam" cho engine
- Engine hiện gọi thẳng `sm.state.update_task(...)`. Thay bằng **callback tiến độ**: `start(task_id, params, on_progress=callback)` để engine không cần biết tiến độ ghi vào đâu (Redis/Postgres/SSE).
- Bố cục: `engine/` (services + utils, nặng ffmpeg/whisper/moviepy), `api/` (FastAPI, chỉ HTTP/auth/DB/enqueue), `worker/` (pull job → gọi `engine.task.start`, cùng image với engine).

### B2. Multi-tenancy + Auth
- **Auth provider quản lý** (Clerk hoặc Supabase Auth) thay vì tự viết JWT. API chỉ nhận `user_id` đã verify; bật dependency router đang bị comment (`app/controllers/v1/video.py:37`).
- Thêm `user_id` vào mọi job; `GET /jobs` filter theo user; `GET/DELETE /jobs/{id}` check ownership.
- Storage namespacing: `utils.task_dir()` → `{user_id}/{task_id}/` (trên object storage là key prefix).
- Quota 2 lớp: rate-limit ở edge + **business quota khi enqueue** (giới hạn render/tháng, concurrent) — đây cũng là cách chặn chi phí Pexels/ffmpeg.

### B3. Data layer — Postgres (Redis chỉ còn làm transport)
- Bảng cốt lõi: `users`, `jobs` (thay dict trong state.py — id/user_id/status/progress/stage/params jsonb/error/timestamps), `assets` (output + upload, storage_key, metadata jsonb chứa bpm/beat grid), `usage` (quota/billing).
- Dùng Alembic. `params jsonb` để thêm field beat-sync không cần đổi schema.
- Live progress mirror vào Redis key TTL ngắn; Postgres update ở mốc chuyển stage.

### B4. Job queue bền + object storage
- Thay `app/controllers/manager/*` bằng **Arq** (asyncio + Redis, hợp FastAPI async sẵn có). Render **không** chạy trong process API nữa.
- Lifecycle: `POST /jobs` → validate + check quota + insert row `queued` + enqueue → trả `job_id` ngay. Worker pop → `processing` → `engine.task.start(on_progress=cb)` → upload file lên **S3-compatible (R2/B2 để né egress)** + insert `assets` → `complete`/`failed`.
- Retry chỉ cho stage transient (tải Pexels/TTS), **không** retry mù cả lần render ffmpeg. Tận dụng filename xác định + guard "đã tồn tại" để idempotent.
- Cancel: dùng cơ chế `stop_at` có sẵn + cờ Redis check giữa các stage.
- Download cho user: **presigned URL** (object store hỗ trợ range), `/stream` `/download` đổi thành redirect.

### B5. API surface (cho frontend mới)
- Auth: `GET /me`, `GET /me/usage`.
- Jobs: `POST /jobs` (body composable: keyword, aspect, target_duration, music, beat_sync{enabled,sensitivity,min/max clip}, voiceover{enabled,...}, subtitles, source, media_types), `GET /jobs`, `GET /jobs/{id}`, `DELETE /jobs/{id}`, `GET /jobs/{id}/events` (**SSE** tiến độ, fallback polling 2s).
- Assets/music: upload/list/delete music + materials, presigned download.
- Reuse `app/controllers/v1/llm.py`: `POST /llm/script`, `/terms`, `/metadata` cho "gợi ý keyword/script".

### B6. Frontend mới — Next.js + TS + Tailwind + shadcn/ui
- Auth SDK của Clerk/Supabase; TanStack Query cho poll/SSE.
- Màn hình: **Composer** (mỗi thành phần = 1 block tùy chọn map 1:1 với body `POST /jobs`), **Render queue** (progress bar qua SSE), **Job detail/preview**, **Library**, **Account/usage**.

### B7. Deploy
- Tách service: `api` (uvicorn, nhẹ, scale ngang), `worker` (Arq, cùng image engine, có ffmpeg/whisper — scale riêng, dùng `Dockerfile.gpu` cho NVENC), `frontend` (Next.js), `postgres`, `redis`, object storage managed.
- GPU worker pool cho `h264_nvenc` (đã whitelist trong video.py) để giảm thời gian/chi phí render; autoscale-to-zero theo độ sâu queue. Bỏ Streamlit khỏi prod (giữ để debug).

---

## Lộ trình ship dần (phasing)

- **Pha 0 — Copy engine + beat-sync MVP (single-tenant):** Copy code vào monorepo (A0) + Phần A đầy đủ + refactor `on_progress` callback. Kiểm chứng chất lượng beat-sync trên API/Streamlit cũ *trước khi* xây SaaS. → Ship: montage beat-sync chạy được trong VideoGenerator.
- **Pha 1 — Tách engine/api/worker + queue bền + object storage:** Refactor `app/` → `engine/`+`api/`+`worker/`; Arq workers + S3/R2 + presigned URL + tách container. Chưa cần auth. → Ship: render an toàn đa instance.
- **Pha 2 — Postgres + multi-tenant:** Postgres + Alembic + Clerk/Supabase auth + `user_id` + namespacing + ownership filter. → Ship: tài khoản thật, dữ liệu cô lập.
- **Pha 3 — Frontend Next.js:** composable flow + SSE + library. Bỏ Streamlit prod. → Ship: sản phẩm thật.
- **Pha 4 — Quota, billing, polish:** enforce plan limit, metering, Stripe, GPU autoscale, lifecycle cleanup storage. → Ship: SaaS thu phí được.

---

## Rủi ro lớn nhất (cần lưu ý)

1. **Chất lượng beat-sync (rủi ro sản phẩm #1):** beat detection trên nhạc người dùng upload không ổn định (tempo biến thiên, transient yếu). Giảm thiểu: MVP giới hạn **thư viện nhạc có sẵn đã phân tích trước** (lưu beat grid vào `assets.metadata`), cho chỉnh sensitivity + clamp min/max clip, luôn fallback cắt cố định. **Làm Pha 0 trước để kiểm chứng.**
2. **Rate limit & chi phí Pexels/Pixabay:** free tier throttle mạnh khi nhiều user. Giảm thiểu: cache mạnh (nâng `cache_videos` lên shared/object storage theo query), quota enqueue/user, budget tải dùng chung.
3. **Thời gian/chi phí render:** ffmpeg+moviepy+whisper tốn vài phút CPU/video. Giảm thiểu: cap concurrency + quota tháng, GPU NVENC, autoscale-to-zero, không auto-retry cả render.
4. **Storage phình to:** giảm thiểu lifecycle (xóa output free tier sau N ngày), chỉ giữ final + script, prune scratch ngay.
5. **Cancel/idempotency:** render nhiều stage phải re-run/stop an toàn — dựa vào `stop_at` + filename xác định.

---

## Verify (kiểm thử end-to-end)

- **Phần A (local, trước SaaS):**
  - Cài extra: `uv sync --frozen && uv pip install '.[beatsync]'`.
  - Unit test `compute_segment_boundaries` với các ca: nhạc bình thường, BPM rất cao, nhạc ambient ít beat, voiceover dài hơn nhạc.
  - Chạy 1 job qua API `POST /api/v1/videos` với `beat_sync_enabled=true`, `material_types=["video","image"]`, `voiceover_enabled=false`, 1 file nhạc trong `resource/songs` → kiểm tra `final-1.mp4`: các điểm cắt rơi đúng beat (mở bằng player, so với waveform), ảnh có zoom, không có gap.
  - Ca fallback: gỡ librosa → job vẫn chạy bằng cắt cố định (kiểm tra log warning).
- **Phần B (từng pha):**
  - Pha 1: submit job → file final nằm trên object storage, tải qua presigned URL; kill 1 worker → job khác vẫn chạy.
  - Pha 2: 2 user khác nhau không thấy/không xóa được job của nhau; storage tách theo `user_id`.
  - Pha 3: tạo job từ frontend, progress bar cập nhật realtime qua SSE, xem/tải video trong Library.
