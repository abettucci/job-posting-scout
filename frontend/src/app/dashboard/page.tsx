"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/lib/auth";
import { api, Job, ScrapeRun, ScrapeRunSource, Search } from "@/lib/api";
import Nav from "@/components/Nav";
import JobCard from "@/components/JobCard";
import SearchForm from "@/components/SearchForm";

const SOURCE_NAMES: Record<string, string> = {
  linkedin: "LinkedIn", remoteok: "Remote OK", workingnomads: "Working Nomads",
  remotive: "Remotive", arbeitnow: "Arbeitnow", compujobs: "CompuJobs",
  onlinejobs: "OnlineJobs.ph", yc: "Y Combinator", freehire: "FreeHire",
  greenhouse: "Greenhouse", lever: "Lever", ashby: "Ashby", workable: "Workable",
  smartrecruiters: "SmartRecruiters", workday: "Workday", deel: "Deel",
};

function sourceName(source: string) {
  return SOURCE_NAMES[source] ?? source.replaceAll("_", " ");
}

function sourceTone(status: ScrapeRunSource["status"]) {
  if (status === "success") return { dot: "bg-emerald-500", label: "OK" };
  if (status === "blocked") return { dot: "bg-rose-500", label: "Blocked" };
  if (status === "paused") return { dot: "bg-amber-500", label: "Paused" };
  if (status === "failed") return { dot: "bg-rose-500", label: "Failed" };
  return { dot: "bg-slate-400", label: "Pending" };
}

function runTime(value: string) {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? "Unknown time" : new Intl.DateTimeFormat("es-AR", {
    dateStyle: "medium", timeStyle: "short",
  }).format(date);
}

export default function DashboardPage() {
  const { user, loading } = useAuth();
  const router = useRouter();

  const [searches, setSearches] = useState<Search[]>([]);
  const [jobs, setJobs] = useState<Job[]>([]);
  const [scrapeRuns, setScrapeRuns] = useState<ScrapeRun[]>([]);
  const [showForm, setShowForm] = useState(false);
  const [fetching, setFetching] = useState(true);
  const [runningScaper, setRunningScaper] = useState(false);
  const [scraperMsg, setScraperMsg] = useState<string | null>(null);
  const hiddenJobIds = useRef(new Set<string>());

  useEffect(() => {
    if (!loading && !user) router.replace("/");
  }, [user, loading, router]);

  useEffect(() => {
    if (!user) return;
    Promise.all([
      api.getSearches(),
      api.getJobs(user.score_threshold, 10, false, false),
      api.getScrapeRuns(),
    ]).then(([s, j, runs]) => {
      setSearches(s);
      setJobs(j.items.filter((job) => !job.deal_breaker && !hiddenJobIds.current.has(job.job_id)));
      setScrapeRuns(runs);
    }).finally(() => setFetching(false));
  }, [user]);

  useEffect(() => {
    if (!user) return;
    const refreshReports = () => api.getScrapeRuns().then(setScrapeRuns).catch(() => undefined);
    const interval = window.setInterval(refreshReports, 30_000);
    return () => window.clearInterval(interval);
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
      setScraperMsg("Scan started. The full source report will arrive in Telegram and appear below when it finishes.");
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

        {/* Source health and run history */}
        <section className="card overflow-hidden p-0">
          <div className="flex flex-wrap items-end justify-between gap-3 border-b px-5 py-4" style={{ borderColor: "var(--line)", background: "color-mix(in srgb, var(--surface-muted) 56%, var(--surface))" }}>
            <div>
              <p className="eyebrow">Source reports</p>
              <h2 className="mt-1 text-xl font-black tracking-[-0.04em]">Every scan, without CloudWatch.</h2>
            </div>
            <p className="max-w-xs text-xs leading-5" style={{ color: "var(--ink-muted)" }}>A compact result is also sent to your linked Telegram chat after each run.</p>
          </div>
          {scrapeRuns.length === 0 ? (
            <div className="px-5 py-7 text-sm" style={{ color: "var(--ink-muted)" }}>
              No completed scans yet. The first report will appear here after the active sources finish.
            </div>
          ) : (
            <div className="divide-y" style={{ borderColor: "var(--line)" }}>
              {scrapeRuns.map((run, index) => {
                const hasIssue = run.status !== "success";
                const autoFiltered = run.sources.reduce((total, source) => total + source.filtered, 0);
                const eligible = Math.max(0, run.new_jobs - autoFiltered);
                return (
                  <details key={run.run_id} open={index === 0} className="group">
                    <summary className="flex cursor-pointer list-none flex-wrap items-center justify-between gap-3 px-5 py-4 marker:hidden hover:bg-black/[0.02] dark:hover:bg-white/[0.03]">
                      <div className="min-w-0">
                        <div className="flex items-center gap-2">
                          <span className={`h-2 w-2 rounded-full ${hasIssue ? "bg-amber-500" : "bg-emerald-500"}`} />
                          <p className="text-sm font-bold" style={{ color: "var(--foreground)" }}>{runTime(run.finished_at)}</p>
                          <span className="rounded-full border px-2 py-0.5 text-[10px] font-extrabold uppercase tracking-[0.11em]" style={{ borderColor: "var(--line)", color: hasIssue ? "var(--accent-strong)" : "var(--ink-muted)" }}>
                            {run.status === "success" ? "Complete" : run.status}
                          </span>
                        </div>
                        <p className="mt-1 text-xs" style={{ color: "var(--ink-muted)" }}>
                          {run.new_jobs} new saved · {eligible} eligible · {autoFiltered} auto-filtered · {run.notified} match notifications
                        </p>
                      </div>
                      <span className="text-xl leading-none transition-transform group-open:rotate-45" style={{ color: "var(--accent)" }}>+</span>
                    </summary>
                    <div className="grid gap-2 border-t px-5 py-4 sm:grid-cols-2" style={{ borderColor: "var(--line)", background: "color-mix(in srgb, var(--surface-muted) 34%, transparent)" }}>
                      {run.sources.map((source) => {
                        const tone = sourceTone(source.status);
                        return (
                          <article key={source.source} className="rounded-xl border px-3 py-2.5" style={{ borderColor: "var(--line)", background: "var(--surface)" }}>
                            <div className="flex items-center justify-between gap-2">
                              <p className="flex min-w-0 items-center gap-2 text-xs font-bold"><span className={`h-1.5 w-1.5 shrink-0 rounded-full ${tone.dot}`} /> <span className="truncate">{sourceName(source.source)}</span></p>
                              <span className="text-[10px] font-extrabold uppercase tracking-wider" style={{ color: "var(--ink-muted)" }}>{tone.label}</span>
                            </div>
                            {source.status === "success" ? (
                              <p className="mt-1.5 text-xs" style={{ color: "var(--ink-muted)" }}>{source.fetched} found · {source.added} new · {source.filtered} auto-filtered · {source.seen} already seen</p>
                            ) : (
                              <p className="mt-1.5 text-xs leading-5" style={{ color: "var(--ink-muted)" }}>{source.message || "No result was available for this source."}</p>
                            )}
                          </article>
                        );
                      })}
                    </div>
                  </details>
                );
              })}
            </div>
          )}
        </section>

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
                    if (applied) {
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
        </section>
      </main>
    </>
  );
}
