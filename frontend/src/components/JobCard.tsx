"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { api, type Job } from "@/lib/api";

interface Props {
  job: Job;
  // Lets each queue update instantly after an action, without a refetch.
  onAppliedChange?: (jobId: string, applied: boolean) => void;
  onDismissedChange?: (jobId: string, dismissed: boolean) => void;
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

const SENIORITY_LABELS: Record<string, string> = {
  internship: "Internship",
  entry: "Entry level",
  associate: "Associate",
  mid: "Mid-level",
  senior: "Senior",
  staff: "Staff/Principal",
  director: "Director",
  executive: "Executive",
};

const REGION_SCOPE: Record<string, { icon: string; label: string; style: string }> = {
  worldwide: { icon: "🌍", label: "Worldwide", style: "bg-white dark:bg-slate-800 text-slate-600 dark:text-slate-400 border-slate-300 dark:border-slate-600" },
  latam: { icon: "🌎", label: "LATAM", style: "bg-white dark:bg-slate-800 text-slate-600 dark:text-slate-400 border-slate-300 dark:border-slate-600" },
  restricted: { icon: "📍", label: "Region restricted", style: "bg-red-950 text-red-300 border-red-700" },
};

// Labeled "(est.)" everywhere it's shown — this is a regex guess over the
// posting's own text, never a verified employee count. See CompanySizeHint.
const COMPANY_SIZE: Record<string, { icon: string; label: string }> = {
  startup: { icon: "🌱", label: "Startup (est.)" },
  midsize: { icon: "🏢", label: "Mid-size (est.)" },
  enterprise: { icon: "🏛️", label: "Enterprise (est.)" },
};

function RecBadge({ rec }: { rec: Job["recommendation"] }) {
  const styles = {
    APPLY: "bg-emerald-950 text-emerald-300 border-emerald-700",
    MAYBE: "bg-yellow-950 text-yellow-300 border-yellow-700",
    SKIP: "bg-white dark:bg-slate-800 text-slate-600 dark:text-slate-400 border-slate-300 dark:border-slate-600",
  };
  const icons = { APPLY: "🚀", MAYBE: "🤔", SKIP: "⏭️" };
  return (
    <span className={`tag border ${styles[rec]}`}>
      {icons[rec]} {rec}
    </span>
  );
}

export default function JobCard({ job, onAppliedChange, onDismissedChange }: Props) {
  const router = useRouter();
  const [applying, setApplying] = useState(false);
  const [dismissing, setDismissing] = useState(false);
  const foundDate = new Date(job.timestamp).toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
  });
  const postedDate = job.posted_date
    ? new Date(job.posted_date).toLocaleDateString("en-US", { month: "short", day: "numeric" })
    : null;

  const trackUrl = `/interviews?job_id=${job.job_id}&company=${encodeURIComponent(job.company)}&role=${encodeURIComponent(job.title)}&score=${job.score}&url=${encodeURIComponent(job.url)}`;

  const handleToggleApplied = async () => {
    const next = !job.applied;
    setApplying(true);
    try {
      await api.setJobApplied(job.job_id, next);
      onAppliedChange?.(job.job_id, next);
    } catch (err) {
      console.error("Failed to update applied status", err);
    } finally {
      setApplying(false);
    }
  };

  const handleToggleDismissed = async () => {
    const next = !job.dismissed;
    setDismissing(true);
    try {
      await api.setJobDismissed(job.job_id, next);
      onDismissedChange?.(job.job_id, next);
    } catch (err) {
      console.error("Failed to update dismissed status", err);
    } finally {
      setDismissing(false);
    }
  };

  return (
    <article className="card space-y-4 hover:-translate-y-0.5 hover:border-orange-300 dark:hover:border-orange-400/50 transition-all duration-200">
      <div className="flex items-start justify-between gap-2 flex-wrap">
        <div className="min-w-0">
          <a
            href={job.url}
            target="_blank"
            rel="noopener noreferrer"
            className="font-bold text-lg text-slate-900 dark:text-white hover:text-brand transition-colors block"
          >
            {job.title}
          </a>
          <p className="text-sm text-slate-600 dark:text-slate-400">
            {job.company} · {job.location}
          </p>
          {(job.seniority_level || job.min_years_experience || job.region_scope || job.company_size_hint || job.experience_mentions.length > 0) && (
            <div className="flex items-center gap-1.5 mt-1 flex-wrap">
              {job.seniority_level && (
                <span className="tag border bg-white dark:bg-slate-800 text-slate-600 dark:text-slate-400 border-slate-300 dark:border-slate-600">
                  🎯 {SENIORITY_LABELS[job.seniority_level] ?? job.seniority_level}
                </span>
              )}
              {job.min_years_experience && (
                <span className="tag border bg-white dark:bg-slate-800 text-slate-600 dark:text-slate-400 border-slate-300 dark:border-slate-600">
                  📅 {job.min_years_experience}+ yrs
                </span>
              )}
              {job.region_scope && (
                <span className={`tag border ${REGION_SCOPE[job.region_scope].style}`}>
                  {REGION_SCOPE[job.region_scope].icon} {REGION_SCOPE[job.region_scope].label}
                </span>
              )}
              {job.company_size_hint && (
                <span
                  title={
                    job.company_size_source === "linkedin"
                      ? `LinkedIn: ${job.company_size_raw ?? "reported employee-count range"} — still an estimate, not an audited headcount`
                      : "Estimated from the posting's own text — not a verified employee count"
                  }
                  className="tag border bg-white dark:bg-slate-800 text-slate-600 dark:text-slate-400 border-slate-300 dark:border-slate-600"
                >
                  {COMPANY_SIZE[job.company_size_hint].icon}{" "}
                  {job.company_size_source === "linkedin"
                    ? COMPANY_SIZE[job.company_size_hint].label.replace("(est.)", "(LinkedIn)")
                    : COMPANY_SIZE[job.company_size_hint].label}
                </span>
              )}
              {job.experience_mentions.slice(0, 4).map((m, i) => (
                <span
                  key={i}
                  title="Extracted from the posting's own text — may miss or misread some mentions"
                  className="tag border bg-white dark:bg-slate-800 text-slate-600 dark:text-slate-400 border-slate-300 dark:border-slate-600"
                >
                  📅 {m.years}+ yrs · {m.context}
                </span>
              ))}
            </div>
          )}
        </div>
        <div className="flex items-center gap-2 flex-shrink-0">
          <ScoreBadge score={job.score} />
          <RecBadge rec={job.recommendation} />
        </div>
      </div>

      {job.reasons.length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {job.reasons.slice(0, 5).map((r, i) => {
            // scorer.py's prompt always prefixes a reason with ✅ (match) or ❌
            // (mismatch) against the candidate profile — style each accordingly.
            const isMatch = r.trim().startsWith("✅");
            const isMismatch = r.trim().startsWith("❌");
            const text = r.replace(/^[✅❌]\s*/, "");
            const style = isMatch
              ? "bg-emerald-950 text-emerald-300 border-emerald-700"
              : isMismatch
              ? "bg-red-950 text-red-300 border-red-700"
              : "bg-white dark:bg-slate-800 text-slate-600 dark:text-slate-400 border-slate-300 dark:border-slate-600";
            return (
              <span key={i} className={`tag border ${style}`}>
                {text}
              </span>
            );
          })}
        </div>
      )}

      {job.summary && (
        <p className="text-sm text-slate-600 dark:text-slate-400 italic leading-relaxed">{job.summary}</p>
      )}

      <div className="flex items-center justify-between border-t pt-3 flex-wrap gap-2" style={{ borderColor: "var(--line)" }}>
        <div className="flex items-center gap-3 text-xs text-slate-500">
          {postedDate && <span>Posted {postedDate}</span>}
          <span>Found {foundDate}</span>
        </div>
        <div className="flex items-center gap-3">
          <button
            onClick={() => router.push(`/resume?tailor_job_id=${job.job_id}&company=${encodeURIComponent(job.company)}&role=${encodeURIComponent(job.title)}`)}
            className="text-xs text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-white transition-colors"
          >
            ✂️ Tailor CV
          </button>
          <button
            onClick={() => router.push(`/resume?cover_job_id=${job.job_id}`)}
            className="text-xs text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-white transition-colors"
          >
            ✉️ Cover Letter
          </button>
          <button
            onClick={() => router.push(`/resume?brief_job_id=${job.job_id}`)}
            className="text-xs text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-white transition-colors"
          >
            🔎 Company brief
          </button>
          <button
            onClick={() => router.push(trackUrl)}
            className="text-xs text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-white transition-colors"
          >
            + Track Interview
          </button>
          {!job.dismissed && (
            <button
              onClick={handleToggleApplied}
              disabled={applying}
              title={job.applied ? "Move back to Jobs" : "Move to Applied"}
              className={`text-xs transition-colors disabled:opacity-50 ${
                job.applied
                  ? "text-emerald-600 dark:text-emerald-400 hover:text-emerald-700 dark:hover:text-emerald-300"
                  : "text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-white"
              }`}
            >
              {applying ? "…" : job.applied ? "✅ Applied" : "+ Applied"}
            </button>
          )}
          <button
            onClick={handleToggleDismissed}
            disabled={dismissing}
            title={job.dismissed ? "Restore to Jobs" : "Move to Dismissed"}
            className={`text-xs transition-colors disabled:opacity-50 ${
              job.dismissed
                ? "text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-white"
                : "text-slate-400 hover:text-red-500 dark:text-slate-500 dark:hover:text-red-400"
            }`}
          >
            {dismissing ? "…" : job.dismissed ? "↩ Restore" : "× Dismiss"}
          </button>
          <a
            href={job.url}
            target="_blank"
            rel="noopener noreferrer"
            className="text-xs text-brand hover:text-brand-light transition-colors"
          >
            View job posting →
          </a>
        </div>
      </div>
    </article>
  );
}
