"use client";

import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/lib/auth";
import { api, Job, Search, type Seniority, type RegionScope, type CompanySizeHint } from "@/lib/api";
import Nav from "@/components/Nav";
import JobCard from "@/components/JobCard";

type SortBy = "posted_date" | "score";

// Kept in sync by hand with shared/seniority.py's SENIORITY_LEVELS (same
// small-constant-duplication pattern already used in SearchForm.tsx/ProfileEditor.tsx).
const SENIORITY_OPTIONS: { id: Seniority; label: string }[] = [
  { id: "", label: "Any" },
  { id: "internship", label: "Internship" },
  { id: "entry", label: "Entry level" },
  { id: "associate", label: "Associate" },
  { id: "mid", label: "Mid-level" },
  { id: "senior", label: "Senior" },
  { id: "staff", label: "Staff/Principal" },
  { id: "director", label: "Director" },
  { id: "executive", label: "Executive" },
];

// Kept in sync by hand with shared/seniority.py's extract_region_scope() return
// values (same pattern as SENIORITY_OPTIONS above). Filtering is strict equality
// against job.region_scope, same as SENIORITY_OPTIONS — selecting a specific
// region hides jobs with an unknown (null) region_scope too.
const REGION_OPTIONS: { id: RegionScope | ""; label: string }[] = [
  { id: "", label: "Any" },
  { id: "worldwide", label: "🌍 Worldwide" },
  { id: "latam", label: "🌎 LATAM" },
  { id: "restricted", label: "📍 Restricted" },
];

// Same caveat as COMPANY_SIZE in JobCard.tsx: this is a text-based estimate,
// not verified headcount — see shared/seniority.py's extract_company_size_hint.
const COMPANY_SIZE_OPTIONS: { id: CompanySizeHint | ""; label: string }[] = [
  { id: "", label: "Any" },
  { id: "startup", label: "🌱 Startup" },
  { id: "midsize", label: "🏢 Mid-size" },
  { id: "enterprise", label: "🏛️ Enterprise" },
];

