"use client";

import { useParams, useRouter } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { ProgressBar, StatusBadge } from "@/components/JobStatus";

export default function JobDetailPage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();

  const { data: job, isLoading } = useQuery({
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

      <button
        onClick={remove}
        className="text-sm text-red-400 hover:text-red-300"
      >
        Delete job
      </button>
    </div>
  );
}
