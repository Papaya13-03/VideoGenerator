"use client";

import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";

type FieldDef = { name: string; label: string; type?: "select"; options?: string[] };

// Where to get each key. For LLM/TTS the link depends on the selected provider.
const LLM_KEY_URLS: Record<string, string> = {
  openai: "https://platform.openai.com/api-keys",
  groq: "https://console.groq.com/keys",
  gemini: "https://aistudio.google.com/app/apikey",
  moonshot: "https://platform.moonshot.cn/console/api-keys",
  deepseek: "https://platform.deepseek.com/api_keys",
  qwen: "https://dashscope.console.aliyun.com/apiKey",
  azure: "https://portal.azure.com/",
  oneapi: "https://github.com/songquanpeng/one-api",
};

const TTS_KEY_URLS: Record<string, string> = {
  azure:
    "https://portal.azure.com/#create/Microsoft.CognitiveServicesSpeechServices",
};

interface ProviderDef {
  id: string;
  title: string;
  hint: string;
  fields: FieldDef[];
  keyUrl?: string; // static "get key" link
  keyUrlByProvider?: Record<string, string>; // link depends on selected `provider` field
}

const PROVIDERS: ProviderDef[] = [
  {
    id: "pexels",
    title: "Pexels",
    hint: "API key(s) for video/image search. Comma-separate multiple keys.",
    keyUrl: "https://www.pexels.com/api/",
    fields: [{ name: "api_keys", label: "API key(s)" }],
  },
  {
    id: "pixabay",
    title: "Pixabay",
    hint: "API key(s) for video/image search.",
    keyUrl: "https://pixabay.com/api/docs/",
    fields: [{ name: "api_keys", label: "API key(s)" }],
  },
  {
    id: "llm",
    title: "LLM (script & terms)",
    hint: "Provider used to generate the script and search terms.",
    keyUrlByProvider: LLM_KEY_URLS,
    fields: [
      {
        name: "provider",
        label: "Provider",
        type: "select",
        options: ["openai", "groq", "gemini", "moonshot", "deepseek", "qwen", "azure", "oneapi"],
      },
      { name: "api_key", label: "API key" },
      { name: "base_url", label: "Base URL (optional)" },
      { name: "model_name", label: "Model name (optional)" },
    ],
  },
  {
    id: "tts",
    title: "TTS (voiceover)",
    hint: "Edge (default) needs no key. Azure needs a speech key + region.",
    keyUrlByProvider: TTS_KEY_URLS,
    fields: [
      { name: "provider", label: "Provider", type: "select", options: ["edge", "azure"] },
      { name: "api_key", label: "Azure speech key" },
      { name: "region", label: "Azure region" },
    ],
  },
  {
    id: "social",
    title: "Social auto-post (Upload-Post)",
    hint: "Auto-post finished videos to TikTok / Instagram via Upload-Post.",
    keyUrl: "https://app.upload-post.com",
    fields: [
      { name: "api_key", label: "Upload-Post API key" },
      { name: "username", label: "Upload-Post username" },
    ],
  },
];

function ProviderCard({
  def,
  initial,
  configured,
  onSaved,
}: {
  def: (typeof PROVIDERS)[number];
  initial: Record<string, string>;
  configured: boolean;
  onSaved: () => void;
}) {
  const [values, setValues] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState("");

  useEffect(() => {
    setValues(initial || {});
  }, [initial]);

  async function save() {
    setBusy(true);
    setMsg("");
    try {
      await api.saveKeys(def.id, values);
      setMsg("Saved ✓");
      onSaved();
    } catch (e) {
      setMsg(e instanceof Error ? e.message : "Save failed");
    } finally {
      setBusy(false);
    }
  }

  async function remove() {
    setBusy(true);
    await api.deleteKeys(def.id);
    setValues({});
    onSaved();
    setBusy(false);
  }

  const input =
    "w-full rounded-md border border-neutral-700 bg-neutral-800 px-3 py-2 text-sm outline-none focus:border-neutral-500";

  // Link to where the user obtains this key (depends on selected provider for LLM/TTS).
  const keyUrl = def.keyUrlByProvider
    ? def.keyUrlByProvider[values.provider || ""]
    : def.keyUrl;

  return (
    <div className="rounded-xl border border-neutral-800 bg-neutral-900 p-4 space-y-3">
      <div className="flex items-center justify-between">
        <h2 className="font-medium">{def.title}</h2>
        {configured && (
          <span className="rounded-full bg-emerald-600/30 px-2 py-0.5 text-xs text-emerald-300">
            configured
          </span>
        )}
      </div>
      <p className="text-xs text-neutral-500">{def.hint}</p>
      {keyUrl && (
        <a
          href={keyUrl}
          target="_blank"
          rel="noopener noreferrer"
          className="inline-flex items-center gap-1 text-xs text-indigo-400 hover:text-indigo-300 hover:underline"
        >
          Get your API key ↗
        </a>
      )}
      {def.fields.map((f) => (
        <div key={f.name} className="space-y-1">
          <label className="text-xs text-neutral-400">{f.label}</label>
          {f.type === "select" ? (
            <select
              value={values[f.name] || ""}
              onChange={(e) => setValues((v) => ({ ...v, [f.name]: e.target.value }))}
              className={input}
            >
              <option value="">—</option>
              {f.options!.map((o) => (
                <option key={o} value={o}>
                  {o}
                </option>
              ))}
            </select>
          ) : (
            <input
              value={values[f.name] || ""}
              onChange={(e) => setValues((v) => ({ ...v, [f.name]: e.target.value }))}
              placeholder={f.label}
              className={input}
            />
          )}
        </div>
      ))}
      <div className="flex items-center gap-3">
        <button
          onClick={save}
          disabled={busy}
          className="rounded-md bg-indigo-600 px-4 py-2 text-sm hover:bg-indigo-500 disabled:opacity-50"
        >
          Save
        </button>
        {configured && (
          <button onClick={remove} disabled={busy} className="text-sm text-red-400 hover:text-red-300">
            Remove
          </button>
        )}
        {msg && <span className="text-xs text-neutral-400">{msg}</span>}
      </div>
    </div>
  );
}

export default function SettingsPage() {
  const { data, refetch, isLoading } = useQuery({
    queryKey: ["keys"],
    queryFn: () => api.listKeys(),
  });

  if (isLoading) return <p className="text-neutral-400">Loading...</p>;

  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-2xl font-semibold">API keys</h1>
        <p className="text-sm text-neutral-500">
          Your keys are stored encrypted and used only for your own renders.
        </p>
      </div>
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        {PROVIDERS.map((def) => (
          <ProviderCard
            key={def.id}
            def={def}
            configured={data?.[def.id]?.configured ?? false}
            initial={data?.[def.id]?.fields ?? {}}
            onSaved={refetch}
          />
        ))}
      </div>
    </div>
  );
}
