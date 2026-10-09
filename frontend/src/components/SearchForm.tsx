"use client";

import { useState } from "react";
import { api, type Search, type SearchSource, type Seniority, type SeniorityLevel, type CompanySizeHint } from "@/lib/api";

interface Props {
  onCreated: (s: Search) => void;
  onCancel: () => void;
}

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

const SOURCES: { id: SearchSource; label: string; placeholder: string; help: string }[] = [
  {
    id: "linkedin",
    label: "LinkedIn (specific URL)",
    placeholder: "https://www.linkedin.com/jobs/search/?keywords=...",
    help: "Paste the URL from a LinkedIn Jobs search with all your filters set. Use this when you want to control LinkedIn's own filters by hand (e.g. f_TPR, boolean keywords).",
  },
  {
    id: "multi_board",
    label: "Multi-board (global sources)",
    placeholder: "",
    help: "One profile-shaped search, fanned out across LinkedIn, global remote boards, Wellfound, SimplyHired, FreeHire and Y Combinator.",
  },
  {
    id: "greenhouse",
    label: "Greenhouse",
    placeholder: "stripe",
    help: "Company slug from boards.greenhouse.io/{slug}. Example: stripe, notion, anthropic.",
  },
  {
    id: "lever",
    label: "Lever",
    placeholder: "openai",
    help: "Company slug from jobs.lever.co/{slug}. Example: openai, figma, vercel.",
  },
  {
    id: "ashby",
    label: "Ashby",
    placeholder: "linear",
    help: "Company slug from jobs.ashbyhq.com/{slug}. Example: linear, brex, ramp.",
  },
  {
    id: "workable",
    label: "Workable",
    placeholder: "acme",
    help: "Company slug from apply.workable.com/{slug}.",
  },
  {
    id: "smartrecruiters",
    label: "SmartRecruiters",
    placeholder: "bosch",
    help: "Company slug from careers.smartrecruiters.com/{slug}.",
  },
  {
    id: "workday",
    label: "Workday (company careers URL)",
    placeholder: "https://company.wd5.myworkdayjobs.com/en-US/External",
    help: "Paste the public Workday careers URL for one company. Workday uses a tenant and career-site path, not a reusable slug.",
  },
  {
    id: "deel",
    label: "Deel (company careers URL)",
    placeholder: "https://jobs.deel.com/acme",
    help: "Paste a public Deel-hosted company board. This source reads only public listing and overview pages, never applications or the API.",
  },
  {
    id: "remoteok",
    label: "RemoteOK",
    placeholder: "",
    help: "Global remote-jobs feed. Requires keywords below — every posting on the feed matches otherwise.",
  },
  {
    id: "workingnomads",
    label: "Working Nomads",
    placeholder: "",
    help: "Global remote-jobs feed. Requires keywords below — every posting on the feed matches otherwise.",
  },
  {
    id: "remotive",
    label: "Remotive",
    placeholder: "",
    help: "Global remote-jobs feed. Requires keywords below — every posting on the feed matches otherwise.",
  },
  {
    id: "arbeitnow",
    label: "Arbeitnow",
    placeholder: "",
    help: "Global jobs feed (EU-focused, remote flag per posting). Requires keywords below.",
  },
  {
    id: "compujobs",
    label: "CompuJobs",
    placeholder: "",
    help: "South African jobs board. Requires keywords below. No public API — HTML scraping, so this source may be less reliable than the feed-based ones above.",
  },
  {
    id: "onlinejobs",
    label: "OnlineJobs.ph",
    placeholder: "",
    help: "Philippines remote/VA jobs board. Requires keywords below. Company name and location aren't available from this source (every posting shows as company-less, \"Remote\"). No public API — HTML scraping.",
  },
  {
    id: "yc",
    label: "Y Combinator",
    placeholder: "",
    help: "Public YC Startup Jobs listings: automatically combines Buenos Aires roles with worldwide-remote roles. Requires keywords below.",
  },
  {
    id: "freehire",
    label: "FreeHire",
    placeholder: "",
    help: "Structured global tech jobs from a public feed. Requires keywords below and favors remote roles.",
  },
  {
    id: "wellfound",
    label: "Wellfound",
    placeholder: "",
    help: "Public startup-job pages with full descriptions read only after a keyword and location match. Included in Multi-board.",
  },
  {
    id: "simplyhired",
    label: "SimplyHired",
    placeholder: "",
    help: "Public, server-rendered remote search results. US-heavy and some roles are region-restricted. Included in Multi-board.",
  },
  {
    id: "justjoin",
    label: "JustJoin.IT",
    placeholder: "",
    help: "Public technology listings, mainly Poland/Europe. Remote eligibility can be country-specific, so it is not included in Multi-board.",
  },
  {
    id: "dixcover",
    label: "Dixcover Hub",
    placeholder: "",
    help: "Public remote-opportunity feed, largely Africa/Nigeria. Use a specific location filter when appropriate; not included in Multi-board.",
  },
];

