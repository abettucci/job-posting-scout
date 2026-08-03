"use client";

import { useState } from "react";
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

interface Props {
  interview: Interview;
  onStageChange: (id: string, stage: InterviewStage) => void;
  onDelete: (id: string) => void;
  isDragging?: boolean;
}

export default function InterviewCard({ interview, onStageChange, onDelete, isDragging }: Props) {
  const [showStageMenu, setShowStageMenu] = useState(false);
  const [deleting, setDeleting] = useState(false);

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
          <p className="font-semibold text-white text-sm truncate">{interview.company}</p>
          <p className="text-xs text-slate-400 truncate">{interview.role}</p>
        </div>
        {interview.job_score != null && (
          <span className={`tag border flex-shrink-0 text-xs ${
            interview.job_score >= 80
              ? "bg-emerald-900 text-emerald-300 border-emerald-700"
              : interview.job_score >= 60
              ? "bg-yellow-900 text-yellow-300 border-yellow-700"
              : "bg-slate-800 text-slate-400 border-slate-600"
          }`}>
            {interview.job_score}/100
          </span>
        )}
      </div>

      {/* Date + location */}
      {scheduledDate && (
        <p className="text-xs text-slate-400">
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
            className="text-xs text-slate-400 hover:text-white bg-slate-700 rounded px-2 py-0.5 transition-colors"
          >
            → Move
          </button>
          {showStageMenu && (
            <div className="absolute z-20 left-0 top-6 bg-slate-700 border border-slate-600 rounded-lg shadow-xl min-w-[140px]">
              {ALL_STAGES.filter((s) => s !== interview.stage).map((s) => (
                <button
                  key={s}
                  onClick={() => { onStageChange(interview.interview_id, s); setShowStageMenu(false); }}
                  className="w-full text-left text-xs px-3 py-1.5 hover:bg-slate-600 text-slate-200 first:rounded-t-lg last:rounded-b-lg transition-colors"
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
            className="text-xs text-slate-400 hover:text-brand transition-colors"
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
            className="text-xs text-slate-400 hover:text-brand transition-colors"
          >
            🔗 Job
          </a>
        )}

        <button
          onClick={handleDelete}
          disabled={deleting}
          className="text-xs text-slate-600 hover:text-red-400 transition-colors ml-auto"
        >
          ✕
        </button>
      </div>
    </div>
  );
}
