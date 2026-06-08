"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import type { CreateJobInput } from "@/lib/types";

const ASPECTS = [
  { value: "9:16", label: "Portrait 9:16" },
  { value: "16:9", label: "Landscape 16:9" },
  { value: "1:1", label: "Square 1:1" },
] as const;

export default function ComposerPage() {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [error, setError] = useState("");

  // MoneyPrinter-style content: keyword -> AI script + terms, user-editable.
  const [scriptPrompt, setScriptPrompt] = useState("");
  const [script, setScript] = useState("");
  const [terms, setTerms] = useState("");
  const [uploading, setUploading] = useState(false);

  // User's uploaded music library.
  const { data: tracks, refetch: refetchMusic } = useQuery({
    queryKey: ["music"],
    queryFn: () => api.listMusic(),
  });

  const [form, setForm] = useState<CreateJobInput>({
    video_subject: "",
    video_aspect: "9:16",
    video_concat_mode: "beat_sync",
    beat_sync_enabled: true,
    beats_per_segment: 4,
    material_types: ["video", "image"],
    voiceover_enabled: false,
    music_file: "",
    music_asset_id: "",
    video_source: "pexels",
  });

  async function onUploadMusic(e: React.ChangeEvent<HTMLInputElement>) {
    const f = e.target.files?.[0];
    if (!f) return;
    setUploading(true);
    try {
      const asset = await api.uploadMusic(f);
      await refetchMusic();
      set("music_asset_id", asset.id); // auto-select the just-uploaded track
      set("music_file", "");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Upload failed");
    } finally {
      setUploading(false);
      e.target.value = "";
    }
  }

  function set<K extends keyof CreateJobInput>(k: K, v: CreateJobInput[K]) {
    setForm((f) => ({ ...f, [k]: v }));
  }

  function toggleMaterial(type: string) {
    setForm((f) => {
      const has = f.material_types.includes(type);
      const next = has
        ? f.material_types.filter((t) => t !== type)
        : [...f.material_types, type];
      return { ...f, material_types: next.length ? next : [type] };
    });
  }

  // Press "Generate with AI": create the script from the keyword, then search terms.
  async function generate() {
    if (!form.video_subject.trim()) {
      setError("Enter a keyword first");
      return;
    }
    setError("");
    setGenerating(true);
    try {
      const s = await api.generateScript(form.video_subject, scriptPrompt);
      setScript(s);
      const t = await api.generateTerms(form.video_subject, s);
      setTerms(t.join(", "));
    } catch (err) {
      setError(err instanceof Error ? err.message : "AI generation failed");
    } finally {
      setGenerating(false);
    }
  }

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    setBusy(true);
    try {
      const jobId = await api.createJob({
        ...form,
        // Pass the (possibly edited) script + terms so the backend uses them as-is.
        video_script: script.trim() || undefined,
        video_terms: terms.trim() || undefined,
        video_script_prompt: scriptPrompt.trim() || undefined,
        video_concat_mode: form.beat_sync_enabled
          ? "beat_sync"
          : form.video_concat_mode,
      });
      router.push(`/jobs/${jobId}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create job");
    } finally {
      setBusy(false);
    }
  }

  const card = "rounded-xl border border-neutral-800 bg-neutral-900 p-4 space-y-3";
  const labelCls = "text-sm font-medium text-neutral-300";
  const inputCls =
    "w-full rounded-md border border-neutral-700 bg-neutral-800 px-3 py-2 text-sm outline-none focus:border-neutral-500";

  return (
    <form onSubmit={submit} className="space-y-5">
      <h1 className="text-2xl font-semibold">Create a video</h1>

      {/* 1. Keyword + AI script/terms (MoneyPrinter flow) */}
      <div className={card}>
        <label className={labelCls}>Keyword / topic</label>
        <input
          required
          value={form.video_subject}
          onChange={(e) => set("video_subject", e.target.value)}
          placeholder="e.g. calm ocean waves at sunset"
          className={inputCls}
        />
        <input
          value={scriptPrompt}
          onChange={(e) => setScriptPrompt(e.target.value)}
          placeholder="Optional: extra prompt to steer the script"
          className={inputCls}
        />
        <button
          type="button"
          onClick={generate}
          disabled={generating}
          className="rounded-md bg-emerald-600 px-4 py-2 text-sm font-medium hover:bg-emerald-500 disabled:opacity-50"
        >
          {generating ? "Generating..." : "✨ Generate script & terms with AI"}
        </button>

        <div className="space-y-1">
          <label className="text-xs text-neutral-400">
            Script (editable — leave blank to auto-generate at render time)
          </label>
          <textarea
            value={script}
            onChange={(e) => setScript(e.target.value)}
            rows={5}
            placeholder="The AI-generated narration script appears here; edit freely."
            className={inputCls}
          />
        </div>
        <div className="space-y-1">
          <label className="text-xs text-neutral-400">
            Search terms (comma-separated — used to find clips/images)
          </label>
          <input
            value={terms}
            onChange={(e) => setTerms(e.target.value)}
            placeholder="ocean, waves, sunset, beach"
            className={inputCls}
          />
        </div>
      </div>

      {/* 2. Media source & type */}
      <div className={card}>
        <label className={labelCls}>Media source & type</label>
        <div className="flex gap-3">
          <select
            value={form.video_source}
            onChange={(e) =>
              set("video_source", e.target.value as CreateJobInput["video_source"])
            }
            className="rounded-md border border-neutral-700 bg-neutral-800 px-3 py-2 text-sm"
          >
            <option value="pexels">Pexels</option>
            <option value="pixabay">Pixabay</option>
          </select>
          {["video", "image"].map((t) => (
            <label key={t} className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                checked={form.material_types.includes(t)}
                onChange={() => toggleMaterial(t)}
              />
              {t}
            </label>
          ))}
        </div>
      </div>

      {/* 3. Aspect ratio */}
      <div className={card}>
        <label className={labelCls}>Aspect ratio</label>
        <div className="flex gap-2">
          {ASPECTS.map((a) => (
            <button
              key={a.value}
              type="button"
              onClick={() => set("video_aspect", a.value)}
              className={`rounded-md border px-3 py-1.5 text-sm ${
                form.video_aspect === a.value
                  ? "border-indigo-500 bg-indigo-600/20 text-indigo-300"
                  : "border-neutral-700 text-neutral-300"
              }`}
            >
              {a.label}
            </button>
          ))}
        </div>
      </div>

      {/* 4. Beat-sync */}
      <div className={card}>
        <label className="flex items-center justify-between">
          <span className={labelCls}>🎵 Beat-sync to music</span>
          <input
            type="checkbox"
            checked={form.beat_sync_enabled}
            onChange={(e) => set("beat_sync_enabled", e.target.checked)}
          />
        </label>
        {form.beat_sync_enabled && (
          <div className="space-y-2">
            <label className="text-xs text-neutral-400">
              Beats per cut: {form.beats_per_segment}
            </label>
            <input
              type="range"
              min={1}
              max={16}
              value={form.beats_per_segment}
              onChange={(e) => set("beats_per_segment", Number(e.target.value))}
              className="w-full"
            />
            <label className="text-xs text-neutral-400">Music track</label>
            <select
              value={form.music_asset_id || ""}
              onChange={(e) => {
                set("music_asset_id", e.target.value);
                set("music_file", "");
              }}
              className={inputCls}
            >
              <option value="">Random BGM (shared library)</option>
              {(tracks ?? []).map((t) => (
                <option key={t.id} value={t.id}>
                  {t.name}
                </option>
              ))}
            </select>
            <label className="inline-flex cursor-pointer items-center gap-2 rounded-md border border-neutral-700 px-3 py-1.5 text-sm text-neutral-300 hover:border-neutral-500">
              {uploading ? "Uploading..." : "⬆ Upload your music (.mp3)"}
              <input
                type="file"
                accept="audio/mpeg,.mp3"
                className="hidden"
                onChange={onUploadMusic}
                disabled={uploading}
              />
            </label>
          </div>
        )}
      </div>

      {/* 5. Voiceover */}
      <div className={card}>
        <label className="flex items-center justify-between">
          <span className={labelCls}>Voiceover (AI narration)</span>
          <input
            type="checkbox"
            checked={form.voiceover_enabled}
            onChange={(e) => set("voiceover_enabled", e.target.checked)}
          />
        </label>
        <p className="text-xs text-neutral-500">
          Off = music-only montage. On = narrate the script over the clips.
        </p>
      </div>

      {error && <p className="text-sm text-red-400">{error}</p>}
      <button
        type="submit"
        disabled={busy}
        className="rounded-md bg-indigo-600 px-5 py-2.5 text-sm font-medium hover:bg-indigo-500 disabled:opacity-50"
      >
        {busy ? "Creating..." : "Generate video"}
      </button>
    </form>
  );
}