function timeAgo(date: Date): string {
  const mins = Math.round((Date.now() - date.getTime()) / 60000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  const hours = Math.round(mins / 60);
  if (hours < 24) return `${hours}h ago`;
  return `${Math.round(hours / 24)}d ago`;
}

function describeSearch(s: Search): string {
  if (s.source === "linkedin") return "LinkedIn (specific URL)";
  if (s.source === "multi_board") {
    return `Multi-board: "${s.job_title}"${s.seniority ? ` (${s.seniority})` : ""}`;
  }
  const filter = s.keywords ? `keywords: "${s.keywords}"` : s.ats_slug ? `company: ${s.ats_slug}` : "";
  return `${s.source}${filter ? ` — ${filter}` : ""}${s.location_filter ? ` · ${s.location_filter}` : ""}`;
}

export default function JobsPage() {
  const { user, loading } = useAuth();
  const router = useRouter();

  const [jobs, setJobs] = useState<Job[]>([]);
  const [searches, setSearches] = useState<Search[]>([]);
  const [minScore, setMinScore] = useState(0);
  const [fetching, setFetching] = useState(true);
  const [sortBy, setSortBy] = useState<SortBy>("posted_date");
  const [titleFilter, setTitleFilter] = useState("");
  const [seniorityFilter, setSeniorityFilter] = useState<Seniority>("");
  const [yearsFilter, setYearsFilter] = useState("");
  const [regionFilter, setRegionFilter] = useState<RegionScope | "">("");
  const [companySizeFilter, setCompanySizeFilter] = useState<CompanySizeHint | "">("");
  const [expSkillFilter, setExpSkillFilter] = useState("");
  const [expYearsFilter, setExpYearsFilter] = useState("");
  const [rescoring, setRescoring] = useState(false);
  const [rescoreMsg, setRescoreMsg] = useState("");

  useEffect(() => {
    if (!loading && !user) router.replace("/");
  }, [user, loading, router]);

  useEffect(() => {
    if (!user) return;
    setFetching(true);
    // Explicitly request only the active queue. Older rows with no `applied`
    // attribute are treated as not applied by the API, so this also works for
    // every job saved before the feature existed.
    api.getJobs(minScore, 50, false, false).then((r) => setJobs(r.items)).finally(() => setFetching(false));
  }, [user, minScore]);

  useEffect(() => {
    if (!user) return;
    api.getSearches().then(setSearches);
  }, [user]);

  const unscoredCount = useMemo(() => jobs.filter((j) => j.score === 0).length, [jobs]);

  const lastScraped = useMemo(() => {
    if (jobs.length === 0) return null;
    const latest = Math.max(...jobs.map((j) => new Date(j.timestamp).getTime()));
    return new Date(latest);
  }, [jobs]);

  const activeSearches = useMemo(() => searches.filter((s) => s.active), [searches]);

  const handleRescore = async () => {
    setRescoring(true);
    setRescoreMsg("");
    try {
      await api.rescoreJobs();
      setRescoreMsg("Rescoring triggered — this can take a few minutes for a large backlog. Refresh shortly.");
    } catch (err: unknown) {
      setRescoreMsg(`Error: ${err instanceof Error ? err.message : "unknown error"}`);
    } finally {
      setRescoring(false);
    }
  };

  const visibleJobs = useMemo(() => {
    const terms = titleFilter
      .split(",")
      .map((t) => t.trim().toLowerCase())
      .filter(Boolean);
    const years = yearsFilter.trim() === "" ? null : Number(yearsFilter);
    const expSkill = expSkillFilter.trim().toLowerCase();
    const expYears = expYearsFilter.trim() === "" ? null : Number(expYearsFilter);

    const filtered = jobs.filter((j) => {
      // These jobs were rejected by a deterministic eligibility rule (for
      // example, Germany-only when the profile allows Argentina/LATAM). Keep
      // the record for auditability, but don't make the active queue noisy.
      if (j.deal_breaker) return false;
      if (terms.length > 0 && !terms.some((t) => j.title.toLowerCase().includes(t))) return false;
      if (seniorityFilter && j.seniority_level !== seniorityFilter) return false;
      if (years !== null && j.min_years_experience !== null && j.min_years_experience > years) return false;
      if (regionFilter && j.region_scope !== regionFilter) return false;
      if (companySizeFilter && j.company_size_hint !== companySizeFilter) return false;
      // Skill/task years filter: only excludes a job when it actually mentions
      // the skill AND asks for more years than declared — a job that never
      // mentions the skill at all is left in (no signal ≠ disqualified).
      if (expSkill && expYears !== null) {
        const overAsk = j.experience_mentions.some(
          (m) => m.context.toLowerCase().includes(expSkill) && m.years > expYears
        );
        if (overAsk) return false;
      }
      return true;
    });

    return [...filtered].sort((a, b) => {
      if (sortBy === "score") return b.score - a.score;
      // posted_date: nulls (LinkedIn jobs, unparseable dates) always sink to the bottom
      if (a.posted_date === null && b.posted_date === null) return 0;
      if (a.posted_date === null) return 1;
      if (b.posted_date === null) return -1;
      return new Date(b.posted_date).getTime() - new Date(a.posted_date).getTime();
    });
  }, [jobs, titleFilter, seniorityFilter, yearsFilter, regionFilter, companySizeFilter, expSkillFilter, expYearsFilter, sortBy]);

  if (loading || !user) return null;

  return (
    <>
      <Nav />
      <main id="main-content" className="page-shell">
        <div className="border-b pb-6" style={{ borderColor: "var(--line)" }}>
          <div className="flex items-center justify-between flex-wrap gap-3">
            <div><p className="eyebrow">Match queue</p><h1 className="page-title mt-1">All jobs</h1></div>
            <div className="flex items-center gap-2 text-sm">
              <label className="text-slate-600 dark:text-slate-400">Min score:</label>
              <div className="flex gap-1">
                {[0, 50, 70, 80, 90].map((v) => (
                  <button
                    key={v}
                    onClick={() => setMinScore(v)}
                    aria-pressed={minScore === v}
                    className="filter-chip"
                  >
                    {v === 0 ? "All" : `${v}+`}
                  </button>
                ))}
              </div>
            </div>
          </div>
          {lastScraped && (
            <p className="text-xs text-slate-500 mt-1">
              Last scraped job: {timeAgo(lastScraped)} ({lastScraped.toLocaleString()}) — this is an
              approximation from your most recent saved job, not a live run status.
            </p>
          )}
          {activeSearches.length > 0 && (
            <details className="text-xs text-slate-500 mt-1">
              <summary className="cursor-pointer hover:text-slate-700 dark:hover:text-slate-300">
                {activeSearches.length} active search{activeSearches.length === 1 ? "" : "es"} configured
              </summary>
              <ul className="mt-1 space-y-0.5 pl-4 list-disc">
                {activeSearches.map((s) => (
                  <li key={s.search_id}>{s.label} — {describeSearch(s)}</li>
                ))}
              </ul>
            </details>
          )}
        </div>

        <section className="card space-y-4">
        <div className="flex items-center justify-between flex-wrap gap-3">
          <div className="flex items-center gap-2 flex-wrap">
            <input
              type="text"
              value={titleFilter}
              onChange={(e) => setTitleFilter(e.target.value)}
              placeholder="Filter by title (e.g. senior, QA, golang — comma = OR)…"
              className="input max-w-sm text-sm"
            />
            <input
              type="number"
              min={0}
              value={yearsFilter}
              onChange={(e) => setYearsFilter(e.target.value)}
              placeholder="Your years of experience"
              className="input w-44 text-sm"
            />
            <input
              type="text"
              value={expSkillFilter}
              onChange={(e) => setExpSkillFilter(e.target.value)}
              placeholder="Skill/task (e.g. Python)"
              className="input w-40 text-sm"
            />
            <input
              type="number"
              min={0}
              value={expYearsFilter}
              onChange={(e) => setExpYearsFilter(e.target.value)}
              placeholder="Your years in it"
              className="input w-36 text-sm"
              title="Hide jobs that ask for more years in that skill/task than you enter here"
            />
          </div>
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
                    aria-pressed={sortBy === o.id}
                    className="filter-chip"
                >
                  {o.label}
                </button>
              ))}
            </div>
          </div>
        </div>

        <div className="flex items-center gap-2 text-sm flex-wrap">
          <label className="text-slate-600 dark:text-slate-400">Seniority:</label>
          <div className="flex gap-1 flex-wrap">
            {SENIORITY_OPTIONS.map((o) => (
              <button
                key={o.id}
                onClick={() => setSeniorityFilter(o.id)}
                aria-pressed={seniorityFilter === o.id}
                className="filter-chip"
              >
                {o.label}
              </button>
            ))}
          </div>
        </div>

        <div className="flex items-center gap-2 text-sm flex-wrap">
          <label className="text-slate-600 dark:text-slate-400">Region:</label>
          <div className="flex gap-1 flex-wrap">
            {REGION_OPTIONS.map((o) => (
              <button
                key={o.id}
                onClick={() => setRegionFilter(o.id)}
                aria-pressed={regionFilter === o.id}
                className="filter-chip"
              >
                {o.label}
              </button>
            ))}
          </div>
        </div>

        <div className="flex items-center gap-2 text-sm flex-wrap">
          <label className="text-slate-600 dark:text-slate-400">Company size:</label>
          <div className="flex gap-1 flex-wrap">
            {COMPANY_SIZE_OPTIONS.map((o) => (
              <button
                key={o.id}
                onClick={() => setCompanySizeFilter(o.id)}
                aria-pressed={companySizeFilter === o.id}
                className="filter-chip"
              >
                {o.label}
              </button>
            ))}
          </div>
          <span className="text-xs text-slate-500">(estimated from posting text, not verified)</span>
        </div>

        {!fetching && unscoredCount > 0 && (
          <div className="card flex items-center justify-between flex-wrap gap-3 border-yellow-700/50">
            <p className="text-sm text-slate-600 dark:text-slate-400">
              {unscoredCount} job{unscoredCount === 1 ? "" : "s"} {unscoredCount === 1 ? "was" : "were"} saved with
              score 0 (usually because your profile was empty when they were first scraped) — the min-score
              filter and score sort won&apos;t do anything useful for these until they&apos;re rescored.
            </p>
            <button onClick={handleRescore} disabled={rescoring} className="btn-primary text-sm whitespace-nowrap">
              {rescoring ? "Triggering…" : "Rescore unscored jobs"}
            </button>
          </div>
        )}
        {rescoreMsg && (
          <p className={`text-xs ${rescoreMsg.startsWith("Error") ? "text-red-400" : "text-green-400"}`}>
            {rescoreMsg}
          </p>
        )}

        {fetching ? (
          <p className="text-slate-600 dark:text-slate-400 text-sm">Loading…</p>
        ) : visibleJobs.length === 0 ? (
          <div className="card text-center py-12">
            <p className="text-slate-600 dark:text-slate-400">No jobs found for this filter.</p>
          </div>
        ) : (
          <div className="space-y-3">
            {visibleJobs.map((j) => (
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
