"use client";

import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";

export default function LibraryPage() {
  const { data, isLoading } = useQuery({
    queryKey: ["jobs", "library"],
    queryFn: () => api.listJobs(1, 100),
  });

  if (isLoading) return <p className="text-neutral-400">Loading...</p>;

  const done = (data?.jobs ?? []).filter(
    (j) => j.status === "complete" && (j.storage_urls?.videos?.length ?? 0) > 0,
  );

  if (!done.length) {
    return <p className="text-neutral-400">No finished videos yet.</p>;
  }

  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-semibold">Library</h1>
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        {done.map((job) => {
          const url = job.storage_urls!.videos[0];
          return (
            <Link
              key={job.id}
              href={`/jobs/${job.id}`}
              className="block rounded-xl border border-neutral-800 bg-neutral-900 p-3 hover:border-neutral-700"
            >
              <video src={url} className="w-full rounded-md" muted />
              <p className="mt-2 truncate text-sm">
                {(job.params?.video_subject as string) || job.id}
              </p>
            </Link>
          );
        })}
      </div>
    </div>
  );
}
