"use client";

import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/lib/auth";
import { api, type Job } from "@/lib/api";
import Nav from "@/components/Nav";
import JobCard from "@/components/JobCard";

function dismissedDate(job: Job): number {
  const timestamp = new Date(job.dismissed_at ?? job.timestamp).getTime();
  return Number.isNaN(timestamp) ? 0 : timestamp;
}

export default function DismissedPage() {
  const { user, loading } = useAuth();
  const router = useRouter();
  const [jobs, setJobs] = useState<Job[]>([]);
  const [fetching, setFetching] = useState(true);

  useEffect(() => {
    if (!loading && !user) router.replace("/");
  }, [user, loading, router]);

  useEffect(() => {
    if (!user) return;
    setFetching(true);
    api.getJobs(0, 100, false, true)
      .then((result) => setJobs(result.items))
      .finally(() => setFetching(false));
  }, [user]);

  const dismissedJobs = useMemo(
    () => [...jobs].sort((a, b) => dismissedDate(b) - dismissedDate(a)),
    [jobs]
  );

  if (loading || !user) return null;

  return (
    <>
      <Nav />
      <main id="main-content" className="page-shell">
        <div className="border-b pb-6" style={{ borderColor: "var(--line)" }}>
          <p className="eyebrow">Archive</p>
          <h1 className="page-title mt-1">Dismissed jobs</h1>
          <p className="text-sm mt-2" style={{ color: "var(--ink-muted)" }}>
            Jobs you set aside. Restore one at any time to return it to Jobs.
          </p>
        </div>

        {fetching ? (
          <p className="text-slate-600 dark:text-slate-400 text-sm">Loading…</p>
        ) : dismissedJobs.length === 0 ? (
          <div className="card text-center py-12">
            <p className="text-slate-600 dark:text-slate-400">No dismissed jobs.</p>
          </div>
        ) : (
          <div className="space-y-3">
            {dismissedJobs.map((job) => (
              <JobCard
                key={job.job_id}
                job={job}
                onDismissedChange={(jobId, dismissed) => {
                  if (!dismissed) setJobs((current) => current.filter((job) => job.job_id !== jobId));
                }}
              />
            ))}
          </div>
        )}
      </main>
    </>
  );
}