const AGGREGATOR_SOURCES: SearchSource[] = ["remoteok", "workingnomads", "remotive", "arbeitnow", "compujobs", "onlinejobs", "yc", "freehire", "wellfound", "simplyhired", "justjoin", "dixcover"];

export default function SearchForm({ onCreated, onCancel }: Props) {
  const [source, setSource] = useState<SearchSource>("linkedin");
  const [url, setUrl] = useState("");
  const [slug, setSlug] = useState("");
  const [label, setLabel] = useState("");
  const [keywords, setKeywords] = useState("");
  const [locationFilter, setLocationFilter] = useState("");
  const [jobTitle, setJobTitle] = useState("");
  const [seniorities, setSeniorities] = useState<SeniorityLevel[]>([]);
  const [maxYearsExperience, setMaxYearsExperience] = useState("");
  const [experienceSkill, setExperienceSkill] = useState("");
  const [maxSkillYears, setMaxSkillYears] = useState("");
  const [companySizeHints, setCompanySizeHints] = useState<CompanySizeHint[]>([]);
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);

  const isLinkedIn = source === "linkedin";
  const isMultiBoard = source === "multi_board";
  const isWorkday = source === "workday";
  const isDeel = source === "deel";
  const isAggregator = AGGREGATOR_SOURCES.includes(source);
  const isAtsSlug = !isLinkedIn && !isMultiBoard && !isAggregator && !isWorkday && !isDeel;
  const sourceMeta = SOURCES.find((s) => s.id === source)!;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");

    if (isLinkedIn || isWorkday || isDeel) {
      try { new URL(url); } catch { setError(isWorkday ? "Enter a valid Workday careers URL" : isDeel ? "Enter a valid Deel company board URL" : "Enter a valid LinkedIn URL"); return; }
      if (isWorkday && !new URL(url).hostname.endsWith(".myworkdayjobs.com")) {
        setError("Enter a public Workday careers URL ending in myworkdayjobs.com"); return;
      }
      if (isDeel) {
        const parsed = new URL(url);
        const parts = parsed.pathname.split("/").filter(Boolean);
        const companyParts = parts[0] === "job-boards" ? parts.slice(1) : parts;
        if (parsed.protocol !== "https:" || parsed.hostname !== "jobs.deel.com" || companyParts.length !== 1 || !/^[a-z0-9][a-z0-9-]*$/i.test(companyParts[0])) {
          setError("Enter a public Deel company board URL like https://jobs.deel.com/acme"); return;
        }
      }
    } else if (isMultiBoard) {
      if (!jobTitle.trim()) { setError("Job title is required"); return; }
    } else if (isAtsSlug) {
      if (!slug.trim()) { setError("Company slug is required"); return; }
    } else if (isAggregator) {
      if (!keywords.trim()) { setError("Keywords are required for global feeds like this one"); return; }
    }
    if (!label.trim()) { setError("Label is required"); return; }

    setSaving(true);
    try {
      const search = await api.createSearch({
        url: isLinkedIn || isWorkday || isDeel ? url.trim() : undefined,
        label: label.trim(),
        source,
        ats_slug: isAtsSlug ? slug.trim().toLowerCase() : "",
        keywords: keywords.trim(),
        location_filter: locationFilter.trim(),
        job_title: isMultiBoard ? jobTitle.trim() : "",
        seniority: seniorities[0] ?? "",
        seniorities,
        max_years_experience: maxYearsExperience ? Number(maxYearsExperience) : null,
        experience_skill: experienceSkill.trim(),
        max_skill_years: maxSkillYears ? Number(maxSkillYears) : null,
        company_size_hints: companySizeHints,
      });
      onCreated(search);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Error saving search");
    } finally {
      setSaving(false);
    }
  };

  return (
    <form onSubmit={handleSubmit} className="card space-y-4">
      <h3 className="font-medium text-slate-900 dark:text-white">New Search</h3>

      {/* Source selector */}
      <div>
        <label className="label">Source</label>
        <div className="flex flex-wrap gap-1.5">
          {SOURCES.map((s) => (
            <button
              key={s.id}
              type="button"
              onClick={() => { setSource(s.id); setUrl(""); setSlug(""); }}
              className={`px-3 py-1 rounded-full text-xs font-medium transition-colors ${
                source === s.id
                  ? "bg-brand text-white"
                  : "bg-slate-200 dark:bg-slate-700 text-slate-700 dark:text-slate-300 hover:bg-slate-300 dark:hover:bg-slate-600"
              }`}
            >
              {s.label}
            </button>
          ))}
        </div>
      </div>

      {/* URL, slug, or (for aggregators/multi-board) nothing — just the help text */}
      {isLinkedIn || isWorkday || isDeel ? (
        <div>
          <label className="label">{isWorkday ? "Workday Careers URL" : isDeel ? "Deel Company Board URL" : "LinkedIn Search URL"}</label>
          <input
            type="url"
            className="input"
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            placeholder={sourceMeta.placeholder}
            required
          />
          <p className="text-xs text-slate-500 mt-1">{sourceMeta.help}</p>
        </div>
      ) : isAtsSlug ? (
        <div>
          <label className="label">Company Slug</label>
          <input
            type="text"
            className="input"
            value={slug}
            onChange={(e) => setSlug(e.target.value)}
            placeholder={sourceMeta.placeholder}
            required
          />
          <p className="text-xs text-slate-500 mt-1">{sourceMeta.help}</p>
        </div>
      ) : (
        <p className="text-xs text-slate-500">{sourceMeta.help}</p>
      )}

      {/* Multi-board: job title instead of a URL/slug/keywords */}
      {isMultiBoard && (
        <>
          <div>
            <label className="label">Job Title</label>
            <input
              type="text"
              className="input"
              value={jobTitle}
              onChange={(e) => setJobTitle(e.target.value)}
              placeholder="Backend Engineer"
              required
            />
          </div>
        </>
      )}

      <details className="rounded-lg border border-slate-200 dark:border-slate-700 p-3">
        <summary className="cursor-pointer text-sm font-medium text-slate-800 dark:text-slate-200">More result filters</summary>
        <div className="grid sm:grid-cols-2 gap-4 mt-4">
          <div>
            <label className="label">Seniority <span className="text-slate-500">(select any)</span></label>
            <div className="grid grid-cols-2 gap-1.5 text-sm text-slate-700 dark:text-slate-300">
              {SENIORITY_OPTIONS.filter((option) => option.id).map((option) => {
                const level = option.id as SeniorityLevel;
                return <label key={level} className="flex items-center gap-1.5 cursor-pointer"><input type="checkbox" checked={seniorities.includes(level)} onChange={() => setSeniorities((current) => current.includes(level) ? current.filter((item) => item !== level) : [...current, level])} className="accent-brand" />{option.label}</label>;
              })}
            </div>
          </div>
          <div>
            <label className="label">Maximum required experience</label>
            <input type="number" min={1} max={40} inputMode="numeric" className="input" value={maxYearsExperience} onChange={(e) => setMaxYearsExperience(e.target.value)} placeholder="e.g. 3 years" />
          </div>
          <div>
            <label className="label">Skill or task experience</label>
            <input type="text" className="input" value={experienceSkill} onChange={(e) => setExperienceSkill(e.target.value)} placeholder="e.g. Python, AWS, data modeling" />
          </div>
          <div>
            <label className="label">Maximum years for that skill/task</label>
            <input type="number" min={1} max={40} inputMode="numeric" className="input" value={maxSkillYears} onChange={(e) => setMaxSkillYears(e.target.value)} placeholder="e.g. 2 years" disabled={!experienceSkill.trim()} />
          </div>
        </div>
        <fieldset className="mt-4">
          <legend className="label">Company size <span className="text-slate-500">(when detected)</span></legend>
          <div className="flex flex-wrap gap-x-4 gap-y-2 text-sm text-slate-700 dark:text-slate-300">
            {([
              ["startup", "Startup"],
              ["midsize", "Mid-size"],
              ["enterprise", "Enterprise"],
            ] as [CompanySizeHint, string][]).map(([size, label]) => (
              <label key={size} className="flex items-center gap-1.5 cursor-pointer">
                <input type="checkbox" checked={companySizeHints.includes(size)} onChange={() => setCompanySizeHints((current) => current.includes(size) ? current.filter((item) => item !== size) : [...current, size])} className="accent-brand" />
                {label}
              </label>
            ))}
          </div>
          <p className="text-xs text-slate-500 mt-2">Company size is an estimate from the posting or LinkedIn. Jobs with no reliable size signal remain eligible.</p>
        </fieldset>
        <p className="text-xs text-slate-500 mt-3">These filters run after a job is fetched and before AI scoring or Telegram notification. Seniority is applied natively on LinkedIn when available and then checked again from the title for every source.</p>
      </details>

      {/* Label */}
      <div>
        <label className="label">Label</label>
        <input
          type="text"
          className="input"
          value={label}
          onChange={(e) => setLabel(e.target.value)}
          placeholder={isLinkedIn ? "e.g. Python Engineer Remote" : isWorkday ? "e.g. Acme Workday Engineering" : isDeel ? "e.g. Acme Deel Engineering" : "e.g. Stripe Engineering"}
          required
        />
      </div>

      {/* Keyword filter (ATS/aggregator only — LinkedIn has it in the URL, multi-board uses Job Title) */}
      {!isLinkedIn && !isMultiBoard && (
        <div>
          <label className="label">
            Keywords {isAggregator ? <span className="text-red-400">(required)</span> : <span className="text-slate-500">(optional)</span>}
          </label>
          <input
            type="text"
            className="input"
            value={keywords}
            onChange={(e) => setKeywords(e.target.value)}
            placeholder="senior, backend, python"
            required={isAggregator}
          />
          <p className="text-xs text-slate-500 mt-1">
            Comma-separated. Only jobs whose title or description contains any of these will be scored.
            {isAggregator && " This is a global feed across many companies — without a keyword filter every posting would be scored."}
          </p>
        </div>
      )}

      {/* Location filter (ATS/aggregator/multi-board — LinkedIn has it in the URL) */}
      {!isLinkedIn && (
        <div>
          <label className="label">Location Filter <span className="text-slate-500">(optional)</span></label>
          <input
            type="text"
            className="input"
            value={locationFilter}
            onChange={(e) => setLocationFilter(e.target.value)}
            placeholder="Argentina, Remote, Worldwide"
          />
          {isMultiBoard && (
            <p className="text-xs text-slate-500 mt-1">
              Separate alternatives with commas (OR). LinkedIn runs one search per location; other boards match any listed location.
            </p>
          )}
        </div>
      )}

      {error && <p className="text-red-400 text-sm">{error}</p>}

      <div className="flex gap-2 pt-1">
        <button type="submit" disabled={saving} className="btn-primary">
          {saving ? "Saving…" : "Save"}
        </button>
        <button type="button" onClick={onCancel} className="btn-ghost">
          Cancel
        </button>
      </div>
    </form>
  );
}
