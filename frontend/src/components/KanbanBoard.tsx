"use client";

import { useState } from "react";
import type { Interview, InterviewStage } from "@/lib/api";
import InterviewCard from "./InterviewCard";

const ACTIVE_STAGES: InterviewStage[] = ["applied", "phone", "technical", "onsite", "offer"];
const ARCHIVE_STAGES: InterviewStage[] = ["accepted", "rejected", "withdrawn"];

const STAGE_LABELS: Record<InterviewStage, string> = {
  applied: "Applied",
  phone: "Phone",
  technical: "Technical",
  onsite: "Onsite",
  offer: "Offer",
  accepted: "Accepted",
  rejected: "Rejected",
  withdrawn: "Withdrawn",
};

const STAGE_COLORS: Record<string, string> = {
  applied: "border-slate-400 dark:border-slate-500",
  phone: "border-blue-500",
  technical: "border-purple-500",
  onsite: "border-yellow-500",
  offer: "border-emerald-500",
};

interface Props {
  interviews: Interview[];
  onStageChange: (id: string, stage: InterviewStage) => void;
  onDelete: (id: string) => void;
}

export default function KanbanBoard({ interviews, onStageChange, onDelete }: Props) {
  const [dragOver, setDragOver] = useState<InterviewStage | null>(null);
  const [archiveOpen, setArchiveOpen] = useState(false);

  const byStage = (stage: InterviewStage) => interviews.filter((i) => i.stage === stage);

  const handleDrop = (e: React.DragEvent, stage: InterviewStage) => {
    e.preventDefault();
    const id = e.dataTransfer.getData("interview_id");
    if (id) onStageChange(id, stage);
    setDragOver(null);
  };

  const archiveCount = ARCHIVE_STAGES.reduce((n, s) => n + byStage(s).length, 0);

  return (
    <div className="space-y-6">
      {/* Active Kanban columns */}
      <div className="flex gap-3 overflow-x-auto pb-4">
        {ACTIVE_STAGES.map((stage) => {
          const cards = byStage(stage);
          const isDragTarget = dragOver === stage;
          return (
            <div
              key={stage}
              className="flex-shrink-0 w-56"
              onDragOver={(e) => { e.preventDefault(); setDragOver(stage); }}
              onDragLeave={() => setDragOver(null)}
              onDrop={(e) => handleDrop(e, stage)}
            >
              {/* Column header */}
              <div className={`flex items-center justify-between mb-2 pb-1.5 border-b-2 ${STAGE_COLORS[stage]}`}>
                <span className="text-xs font-semibold text-slate-700 dark:text-slate-300 uppercase tracking-wide">
                  {STAGE_LABELS[stage]}
                </span>
                <span className="text-xs text-slate-500 bg-white dark:bg-slate-800 rounded-full px-1.5">
                  {cards.length}
                </span>
              </div>

              {/* Drop zone */}
              <div
                className={`min-h-24 rounded-lg transition-colors space-y-2 p-1 ${
                  isDragTarget ? "bg-slate-200/50 dark:bg-slate-700/50 border border-dashed border-slate-400 dark:border-slate-500" : ""
                }`}
              >
                {cards.map((i) => (
                  <InterviewCard
                    key={i.interview_id}
                    interview={i}
                    onStageChange={onStageChange}
                    onDelete={onDelete}
                  />
                ))}
                {cards.length === 0 && !isDragTarget && (
                  <p className="text-xs text-slate-600 text-center py-4">Drop here</p>
                )}
              </div>
            </div>
          );
        })}
      </div>

      {/* Archive section */}
      {archiveCount > 0 && (
        <div>
          <button
            onClick={() => setArchiveOpen((p) => !p)}
            className="flex items-center gap-2 text-sm text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-white transition-colors mb-3"
          >
            <span className={`transition-transform ${archiveOpen ? "rotate-90" : ""}`}>▶</span>
            Archive ({archiveCount})
          </button>

          {archiveOpen && (
            <div className="flex gap-3 overflow-x-auto pb-2">
              {ARCHIVE_STAGES.map((stage) => {
                const cards = byStage(stage);
                if (cards.length === 0) return null;
                return (
                  <div key={stage} className="flex-shrink-0 w-56">
                    <div className="flex items-center justify-between mb-2 pb-1.5 border-b-2 border-slate-300 dark:border-slate-600">
                      <span className="text-xs font-semibold text-slate-500 uppercase tracking-wide">
                        {STAGE_LABELS[stage]}
                      </span>
                      <span className="text-xs text-slate-600 bg-white dark:bg-slate-800 rounded-full px-1.5">
                        {cards.length}
                      </span>
                    </div>
                    <div className="space-y-2 p-1">
                      {cards.map((i) => (
                        <InterviewCard
                          key={i.interview_id}
                          interview={i}
                          onStageChange={onStageChange}
                          onDelete={onDelete}
                        />
                      ))}
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
