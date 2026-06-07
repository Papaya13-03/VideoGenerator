"""Unit tests for beat-sync segment boundaries (no librosa dependency)."""

from app.services import audio_analysis as aa


def _covers(segments, total, eps=1e-6):
    """Segments must be contiguous, non-overlapping, and cover [0, total]."""
    assert segments, "empty segments"
    assert abs(segments[0][0]) < eps, f"does not start at 0: {segments[0]}"
    assert abs(segments[-1][1] - total) < eps, f"does not end at {total}: {segments[-1]}"
    for (s, e), (ns, _ne) in zip(segments, segments[1:]):
        assert e <= s + (e - s) + eps  # each segment is valid
        assert abs(e - ns) < eps, f"gap/overlap between {(s, e)} and {(ns, _ne)}"
    for s, e in segments:
        assert e > s, f"non-positive segment: {(s, e)}"


def test_normal_beats_group_by_n():
    # Even beats every 0.5s over 10s, grouped by 4 -> 2s segments.
    beats = [i * 0.5 for i in range(21)]
    segs = aa.compute_segment_boundaries(beats, 10.0, beats_per_segment=4)
    _covers(segs, 10.0)
    durs = [round(e - s, 2) for s, e in segs]
    assert durs.count(2.0) >= 3, durs


def test_fast_bpm_merges_tiny_segments():
    # Beats every 0.05s, 1 beat/segment -> many tiny segments must be merged.
    beats = [i * 0.05 for i in range(40)]
    segs = aa.compute_segment_boundaries(beats, 2.0, beats_per_segment=1, min_segment=0.4)
    _covers(segs, 2.0)
    assert min(e - s for s, e in segs) >= 0.4 - 1e-6


def test_ambient_few_beats_splits_long_segments():
    # Only 2 beats over 30s -> long segments must be split by max_segment.
    segs = aa.compute_segment_boundaries([0.2, 9.8], 30.0, beats_per_segment=4, max_segment=8.0)
    _covers(segs, 30.0)
    assert max(e - s for s, e in segs) <= 8.0 + 1e-6


def test_fixed_interval_fallback_covers_duration():
    segs = aa.fixed_interval_boundaries(10.0, segment_seconds=2.0)
    _covers(segs, 10.0)
    assert len(segs) == 5


def test_get_segment_boundaries_falls_back_without_librosa(monkeypatch):
    # Force detect_beats to report the library is missing -> must fall back, not raise.
    def _boom(_):
        raise aa.BeatDetectionUnavailable("no librosa")

    monkeypatch.setattr(aa, "detect_beats", _boom)
    segs, used = aa.get_segment_boundaries("whatever.mp3", 8.0, beats_per_segment=4)
    assert used is False
    _covers(segs, 8.0)


def test_voiceover_longer_than_music_total_duration():
    # total_duration exceeds the last beat -> segments still cover up to total_duration.
    beats = [i * 0.5 for i in range(9)]  # up to 4.0s
    segs = aa.compute_segment_boundaries(beats, 12.0, beats_per_segment=4)
    _covers(segs, 12.0)
