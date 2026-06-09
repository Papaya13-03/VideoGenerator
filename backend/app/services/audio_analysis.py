"""Beat detection + segment boundaries for beat-sync mode.

`librosa` is a heavy dependency (numpy/scipy/numba), so it lives in the optional
`beatsync` extra and is imported lazily. Callers must handle
`BeatDetectionUnavailable` / `BeatDetectionError` by falling back to fixed-interval cuts.
"""

import math
from typing import List, Tuple

from loguru import logger


class BeatDetectionUnavailable(RuntimeError):
    """librosa is missing (the `beatsync` extra is not installed)."""


class BeatDetectionError(RuntimeError):
    """Beat detection failed (bad file, not enough beats, ...)."""


def _import_librosa():
    try:
        import librosa  # lazy import on purpose

        return librosa
    except ImportError as e:  # pragma: no cover - environment dependent
        raise BeatDetectionUnavailable(
            "Beat-sync needs the 'beatsync' extra: install with "
            "`uv pip install '.[beatsync]'` (or `pip install librosa soundfile`)."
        ) from e


def detect_beats(audio_file: str) -> Tuple[float, List[float]]:
    """Return (tempo_bpm, beat_times_seconds).

    Raises BeatDetectionUnavailable if librosa is missing, BeatDetectionError on failure.
    """
    librosa = _import_librosa()
    try:
        y, sr = librosa.load(audio_file, sr=None, mono=True)
        # Compute the onset envelope explicitly and pass it to beat_track — far more
        # reliable than letting beat_track infer it (especially for sparse/percussive audio).
        onset_env = librosa.onset.onset_strength(y=y, sr=sr)
        tempo, beat_frames = librosa.beat.beat_track(
            onset_envelope=onset_env, sr=sr, units="frames"
        )
        beat_times = librosa.frames_to_time(beat_frames, sr=sr)
        tempo_val = float(tempo) if not hasattr(tempo, "__len__") else float(tempo[0])
        beats = [float(t) for t in beat_times]
        if len(beats) < 2:
            raise BeatDetectionError(
                f"too few beats detected ({len(beats)}) in {audio_file}"
            )
        return tempo_val, beats
    except BeatDetectionError:
        raise
    except Exception as e:
        raise BeatDetectionError(f"beat analysis failed for {audio_file}: {e}") from e


def compute_segment_boundaries(
    beat_times: List[float],
    total_duration: float,
    beats_per_segment: int = 4,
    min_segment: float = 0.4,
    max_segment: float = 8.0,
) -> List[Tuple[float, float]]:
    """Group beats into cut points; return [(start, end), ...] covering [0, total_duration].

    - Take every `beats_per_segment`-th beat as a cut point.
    - Merge any segment shorter than `min_segment` into the previous one
      (guards against high BPM / doubled tempo).
    - Split any segment longer than `max_segment` (guards against ambient music with few beats).
    """
    beats_per_segment = max(1, int(beats_per_segment))

    # Build raw cut points from beats, anchored at 0 and total_duration.
    cut_points = [0.0]
    for i in range(0, len(beat_times), beats_per_segment):
        t = beat_times[i]
        if 0.0 < t < total_duration and t > cut_points[-1]:
            cut_points.append(t)
    if cut_points[-1] < total_duration:
        cut_points.append(total_duration)

    # Build raw segments.
    raw = [(cut_points[i], cut_points[i + 1]) for i in range(len(cut_points) - 1)]

    # Merge segments that are too short into the previous one.
    merged: List[Tuple[float, float]] = []
    for start, end in raw:
        if merged and (end - start) < min_segment:
            prev_start, _ = merged[-1]
            merged[-1] = (prev_start, end)
        else:
            merged.append((start, end))
    # If the first segment is too short (no previous to merge into), merge it forward.
    if len(merged) >= 2 and (merged[0][1] - merged[0][0]) < min_segment:
        merged[1] = (merged[0][0], merged[1][1])
        merged.pop(0)

    # Split segments that are too long.
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
    """Fallback when librosa is unavailable / no beats detected: even fixed-interval cuts."""
    segment_seconds = max(0.4, float(segment_seconds))
    n = max(1, int(math.ceil(total_duration / segment_seconds)))
    out = []
    for i in range(n):
        s = i * segment_seconds
        e = min((i + 1) * segment_seconds, total_duration)
        if e > s:
            out.append((s, e))
    return out


def segments_from_cut_points(
    cut_points: List[float], total_duration: float
) -> List[Tuple[float, float]]:
    """Build contiguous segments from user-edited cut points (scene-change times)."""
    pts = [0.0] + sorted(p for p in cut_points if 0.0 < p < total_duration) + [float(total_duration)]
    return [(pts[i], pts[i + 1]) for i in range(len(pts) - 1) if pts[i + 1] > pts[i]]


def _cut_points_from_segments(segments: List[Tuple[float, float]]) -> List[float]:
    """Internal boundaries between segments (exclude 0 and total)."""
    return [round(end, 3) for (_s, end), _nxt in zip(segments, segments[1:])]


def _audio_duration(audio_file: str) -> float:
    try:
        librosa = _import_librosa()
        return float(librosa.get_duration(path=audio_file))
    except Exception:
        from moviepy import AudioFileClip

        clip = AudioFileClip(audio_file)
        try:
            return float(clip.duration)
        finally:
            clip.close()


def analyze_music(audio_file: str, beats_per_segment: int = 4) -> dict:
    """Analyze a track for the beat editor.

    Returns {duration, tempo, beats, cut_points, used_beats}. Falls back to fixed
    intervals (used_beats=False) if librosa is unavailable or detection fails.
    """
    duration = _audio_duration(audio_file)
    try:
        tempo, beats = detect_beats(audio_file)
        segments = compute_segment_boundaries(beats, duration, beats_per_segment=beats_per_segment)
        return {
            "duration": round(duration, 3),
            "tempo": round(tempo, 1),
            "beats": [round(b, 3) for b in beats],
            "cut_points": _cut_points_from_segments(segments),
            "used_beats": True,
        }
    except (BeatDetectionUnavailable, BeatDetectionError) as e:
        logger.warning(f"analyze_music fallback: {e}")
        segments = fixed_interval_boundaries(duration)
        return {
            "duration": round(duration, 3),
            "tempo": 0.0,
            "beats": [],
            "cut_points": _cut_points_from_segments(segments),
            "used_beats": False,
        }


def get_segment_boundaries(
    music_file: str,
    total_duration: float,
    beats_per_segment: int = 4,
    fallback_segment_seconds: float = 2.0,
) -> Tuple[List[Tuple[float, float]], bool]:
    """Helper for the assembler: return (segments, used_beats).

    Falls back to fixed-interval cuts if librosa is missing or beat analysis fails.
    """
    try:
        _, beat_times = detect_beats(music_file)
        segments = compute_segment_boundaries(
            beat_times, total_duration, beats_per_segment=beats_per_segment
        )
        if segments:
            return segments, True
        logger.warning("beat detection returned 0 segments, falling back to fixed interval")
    except BeatDetectionUnavailable as e:
        logger.warning(f"{e} -> falling back to fixed interval")
    except BeatDetectionError as e:
        logger.warning(f"{e} -> falling back to fixed interval")

    return fixed_interval_boundaries(total_duration, fallback_segment_seconds), False
