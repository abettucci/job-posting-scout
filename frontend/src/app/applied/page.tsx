"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/lib/auth";
import { api, type Job } from "@/lib/api";
import Nav from "@/components/Nav";
import JobCard from "@/components/JobCard";

function appliedDate(job: Job): number {
  const value = job.applied_at ?? job.timestamp;
  const timestamp = new Date(value).getTime();
  return Number.isNaN(timestamp) ? 0 : timestamp;
}

export default function AppliedPage() {
  const { user, loading } = useAuth();
  const router = useRouter();
  const [jobs, setJobs] = useState<Job[]>([]);
  const [fetching, setFetching] = useState(true);
  const hiddenJobIds = useRef(new Set<string>());

  useEffect(() => {
    if (!loading && !user) router.replace("/");
  }, [user, loading, router]);

  useEffect(() => {
    if (!user) return;
    setFetching(true);
    api.getJobs(0, 100, true, false)
      .then((result) => setJobs(result.items.filter((job) => !hiddenJobIds.current.has(job.job_id))) )
      .finally(() => setFetching(false));
  }, [user]);

  const appliedJobs = useMemo(
    () => [...jobs].sort((a, b) => appliedDate(b) - appliedDate(a)),
    [jobs]
  );

  if (loading || !user) return null;

  return (
    <>
      <Nav />
      <main id="main-content" className="page-shell">
        <div className="border-b pb-6" style={{ borderColor: "var(--line)" }}>
          <p className="eyebrow">Pipeline</p>
          <h1 className="page-title mt-1">Applied jobs</h1>
          <p className="text-sm mt-2" style={{ color: "var(--ink-muted)" }}>
            Jobs you marked as applied, newest application first.
          </p>
        </div>

        {fetching ? (
          <p className="text-slate-600 dark:text-slate-400 text-sm">Loading…</p>
        ) : appliedJobs.length === 0 ? (
          <div className="card text-center py-12">
            <p className="text-slate-600 dark:text-slate-400">No applied jobs yet.</p>
            <p className="text-slate-500 text-sm mt-1">
              Mark a job as “+ Applied” from the Jobs page to move it here.
            </p>
          </div>
        ) : (
          <div className="space-y-3">
            {appliedJobs.map((job) => (
              <JobCard
                key={job.job_id}
                job={job}
                onAppliedChange={(jobId, applied) => {
                  if (!applied) {
                    hiddenJobIds.current.add(jobId);
                    setJobs((current) => current.filter((job) => job.job_id !== jobId));
                  }
                }}
                onDismissedChange={(jobId, dismissed) => {
                  if (dismissed) {
                    hiddenJobIds.current.add(jobId);
                    setJobs((current) => current.filter((job) => job.job_id !== jobId));
                  }
                }}
              />
            ))}
          </div>
        )}
      </main>
    </>
  );
}
