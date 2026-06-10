"use client";

import { useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { ProgressBar, StatusBadge } from "@/components/JobStatus";

export default function JobDetailPage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const [recovering, setRecovering] = useState(false);

  const { data: job, isLoading, refetch } = useQuery({
    queryKey: ["job", id],
    queryFn: () => api.getJob(id),
    // Keep polling until the job reaches a terminal state.
    refetchInterval: (q) => {
      const s = q.state.data?.status;
      return s === "complete" || s === "failed" ? false : 2000;
    },
  });

  if (isLoading || !job) return <p className="text-neutral-400">Loading...</p>;

  const videos = job.storage_urls?.videos ?? [];

  async function remove() {
    await api.deleteJob(id);
    router.push("/jobs");
  }

  async function recover() {
    setRecovering(true);
    try {
      await api.recoverJob(id);
      await refetch();
    } finally {
      setRecovering(false);
    }
  }

  return (
    <div className="space-y-5">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold">
          {(job.params?.video_subject as string) || "Job"}
        </h1>
        <StatusBadge status={job.status} />
      </div>

      {job.status !== "complete" && job.status !== "failed" && (
        <div className="space-y-2">
          <p className="text-sm text-neutral-400">
            {job.stage || "processing"} · {job.progress}%
          </p>
          <ProgressBar job={job} />
        </div>
      )}

      {job.status === "failed" && (
        <p className="rounded-md border border-red-800 bg-red-950/40 p-3 text-sm text-red-300">
          {job.error || "Render failed."}
        </p>
      )}

      {/* Recover a job whose render finished on disk but timed out before upload. */}
      {(job.status === "processing" || job.status === "failed") &&
        (job.storage_urls?.videos?.length ?? 0) === 0 && (
          <button
            onClick={recover}
            disabled={recovering}
            className="rounded-md border border-amber-700 bg-amber-600/20 px-4 py-2 text-sm text-amber-300 hover:bg-amber-600/30 disabled:opacity-50"
          >
            {recovering ? "Recovering..." : "Recover output (if already rendered)"}
          </button>
        )}

      {job.status === "complete" && videos.length > 0 && (
        <div className="space-y-4">
          {videos.map((url, i) => (
            <div key={i} className="space-y-2">
              <video src={url} controls className="w-full rounded-lg border border-neutral-800" />
              <a
                href={url}
                download
                className="inline-block rounded-md bg-indigo-600 px-4 py-2 text-sm hover:bg-indigo-500"
              >
                Download
              </a>
            </div>
          ))}
        </div>
      )}

      {job.status === "complete" && videos.length === 0 && (
        <p className="text-sm text-neutral-400">
          Completed, but no output URL is available yet.
        </p>
      )}

      {job.social_results && job.social_results.length > 0 && (
        <div className="space-y-1 rounded-md border border-neutral-800 bg-neutral-900 p-3 text-sm">
          <p className="font-medium text-neutral-300">📲 Social posting</p>
          {job.social_results.map((r, i) => (
            <p key={i} className={r.success ? "text-emerald-400" : "text-red-400"}>
              {r.success
                ? `✓ Posted${r.request_id ? ` (id ${r.request_id})` : ""}`
                : `✗ ${r.error || "Post failed"}`}
            </p>
          ))}
        </div>
      )}

      <button
        onClick={remove}
        className="text-sm text-red-400 hover:text-red-300"
      >
        Delete job
      </button>
    </div>
  );
}
