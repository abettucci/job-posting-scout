"use client";

import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/lib/auth";
import { api, Job } from "@/lib/api";
import Nav from "@/components/Nav";
import JobCard from "@/components/JobCard";

type SortBy = "posted_date" | "score";

export default function JobsPage() {
  const { user, loading } = useAuth();
  const router = useRouter();

  const [jobs, setJobs] = useState<Job[]>([]);
  const [minScore, setMinScore] = useState(0);
  const [fetching, setFetching] = useState(true);
  const [sortBy, setSortBy] = useState<SortBy>("posted_date");
  const [titleFilter, setTitleFilter] = useState("");

  useEffect(() => {
    if (!loading && !user) router.replace("/");
  }, [user, loading, router]);

  useEffect(() => {
    if (!user) return;
    setFetching(true);
    api.getJobs(minScore, 50).then((r) => setJobs(r.items)).finally(() => setFetching(false));
  }, [user, minScore]);

  const visibleJobs = useMemo(() => {
    const terms = titleFilter
      .split(",")
      .map((t) => t.trim().toLowerCase())
      .filter(Boolean);
    const filtered =
      terms.length === 0
        ? jobs
        : jobs.filter((j) => terms.some((t) => j.title.toLowerCase().includes(t)));

    return [...filtered].sort((a, b) => {
      if (sortBy === "score") return b.score - a.score;
      // posted_date: nulls (LinkedIn jobs, unparseable dates) always sink to the bottom
      if (a.posted_date === null && b.posted_date === null) return 0;
      if (a.posted_date === null) return 1;
      if (b.posted_date === null) return -1;
      return new Date(b.posted_date).getTime() - new Date(a.posted_date).getTime();
    });
  }, [jobs, titleFilter, sortBy]);

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

        <div className="flex items-center justify-between flex-wrap gap-3">
          <input
            type="text"
            value={titleFilter}
            onChange={(e) => setTitleFilter(e.target.value)}
            placeholder="Filter by title (e.g. senior, QA, golang — comma = OR)…"
            className="input max-w-sm text-sm"
          />
          <div className="flex items-center gap-2 text-sm">
            <label className="text-slate-600 dark:text-slate-400">Sort by:</label>
            <div className="flex gap-1">
              {([
                { id: "posted_date", label: "Posted date" },
                { id: "score", label: "Score" },
              ] as { id: SortBy; label: string }[]).map((o) => (
                <button
                  key={o.id}
                  onClick={() => setSortBy(o.id)}
                  className={`px-2.5 py-1 rounded-md text-xs font-medium transition-colors ${
                    sortBy === o.id
                      ? "bg-brand text-white"
                      : "bg-white dark:bg-slate-800 text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-white"
                  }`}
                >
                  {o.label}
                </button>
              ))}
            </div>
          </div>
        </div>

        {fetching ? (
          <p className="text-slate-600 dark:text-slate-400 text-sm">Loading…</p>
        ) : visibleJobs.length === 0 ? (
          <div className="card text-center py-12">
            <p className="text-slate-600 dark:text-slate-400">No jobs found for this filter.</p>
          </div>
        ) : (
          <div className="space-y-3">
            {visibleJobs.map((j) => (
              <JobCard key={j.job_id} job={j} />
            ))}
          </div>
        )}
      </main>
    </>
  );
}
