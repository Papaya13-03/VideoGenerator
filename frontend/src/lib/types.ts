export interface User {
  id: string;
  email: string;
  plan: string;
}

export interface TokenResponse {
  access_token: string;
  token_type: string;
}

export type JobStatus = "queued" | "processing" | "complete" | "failed";

export interface Job {
  id: string;
  status: JobStatus;
  progress: number;
  stage: string;
  error: string;
  params: Record<string, unknown>;
  created_at: string | null;
  finished_at: string | null;
  storage_urls?: { videos: string[]; combined_videos: string[] };
}

export interface JobList {
  jobs: Job[];
  total: number;
  page: number;
  page_size: number;
}

// Maps 1:1 to the backend VideoParams subset the composer exposes.
export interface CreateJobInput {
  video_subject: string;
  // MoneyPrinter-style: AI-generated, user-editable script + search terms.
  video_script?: string;
  video_terms?: string; // comma-separated; backend accepts str or list
  video_script_prompt?: string;
  video_aspect: "16:9" | "9:16" | "1:1";
  video_concat_mode: "random" | "sequential" | "beat_sync";
  beat_sync_enabled: boolean;
  beats_per_segment: number;
  material_types: string[];
  voiceover_enabled: boolean;
  music_file?: string;
  video_source: "pexels" | "pixabay";
}
