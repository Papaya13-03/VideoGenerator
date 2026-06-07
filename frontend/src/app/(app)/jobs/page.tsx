"use client";

import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { ProgressBar, StatusBadge } from "@/components/JobStatus";

export default function QueuePage() {
  const { data, isLoading } = useQuery({
    queryKey: ["jobs"],
    queryFn: () => api.listJobs(1, 50),
    refetchInterval: 3000, // live poll for progress
  });

  if (isLoading) return <p className="text-neutral-400">Loading...</p>;

  const jobs = data?.jobs ?? [];
  if (!jobs.length) {
    return (
      <div className="text-neutral-400">
        No jobs yet.{" "}
        <Link href="/composer" className="text-indigo-400 hover:underline">
          Create one
        </Link>
        .
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-semibold">Render queue</h1>
      <div className="space-y-3">
        {jobs.map((job) => (
          <Link
            key={job.id}
            href={`/jobs/${job.id}`}
            className="block rounded-xl border border-neutral-800 bg-neutral-900 p-4 hover:border-neutral-700"
          >
            <div className="flex items-center justify-between">
              <span className="text-sm font-medium">
                {(job.params?.video_subject as string) || job.id}
              </span>
              <StatusBadge status={job.status} />
            </div>
            <div className="mt-3">
              <ProgressBar job={job} />
            </div>
          </Link>
        ))}
      </div>
    </div>
  );
}
