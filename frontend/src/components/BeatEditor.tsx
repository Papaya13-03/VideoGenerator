"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "@/lib/api";

interface Props {
  assetId: string;
  audioUrl: string;
  beatsPerSegment: number;
  cutPoints: number[];
  onChange: (cutPoints: number[]) => void;
}

const fmt = (s: number) => {
  const m = Math.floor(s / 60);
  const sec = Math.floor(s % 60);
  return `${m}:${sec.toString().padStart(2, "0")}`;
};

export function BeatEditor({ assetId, audioUrl, beatsPerSegment, cutPoints, onChange }: Props) {
  const [duration, setDuration] = useState(0);
  const [beats, setBeats] = useState<number[]>([]);
  const [tempo, setTempo] = useState(0);
  const [loading, setLoading] = useState(false);
  const [playhead, setPlayhead] = useState(0);
  const audioRef = useRef<HTMLAudioElement>(null);
  const barRef = useRef<HTMLDivElement>(null);
  const dragIdx = useRef<number | null>(null);
  const moved = useRef(false);

  const analyze = useCallback(
    async (apply: boolean) => {
      setLoading(true);
      try {
        const r = await api.getBeats(assetId, beatsPerSegment);
        setDuration(r.duration);
        setBeats(r.beats);
        setTempo(r.tempo);
        if (apply || cutPoints.length === 0) onChange(r.cut_points);
      } finally {
        setLoading(false);
      }
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [assetId, beatsPerSegment],
  );

  // Auto-analyze when the track changes.
  useEffect(() => {
    if (assetId) analyze(false);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [assetId]);

  const sorted = [...cutPoints].sort((a, b) => a - b);

  function timeFromClientX(clientX: number): number {
    const bar = barRef.current;
    if (!bar || !duration) return 0;
    const rect = bar.getBoundingClientRect();
    const ratio = Math.min(1, Math.max(0, (clientX - rect.left) / rect.width));
    return Math.round(ratio * duration * 1000) / 1000;
  }

  function addCutAt(clientX: number) {
    const t = timeFromClientX(clientX);
    if (t <= 0 || t >= duration) return;
    onChange([...cutPoints, t].sort((a, b) => a - b));
  }

  function removeCut(value: number) {
    onChange(cutPoints.filter((c) => c !== value));
  }

  // Drag a marker.
  useEffect(() => {
    function onMove(e: PointerEvent) {
      if (dragIdx.current === null) return;
      moved.current = true;
      const t = timeFromClientX(e.clientX);
      const next = [...sorted];
      next[dragIdx.current] = Math.min(duration - 0.05, Math.max(0.05, t));
      onChange(next);
    }
    function onUp() {
      dragIdx.current = null;
    }
    window.addEventListener("pointermove", onMove);
    window.addEventListener("pointerup", onUp);
    return () => {
      window.removeEventListener("pointermove", onMove);
      window.removeEventListener("pointerup", onUp);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sorted, duration]);

  return (
    <div className="space-y-2 rounded-md border border-neutral-700 bg-neutral-800/50 p-3">
      <div className="flex items-center justify-between text-xs text-neutral-400">
        <span>
          Scene cuts: {cutPoints.length}
          {tempo ? ` · ~${Math.round(tempo)} BPM` : ""}
          {duration ? ` · ${fmt(duration)}` : ""}
        </span>
        <button
          type="button"
          onClick={() => analyze(true)}
          disabled={loading}
          className="rounded border border-neutral-600 px-2 py-1 hover:border-neutral-400 disabled:opacity-50"
        >
          {loading ? "Analyzing..." : "↻ Auto-detect beats"}
        </button>
      </div>

      <audio
        ref={audioRef}
        src={audioUrl}
        controls
        className="h-8 w-full"
        onLoadedMetadata={(e) => {
          if (!duration) setDuration(e.currentTarget.duration || 0);
        }}
        onTimeUpdate={(e) => setPlayhead(e.currentTarget.currentTime)}
      />

      {/* Timeline: click empty to add a cut, drag a marker to move, × to delete. */}
      <div
        ref={barRef}
        onClick={(e) => {
          if (moved.current) {
            moved.current = false;
            return;
          }
          addCutAt(e.clientX);
        }}
        className="relative h-16 w-full cursor-copy rounded bg-neutral-900"
      >
        {/* detected beat ticks (guides) */}
        {duration > 0 &&
          beats.map((b, i) => (
            <div
              key={`bt-${i}`}
              className="absolute top-0 h-2 w-px bg-neutral-600"
              style={{ left: `${(b / duration) * 100}%` }}
            />
          ))}

        {/* playhead */}
        {duration > 0 && (
          <div
            className="pointer-events-none absolute top-0 h-full w-0.5 bg-emerald-400"
            style={{ left: `${(playhead / duration) * 100}%` }}
          />
        )}

        {/* cut markers */}
        {duration > 0 &&
          sorted.map((c, i) => (
            <div
              key={`cut-${i}`}
              className="group absolute top-0 h-full"
              style={{ left: `${(c / duration) * 100}%`, transform: "translateX(-50%)" }}
            >
              <div
                onPointerDown={(e) => {
                  e.stopPropagation();
                  dragIdx.current = i;
                  moved.current = false;
                }}
                onDoubleClick={(e) => {
                  e.stopPropagation();
                  removeCut(c);
                }}
                title={`${c.toFixed(2)}s — drag to move, double-click to delete`}
                className="h-full w-1 cursor-ew-resize bg-indigo-400 group-hover:bg-indigo-300"
              />
              <button
                type="button"
                onClick={(e) => {
                  e.stopPropagation();
                  removeCut(c);
                }}
                className="absolute -top-1 left-1/2 hidden -translate-x-1/2 rounded-full bg-red-500 px-1 text-[10px] leading-none text-white group-hover:block"
              >
                ×
              </button>
            </div>
          ))}
      </div>

      <p className="text-[11px] text-neutral-500">
        Click the bar to add a cut · drag a marker to move · double-click (or ×) to delete.
        Each scene change lands on these times.
      </p>
    </div>
  );
}
