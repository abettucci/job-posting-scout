"use client";

import { useState } from "react";
import { api, type Search, type SearchSource, type Seniority } from "@/lib/api";

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
    label: "Multi-board (all boards)",
    placeholder: "",
    help: "One profile-shaped search, fanned out across LinkedIn (auto-built URL) + RemoteOK + Working Nomads + Remotive + Arbeitnow + CompuJobs + OnlineJobs.ph + Y Combinator.",
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
];

const AGGREGATOR_SOURCES: SearchSource[] = ["remoteok", "workingnomads", "remotive", "arbeitnow", "compujobs", "onlinejobs", "yc"];

export default function SearchForm({ onCreated, onCancel }: Props) {
  const [source, setSource] = useState<SearchSource>("linkedin");
  const [url, setUrl] = useState("");
  const [slug, setSlug] = useState("");
  const [label, setLabel] = useState("");
  const [keywords, setKeywords] = useState("");
  const [locationFilter, setLocationFilter] = useState("");
  const [jobTitle, setJobTitle] = useState("");
  const [seniority, setSeniority] = useState<Seniority>("");
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);

  const isLinkedIn = source === "linkedin";
  const isMultiBoard = source === "multi_board";
  const isAggregator = AGGREGATOR_SOURCES.includes(source);
  const isAtsSlug = !isLinkedIn && !isMultiBoard && !isAggregator;
  const sourceMeta = SOURCES.find((s) => s.id === source)!;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");

    if (isLinkedIn) {
      try { new URL(url); } catch { setError("Enter a valid LinkedIn URL"); return; }
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
        url: isLinkedIn ? url.trim() : undefined,
        label: label.trim(),
        source,
        ats_slug: isAtsSlug ? slug.trim().toLowerCase() : "",
        keywords: keywords.trim(),
        location_filter: locationFilter.trim(),
        job_title: isMultiBoard ? jobTitle.trim() : "",
        seniority: isMultiBoard ? seniority : "",
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
      {isLinkedIn ? (
        <div>
          <label className="label">LinkedIn Search URL</label>
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

      {/* Multi-board: job title + seniority instead of a URL/slug/keywords */}
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
          <div>
            <label className="label">Seniority <span className="text-slate-500">(optional)</span></label>
            <select
              className="input"
              value={seniority}
              onChange={(e) => setSeniority(e.target.value as Seniority)}
            >
              {SENIORITY_OPTIONS.map((o) => (
                <option key={o.id} value={o.id}>{o.label}</option>
              ))}
            </select>
            <p className="text-xs text-slate-500 mt-1">
              Applied natively on LinkedIn (its Experience level filter). The other boards (RemoteOK, Working
              Nomads, Remotive, Arbeitnow, and Y Combinator) have no structured seniority field, so this only narrows LinkedIn.
            </p>
          </div>
          <p className="text-xs text-slate-500">
            Company size/type isn&apos;t filterable yet on any of these boards — none of them expose it via their public API.
          </p>
        </>
      )}

      {/* Label */}
      <div>
        <label className="label">Label</label>
        <input
          type="text"
          className="input"
          value={label}
          onChange={(e) => setLabel(e.target.value)}
          placeholder={isLinkedIn ? "e.g. Python Engineer Remote" : "e.g. Stripe Engineering"}
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
            placeholder="Remote"
          />
          {isMultiBoard && (
            <p className="text-xs text-slate-500 mt-1">
              Passed as LinkedIn&apos;s location filter; on the other boards it only narrows results whose location text matches.
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
