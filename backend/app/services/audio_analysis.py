"""Beat detection + segment boundaries cho chế độ beat-sync.

`librosa` là dependency nặng (numpy/scipy/numba) nên để ở optional extra `beatsync`
và chỉ import khi cần (lazy). Caller phải xử lý `BeatDetectionUnavailable` /
`BeatDetectionError` bằng cách fallback sang cắt theo khoảng cố định.
"""

import math
from typing import List, Tuple

from loguru import logger


class BeatDetectionUnavailable(RuntimeError):
    """Thiếu thư viện librosa (chưa cài extra `beatsync`)."""


class BeatDetectionError(RuntimeError):
    """Phát hiện beat thất bại (file lỗi, không đủ beat...)."""


def _import_librosa():
    try:
        import librosa  # noqa: WPS433 (lazy import có chủ đích)

        return librosa
    except ImportError as e:  # pragma: no cover - phụ thuộc môi trường
        raise BeatDetectionUnavailable(
            "Beat-sync cần extra 'beatsync': cài bằng `uv pip install '.[beatsync]'` "
            "(hoặc `pip install librosa soundfile`)."
        ) from e


def detect_beats(audio_file: str) -> Tuple[float, List[float]]:
    """Trả về (tempo_bpm, beat_times_seconds).

    Raises BeatDetectionUnavailable nếu thiếu librosa, BeatDetectionError nếu phân tích lỗi.
    """
    librosa = _import_librosa()
    try:
        y, sr = librosa.load(audio_file, sr=None, mono=True)
        # Tính onset envelope tường minh rồi truyền vào beat_track — ổn định hơn nhiều
        # so với để beat_track tự suy ra (nhất là tín hiệu sparse/percussive).
        onset_env = librosa.onset.onset_strength(y=y, sr=sr)
        tempo, beat_frames = librosa.beat.beat_track(
            onset_envelope=onset_env, sr=sr, units="frames"
        )
        beat_times = librosa.frames_to_time(beat_frames, sr=sr)
        tempo_val = float(tempo) if not hasattr(tempo, "__len__") else float(tempo[0])
        beats = [float(t) for t in beat_times]
        if len(beats) < 2:
            raise BeatDetectionError(
                f"không đủ beat phát hiện được ({len(beats)}) trong {audio_file}"
            )
        return tempo_val, beats
    except BeatDetectionError:
        raise
    except Exception as e:
        raise BeatDetectionError(f"phân tích beat thất bại cho {audio_file}: {e}") from e


def compute_segment_boundaries(
    beat_times: List[float],
    total_duration: float,
    beats_per_segment: int = 4,
    min_segment: float = 0.4,
    max_segment: float = 8.0,
) -> List[Tuple[float, float]]:
    """Gom beat thành các mốc cắt; trả về [(start, end), ...] phủ kín [0, total_duration].

    - Lấy mỗi `beats_per_segment` beat làm 1 mốc cắt.
    - Gộp segment ngắn hơn `min_segment` vào segment trước (chống BPM cao / double-tempo).
    - Chẻ đôi segment dài hơn `max_segment` (chống nhạc ambient ít beat).
    """
    beats_per_segment = max(1, int(beats_per_segment))

    # Lấy các mốc cắt thô từ beat, đảm bảo bắt đầu ở 0 và kết thúc ở total_duration.
    cut_points = [0.0]
    for i in range(0, len(beat_times), beats_per_segment):
        t = beat_times[i]
        if 0.0 < t < total_duration and t > cut_points[-1]:
            cut_points.append(t)
    if cut_points[-1] < total_duration:
        cut_points.append(total_duration)

    # Dựng segment thô.
    raw = [(cut_points[i], cut_points[i + 1]) for i in range(len(cut_points) - 1)]

    # Gộp segment quá ngắn vào segment liền trước.
    merged: List[Tuple[float, float]] = []
    for start, end in raw:
        if merged and (end - start) < min_segment:
            prev_start, _ = merged[-1]
            merged[-1] = (prev_start, end)
        else:
            merged.append((start, end))
    # Nếu segment đầu tiên quá ngắn (không có "trước" để gộp), gộp vào segment sau.
    if len(merged) >= 2 and (merged[0][1] - merged[0][0]) < min_segment:
        merged[1] = (merged[0][0], merged[1][1])
        merged.pop(0)

    # Chẻ đôi segment quá dài.
    result: List[Tuple[float, float]] = []
    for start, end in merged:
        dur = end - start
        if dur > max_segment:
            n = int(math.ceil(dur / max_segment))
            step = dur / n
            for k in range(n):
                s = start + k * step
                e = start + (k + 1) * step if k < n - 1 else end
                result.append((s, e))
        else:
            result.append((start, end))

    return result


def fixed_interval_boundaries(
    total_duration: float,
    segment_seconds: float = 2.0,
) -> List[Tuple[float, float]]:
    """Fallback khi không có librosa / không phát hiện được beat: cắt đều theo khoảng cố định."""
    segment_seconds = max(0.4, float(segment_seconds))
    n = max(1, int(math.ceil(total_duration / segment_seconds)))
    out = []
    for i in range(n):
        s = i * segment_seconds
        e = min((i + 1) * segment_seconds, total_duration)
        if e > s:
            out.append((s, e))
    return out


def get_segment_boundaries(
    music_file: str,
    total_duration: float,
    beats_per_segment: int = 4,
    fallback_segment_seconds: float = 2.0,
) -> Tuple[List[Tuple[float, float]], bool]:
    """Tiện ích cho assembler: trả về (segments, used_beats).

    Tự fallback sang cắt cố định nếu thiếu librosa hoặc phân tích beat lỗi.
    """
    try:
        _, beat_times = detect_beats(music_file)
        segments = compute_segment_boundaries(
            beat_times, total_duration, beats_per_segment=beats_per_segment
        )
        if segments:
            return segments, True
        logger.warning("beat detection trả về 0 segment, fallback sang cắt cố định")
    except BeatDetectionUnavailable as e:
        logger.warning(f"{e} -> fallback sang cắt cố định")
    except BeatDetectionError as e:
        logger.warning(f"{e} -> fallback sang cắt cố định")

    return fixed_interval_boundaries(total_duration, fallback_segment_seconds), False
