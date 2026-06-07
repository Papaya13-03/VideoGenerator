import type { Job, JobStatus } from "@/lib/types";

const COLORS: Record<JobStatus, string> = {
  queued: "bg-neutral-700 text-neutral-200",
  processing: "bg-amber-600/30 text-amber-300",
  complete: "bg-emerald-600/30 text-emerald-300",
  failed: "bg-red-600/30 text-red-300",
};

export function StatusBadge({ status }: { status: JobStatus }) {
  return (
    <span className={`rounded-full px-2 py-0.5 text-xs ${COLORS[status]}`}>
      {status}
    </span>
  );
}

export function ProgressBar({ job }: { job: Job }) {
  return (
    <div className="h-2 w-full overflow-hidden rounded-full bg-neutral-800">
      <div
        className="h-full bg-indigo-500 transition-all"
        style={{ width: `${Math.min(100, job.progress)}%` }}
      />
    </div>
  );
}
