"use client";

import { useRouter } from "next/navigation";
import type { Job } from "@/lib/api";

interface Props {
  job: Job;
}

function ScoreBadge({ score }: { score: number }) {
  const color =
    score >= 80
      ? "bg-emerald-900 text-emerald-300 border-emerald-700"
      : score >= 60
      ? "bg-yellow-900 text-yellow-300 border-yellow-700"
      : "bg-red-900 text-red-300 border-red-700";

  const dot =
    score >= 80 ? "bg-emerald-400" : score >= 60 ? "bg-yellow-400" : "bg-red-400";

  return (
    <span className={`tag border ${color}`}>
      <span className={`w-1.5 h-1.5 rounded-full ${dot}`} />
      {score}/100
    </span>
  );
}

function RecBadge({ rec }: { rec: Job["recommendation"] }) {
  const styles = {
    APPLY: "bg-emerald-950 text-emerald-300 border-emerald-700",
    MAYBE: "bg-yellow-950 text-yellow-300 border-yellow-700",
    SKIP: "bg-slate-800 text-slate-400 border-slate-600",
  };
  const icons = { APPLY: "🚀", MAYBE: "🤔", SKIP: "⏭️" };
  return (
    <span className={`tag border ${styles[rec]}`}>
      {icons[rec]} {rec}
    </span>
  );
}

export default function JobCard({ job }: Props) {
  const router = useRouter();
  const date = new Date(job.timestamp).toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
  });

  const trackUrl = `/interviews?job_id=${job.job_id}&company=${encodeURIComponent(job.company)}&role=${encodeURIComponent(job.title)}&score=${job.score}&url=${encodeURIComponent(job.url)}`;

  return (
    <div className="card space-y-3 hover:border-slate-600 transition-colors">
      <div className="flex items-start justify-between gap-2 flex-wrap">
        <div className="min-w-0">
          <a
            href={job.url}
            target="_blank"
            rel="noopener noreferrer"
            className="font-semibold text-white hover:text-brand transition-colors truncate block"
          >
            {job.title}
          </a>
          <p className="text-sm text-slate-400">
            {job.company} · {job.location}
          </p>
        </div>
        <div className="flex items-center gap-2 flex-shrink-0">
          <ScoreBadge score={job.score} />
          <RecBadge rec={job.recommendation} />
        </div>
      </div>

      {job.reasons.length > 0 && (
        <ul className="space-y-0.5">
          {job.reasons.slice(0, 5).map((r, i) => (
            <li key={i} className="text-sm text-slate-300">
              {r}
            </li>
          ))}
        </ul>
      )}

      {job.summary && (
        <p className="text-sm text-slate-400 italic leading-relaxed">{job.summary}</p>
      )}

      <div className="flex items-center justify-between pt-1 flex-wrap gap-2">
        <span className="text-xs text-slate-500">{date}</span>
        <div className="flex items-center gap-3">
          <button
            onClick={() => router.push(trackUrl)}
            className="text-xs text-slate-400 hover:text-white transition-colors"
          >
            + Track Interview
          </button>
          <a
            href={job.url}
            target="_blank"
            rel="noopener noreferrer"
            className="text-xs text-brand hover:text-brand-light transition-colors"
          >
            View on LinkedIn →
          </a>
        </div>
      </div>
    </div>
  );
}
