"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/lib/auth";
import { api, type Job } from "@/lib/api";
import Nav from "@/components/Nav";
import JobCard from "@/components/JobCard";

function newestFirst(jobs: Job[]) {
  return [...jobs].sort((a, b) => new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime());
}

export default function FilteredJobsPage() {
  const { user, loading } = useAuth();
  const router = useRouter();
  const [jobs, setJobs] = useState<Job[]>([]);
  const [fetching, setFetching] = useState(true);
  const [nextCursor, setNextCursor] = useState<string | null>(null);
  const [loadingMore, setLoadingMore] = useState(false);
  const [restoringJobId, setRestoringJobId] = useState<string | null>(null);
  const [restoreError, setRestoreError] = useState("");
  const hiddenJobIds = useRef(new Set<string>());

  useEffect(() => {
    if (!loading && !user) router.replace("/");
  }, [user, loading, router]);

  useEffect(() => {
    if (!user) return;
    setFetching(true);
    api.getJobs(0, 50, false, false, true)
      .then((result) => {
        setJobs(result.items.filter((job) => !hiddenJobIds.current.has(job.job_id)));
        setNextCursor(result.next_cursor ?? null);
      })
      .finally(() => setFetching(false));
  }, [user]);

  const loadMore = async () => {
    if (!nextCursor || loadingMore) return;
    setLoadingMore(true);
    try {
      const result = await api.getJobs(0, 50, false, false, true, nextCursor);
      setJobs((current) => [
        ...current,
        ...result.items.filter((job) => !hiddenJobIds.current.has(job.job_id) && !current.some((item) => item.job_id === job.job_id)),
      ]);
      setNextCursor(result.next_cursor ?? null);
    } finally {
      setLoadingMore(false);
    }
  };

  const filteredJobs = useMemo(() => newestFirst(jobs), [jobs]);

  const keepInJobs = async (jobId: string) => {
    setRestoreError("");
    setRestoringJobId(jobId);
    try {
      await api.setJobFilterOverride(jobId, true);
      hiddenJobIds.current.add(jobId);
      setJobs((current) => current.filter((item) => item.job_id !== jobId));
    } catch (error: unknown) {
      setRestoreError(error instanceof Error ? error.message : "Could not keep this job.");
    } finally {
      setRestoringJobId(null);
    }
  };

  if (loading || !user) return null;

  return (
    <>
      <Nav />
      <main id="main-content" className="page-shell">
        <div className="border-b pb-6" style={{ borderColor: "var(--line)" }}>
          <p className="eyebrow">Audit</p>
          <h1 className="page-title mt-1">Auto-filtered jobs</h1>
          <p className="text-sm mt-2 max-w-3xl" style={{ color: "var(--ink-muted)" }}>
            These postings were saved but kept out of Jobs because a deterministic search or profile rule did not match.
            Review the reason on each card to spot false positives and refine Settings or the search filters. “Keep in Jobs”
            is explicit feedback: it restores that posting without erasing the original filter reason.
          </p>
        </div>

        {fetching ? (
          <p className="text-slate-600 dark:text-slate-400 text-sm">Loading…</p>
        ) : filteredJobs.length === 0 ? (
          <div className="card text-center py-12">
            <p className="text-slate-600 dark:text-slate-400">No jobs have been auto-filtered.</p>
          </div>
        ) : (
          <div className="space-y-3">
            {filteredJobs.map((job) => (
              <div key={job.job_id} className="space-y-2">
                <div className="flex justify-end">
                  <button
                    type="button"
                    onClick={() => keepInJobs(job.job_id)}
                    disabled={restoringJobId === job.job_id}
                    className="btn-ghost text-sm disabled:opacity-50"
                    title="Keep this job in the main queue while retaining the audit reason"
                  >
                    {restoringJobId === job.job_id ? "Keeping…" : "Keep in Jobs"}
                  </button>
                </div>
                <JobCard
                  job={job}
                  onAppliedChange={(jobId, applied) => {
                    if (applied) {
                      hiddenJobIds.current.add(jobId);
                      setJobs((current) => current.filter((item) => item.job_id !== jobId));
                    }
                  }}
                  onDismissedChange={(jobId, dismissed) => {
                    if (dismissed) {
                      hiddenJobIds.current.add(jobId);
                      setJobs((current) => current.filter((item) => item.job_id !== jobId));
                    }
                  }}
                />
              </div>
            ))}
          </div>
        )}
        {restoreError && <p role="alert" className="text-xs text-red-500">{restoreError}</p>}
        {nextCursor && (
          <div className="flex justify-center pt-5">
            <button type="button" onClick={loadMore} disabled={loadingMore} className="btn-ghost text-sm disabled:opacity-50">
              {loadingMore ? "Loading…" : "Load more filtered jobs"}
            </button>
          </div>
        )}
      </main>
    </>
  );
}
