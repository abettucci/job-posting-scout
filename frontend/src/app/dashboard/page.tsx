"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/lib/auth";
import { api, Job, Search } from "@/lib/api";
import Nav from "@/components/Nav";
import JobCard from "@/components/JobCard";
import SearchForm from "@/components/SearchForm";

export default function DashboardPage() {
  const { user, loading } = useAuth();
  const router = useRouter();

  const [searches, setSearches] = useState<Search[]>([]);
  const [jobs, setJobs] = useState<Job[]>([]);
  const [showForm, setShowForm] = useState(false);
  const [fetching, setFetching] = useState(true);
  const [runningScaper, setRunningScaper] = useState(false);
  const [scraperMsg, setScraperMsg] = useState<string | null>(null);

  useEffect(() => {
    if (!loading && !user) router.replace("/");
  }, [user, loading, router]);

  useEffect(() => {
    if (!user) return;
    Promise.all([
      api.getSearches(),
      api.getJobs(user.score_threshold, 10, false, false),
    ]).then(([s, j]) => {
      setSearches(s);
      setJobs(j.items.filter((job) => !job.deal_breaker));
    }).finally(() => setFetching(false));
  }, [user]);

  const toggleSearch = async (s: Search) => {
    await api.patchSearch(s.search_id, !s.active);
    setSearches((prev) =>
      prev.map((x) => (x.search_id === s.search_id ? { ...x, active: !x.active } : x))
    );
  };

  const deleteSearch = async (id: string) => {
    await api.deleteSearch(id);
    setSearches((prev) => prev.filter((s) => s.search_id !== id));
  };

  const handleRunScraper = async () => {
    setRunningScaper(true);
    setScraperMsg(null);
    try {
      await api.runScraper();
      setScraperMsg("Scraper triggered. Results will arrive via Telegram in ~5 min.");
    } catch (e: unknown) {
      setScraperMsg(`Error: ${e instanceof Error ? e.message : "unknown error"}`);
    } finally {
      setRunningScaper(false);
    }
  };

  if (loading || !user) return null;

  const activeCount = searches.filter((s) => s.active).length;

  return (
    <>
      <Nav />
      <main id="main-content" className="page-shell">
        <section className="grid lg:grid-cols-[1fr_auto] gap-6 items-end border-b pb-8" style={{ borderColor: "var(--line)" }}>
          <div>
            <p className="eyebrow">Your search desk</p>
            <h1 className="page-title mt-2">Find the role worth<br className="hidden sm:block" /> applying to.</h1>
            <p className="mt-3 max-w-xl text-sm leading-6" style={{ color: "var(--ink-muted)" }}>A focused view of the searches, signals and job matches that deserve your attention today.</p>
          </div>
          <button onClick={handleRunScraper} disabled={runningScaper} className="btn-primary text-sm">
            {runningScaper ? "Checking sources…" : "Run a fresh scan"}
          </button>
        </section>
        {/* Stats row */}
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
          {[
            { label: "Searches", value: searches.length },
            { label: "Active", value: activeCount },
            { label: "Jobs found", value: jobs.length },
            { label: "Score threshold", value: `${user.score_threshold}/100` },
          ].map((s) => (
            <div key={s.label} className="card">
              <p className="text-3xl font-black tracking-[-0.06em] text-slate-900 dark:text-white">{s.value}</p>
              <p className="text-xs font-bold uppercase tracking-wider text-slate-600 dark:text-slate-400 mt-1">{s.label}</p>
            </div>
          ))}
        </div>

        {/* Manual scraper trigger */}
        {scraperMsg && (
          <div role="status" aria-live="polite" className="card py-3">
            <p className={`text-xs ${scraperMsg.startsWith("Error") ? "text-red-400" : "text-green-400"}`}>
              {scraperMsg}
            </p>
          </div>
        )}

        {/* Searches */}
        <section>
          <div className="flex items-center justify-between mb-3">
            <div><p className="eyebrow">Automations</p><h2 className="text-xl font-black tracking-[-0.04em] text-slate-900 dark:text-white">My searches</h2></div>
            {!showForm && (
              <button onClick={() => setShowForm(true)} className="btn-primary text-sm">
                + Add Search
              </button>
            )}
          </div>

          {showForm && (
            <div className="mb-3">
              <SearchForm
                onCreated={(s) => { setSearches((p) => [s, ...p]); setShowForm(false); }}
                onCancel={() => setShowForm(false)}
              />
            </div>
          )}

          {fetching ? (
            <p className="text-slate-600 dark:text-slate-400 text-sm">Loading…</p>
          ) : searches.length === 0 ? (
            <div className="card text-center py-8">
              <p className="text-slate-600 dark:text-slate-400 text-sm">No searches yet.</p>
              <p className="text-slate-500 text-xs mt-1">
                Add a search — a LinkedIn URL, a multi-board profile search, or a specific company — to start monitoring.
              </p>
            </div>
          ) : (
            <div className="space-y-2">
              {searches.map((s) => (
                <div key={s.search_id} className="card flex items-center justify-between gap-3">
                  <div className="min-w-0">
                    <p className="text-sm font-medium text-slate-900 dark:text-white truncate">{s.label}</p>
                    <p className="text-xs text-slate-500 truncate">{s.url}</p>
                  </div>
                  <div className="flex items-center gap-2 flex-shrink-0">
                    <button
                      onClick={() => toggleSearch(s)}
                      className={`relative w-10 h-5 rounded-full transition-colors ${
                        s.active ? "bg-brand" : "bg-slate-300 dark:bg-slate-600"
                      }`}
                    >
                      <span
                        className={`absolute top-0.5 left-0.5 w-4 h-4 rounded-full bg-white transition-transform ${
                          s.active ? "translate-x-5" : "translate-x-0"
                        }`}
                      />
                    </button>
                    <button
                      onClick={() => deleteSearch(s.search_id)}
                      className="text-slate-500 hover:text-red-400 transition-colors text-xs"
                    >
                      Delete
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </section>

        {/* Recent high-score jobs */}
        <section>
          <div className="flex items-center justify-between mb-3">
            <div><p className="eyebrow">Match queue</p><h2 className="text-xl font-black tracking-[-0.04em] text-slate-900 dark:text-white">Recent matches</h2></div>
            <a href="/jobs" className="text-sm text-brand hover:text-brand-light transition-colors">
              View all →
            </a>
          </div>

          {fetching ? (
            <p className="text-slate-600 dark:text-slate-400 text-sm">Loading…</p>
          ) : jobs.length === 0 ? (
            <div className="card text-center py-8">
              <p className="text-slate-600 dark:text-slate-400 text-sm">No jobs yet.</p>
              <p className="text-slate-500 text-xs mt-1">
                The scraper runs 4× per weekday. Check back later.
              </p>
            </div>
          ) : (
            <div className="space-y-3">
              {jobs.map((j) => (
                <JobCard
                  key={j.job_id}
                  job={j}
                  onAppliedChange={(jobId, applied) => {
                    if (applied) setJobs((current) => current.filter((job) => job.job_id !== jobId));
                  }}
                  onDismissedChange={(jobId, dismissed) => {
                    if (dismissed) setJobs((current) => current.filter((job) => job.job_id !== jobId));
                  }}
                />
              ))}
            </div>
          )}
        </section>
      </main>
    </>
  );
}
