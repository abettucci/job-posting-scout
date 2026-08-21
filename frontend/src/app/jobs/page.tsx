"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/lib/auth";
import { api, Job } from "@/lib/api";
import Nav from "@/components/Nav";
import JobCard from "@/components/JobCard";

export default function JobsPage() {
  const { user, loading } = useAuth();
  const router = useRouter();

  const [jobs, setJobs] = useState<Job[]>([]);
  const [minScore, setMinScore] = useState(0);
  const [fetching, setFetching] = useState(true);

  useEffect(() => {
    if (!loading && !user) router.replace("/");
  }, [user, loading, router]);

  useEffect(() => {
    if (!user) return;
    setFetching(true);
    api.getJobs(minScore, 50).then((r) => setJobs(r.items)).finally(() => setFetching(false));
  }, [user, minScore]);

  if (loading || !user) return null;

  return (
    <>
      <Nav />
      <main className="max-w-5xl mx-auto px-4 py-6 space-y-6">
        <div className="flex items-center justify-between flex-wrap gap-3">
          <h1 className="font-semibold text-slate-900 dark:text-white text-lg">All Jobs</h1>
          <div className="flex items-center gap-2 text-sm">
            <label className="text-slate-600 dark:text-slate-400">Min score:</label>
            <div className="flex gap-1">
              {[0, 50, 70, 80, 90].map((v) => (
                <button
                  key={v}
                  onClick={() => setMinScore(v)}
                  className={`px-2.5 py-1 rounded-md text-xs font-medium transition-colors ${
                    minScore === v
                      ? "bg-brand text-white"
                      : "bg-white dark:bg-slate-800 text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-white"
                  }`}
                >
                  {v === 0 ? "All" : `${v}+`}
                </button>
              ))}
            </div>
          </div>
        </div>

        {fetching ? (
          <p className="text-slate-600 dark:text-slate-400 text-sm">Loading…</p>
        ) : jobs.length === 0 ? (
          <div className="card text-center py-12">
            <p className="text-slate-600 dark:text-slate-400">No jobs found for this filter.</p>
          </div>
        ) : (
          <div className="space-y-3">
            {jobs.map((j) => (
              <JobCard key={j.job_id} job={j} />
            ))}
          </div>
        )}
      </main>
    </>
  );
}
