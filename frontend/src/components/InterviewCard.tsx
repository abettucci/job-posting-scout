"use client";

import { useState } from "react";
import { api } from "@/lib/api";
import type { Interview, InterviewStage } from "@/lib/api";
import { gcalUrl } from "@/lib/gcal";

const STAGE_LABELS: Record<InterviewStage, string> = {
  applied: "Applied",
  phone: "Phone Screen",
  technical: "Technical",
  onsite: "Onsite",
  offer: "Offer",
  accepted: "Accepted",
  rejected: "Rejected",
  withdrawn: "Withdrawn",
};

const ALL_STAGES: InterviewStage[] = [
  "applied", "phone", "technical", "onsite", "offer", "accepted", "rejected", "withdrawn",
];

const TERMINAL_STAGES: InterviewStage[] = ["accepted", "rejected", "withdrawn"];
const STALE_DAYS = 10;

interface Props {
  interview: Interview;
  onStageChange: (id: string, stage: InterviewStage) => void;
  onDelete: (id: string) => void;
  isDragging?: boolean;
}

export default function InterviewCard({ interview, onStageChange, onDelete, isDragging }: Props) {
  const [showStageMenu, setShowStageMenu] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [draftingFollowup, setDraftingFollowup] = useState(false);
  const [followup, setFollowup] = useState<{ subject: string; body: string } | null>(null);
  const [followupError, setFollowupError] = useState("");
  const [copied, setCopied] = useState(false);

  const isStale = !TERMINAL_STAGES.includes(interview.stage) &&
    Date.now() - new Date(interview.updated_at).getTime() > STALE_DAYS * 24 * 60 * 60 * 1000;

  const handleDraftFollowup = async () => {
    setDraftingFollowup(true);
    setFollowupError("");
    setFollowup(null);
    try {
      const result = await api.draftFollowup(interview.interview_id);
      setFollowup(result);
    } catch (e: unknown) {
      setFollowupError(e instanceof Error ? e.message : "Could not draft follow-up");
    } finally {
      setDraftingFollowup(false);
    }
  };

  const handleCopyFollowup = () => {
    if (!followup) return;
    navigator.clipboard.writeText(`Subject: ${followup.subject}\n\n${followup.body}`);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const scheduledDate = interview.scheduled_at
    ? new Date(interview.scheduled_at).toLocaleString("en-US", {
        month: "short", day: "numeric", hour: "2-digit", minute: "2-digit",
      })
    : null;

  const calUrl = interview.scheduled_at
    ? gcalUrl({
        title: `Interview at ${interview.company}`,
        startIso: interview.scheduled_at,
        location: interview.location ?? undefined,
        details: [
          `Role: ${interview.role}`,
          interview.job_score ? `Score: ${interview.job_score}/100` : "",
          interview.job_url ? `Job: ${interview.job_url}` : "",
        ].filter(Boolean).join(" | "),
      })
    : null;

  const handleDelete = async () => {
    if (!confirm(`Delete ${interview.company} interview?`)) return;
    setDeleting(true);
    onDelete(interview.interview_id);
  };

  return (
    <div
      className={`card cursor-grab active:cursor-grabbing space-y-2 ${isDragging ? "opacity-50" : ""}`}
      draggable
      onDragStart={(e) => e.dataTransfer.setData("interview_id", interview.interview_id)}
    >
      {/* Header */}
      <div className="flex items-start justify-between gap-1">
        <div className="min-w-0">
          <p className="font-semibold text-slate-900 dark:text-white text-sm truncate">{interview.company}</p>
          <p className="text-xs text-slate-600 dark:text-slate-400 truncate">{interview.role}</p>
        </div>
        {interview.job_score != null && (
          <span className={`tag border flex-shrink-0 text-xs ${
            interview.job_score >= 80
              ? "bg-emerald-900 text-emerald-300 border-emerald-700"
              : interview.job_score >= 60
              ? "bg-yellow-900 text-yellow-300 border-yellow-700"
              : "bg-white dark:bg-slate-800 text-slate-600 dark:text-slate-400 border-slate-300 dark:border-slate-600"
          }`}>
            {interview.job_score}/100
          </span>
        )}
      </div>

      {/* Date + location */}
      {scheduledDate && (
        <p className="text-xs text-slate-600 dark:text-slate-400">
          📅 {scheduledDate}
          {interview.location && ` · ${interview.location}`}
        </p>
      )}

      {/* Notes */}
      {interview.notes && (
        <p className="text-xs text-slate-500 line-clamp-2">{interview.notes}</p>
      )}

      {/* Actions */}
      <div className="flex items-center gap-1.5 pt-0.5 flex-wrap">
        {/* Stage selector */}
        <div className="relative">
          <button
            onClick={() => setShowStageMenu((p) => !p)}
            className="text-xs text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-white bg-slate-200 dark:bg-slate-700 rounded px-2 py-0.5 transition-colors"
          >
            → Move
          </button>
          {showStageMenu && (
            <div className="absolute z-20 left-0 top-6 bg-slate-200 dark:bg-slate-700 border border-slate-300 dark:border-slate-600 rounded-lg shadow-xl min-w-[140px]">
              {ALL_STAGES.filter((s) => s !== interview.stage).map((s) => (
                <button
                  key={s}
                  onClick={() => { onStageChange(interview.interview_id, s); setShowStageMenu(false); }}
                  className="w-full text-left text-xs px-3 py-1.5 hover:bg-slate-300 dark:hover:bg-slate-600 text-slate-800 dark:text-slate-200 first:rounded-t-lg last:rounded-b-lg transition-colors"
                >
                  {STAGE_LABELS[s]}
                </button>
              ))}
            </div>
          )}
        </div>

        {calUrl && (
          <a
            href={calUrl}
            target="_blank"
            rel="noopener noreferrer"
            className="text-xs text-slate-600 dark:text-slate-400 hover:text-brand transition-colors"
            title="Add to Google Calendar"
          >
            📅 Calendar
          </a>
        )}

        {interview.job_url && (
          <a
            href={interview.job_url}
            target="_blank"
            rel="noopener noreferrer"
            className="text-xs text-slate-600 dark:text-slate-400 hover:text-brand transition-colors"
          >
            🔗 Job
          </a>
        )}

        {isStale && (
          <button
            onClick={handleDraftFollowup}
            disabled={draftingFollowup}
            className="text-xs text-amber-600 dark:text-amber-400 hover:underline disabled:opacity-50"
            title={`No update in ${STALE_DAYS}+ days`}
          >
            {draftingFollowup ? "Drafting..." : "✉️ Draft follow-up"}
          </button>
        )}

        <button
          onClick={handleDelete}
          disabled={deleting}
          className="text-xs text-slate-600 hover:text-red-400 transition-colors ml-auto"
        >
          ✕
        </button>
      </div>

      {followupError && <p className="text-xs text-red-500 dark:text-red-400">{followupError}</p>}

      {followup && (
        <div className="border border-slate-300 dark:border-slate-600 rounded-lg p-3 space-y-2 bg-slate-50 dark:bg-slate-900/60">
          <p className="text-xs font-medium text-slate-800 dark:text-slate-200">{followup.subject}</p>
          <p className="text-xs text-slate-600 dark:text-slate-400 whitespace-pre-wrap">{followup.body}</p>
          <button
            onClick={handleCopyFollowup}
            className="text-xs text-brand hover:underline"
          >
            {copied ? "Copied ✓" : "Copy"}
          </button>
        </div>
      )}
    </div>
  );
}
