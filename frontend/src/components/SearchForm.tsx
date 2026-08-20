"use client";

import { useState } from "react";
import { api, type Search, type SearchSource } from "@/lib/api";

interface Props {
  onCreated: (s: Search) => void;
  onCancel: () => void;
}

const SOURCES: { id: SearchSource; label: string; placeholder: string; help: string }[] = [
  {
    id: "linkedin",
    label: "LinkedIn",
    placeholder: "https://www.linkedin.com/jobs/search/?keywords=...",
    help: "Paste the URL from a LinkedIn Jobs search with all your filters set.",
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
];

export default function SearchForm({ onCreated, onCancel }: Props) {
  const [source, setSource] = useState<SearchSource>("linkedin");
  const [url, setUrl] = useState("");
  const [slug, setSlug] = useState("");
  const [label, setLabel] = useState("");
  const [keywords, setKeywords] = useState("");
  const [locationFilter, setLocationFilter] = useState("");
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);

  const isLinkedIn = source === "linkedin";
  const sourceMeta = SOURCES.find((s) => s.id === source)!;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");

    if (isLinkedIn) {
      try { new URL(url); } catch { setError("Enter a valid LinkedIn URL"); return; }
    } else {
      if (!slug.trim()) { setError("Company slug is required"); return; }
    }
    if (!label.trim()) { setError("Label is required"); return; }

    setSaving(true);
    try {
      const search = await api.createSearch({
        url: isLinkedIn ? url.trim() : undefined,
        label: label.trim(),
        source,
        ats_slug: isLinkedIn ? "" : slug.trim().toLowerCase(),
        keywords: keywords.trim(),
        location_filter: locationFilter.trim(),
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
      <h3 className="font-medium text-white">New Search</h3>

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
                  : "bg-slate-700 text-slate-300 hover:bg-slate-600"
              }`}
            >
              {s.label}
            </button>
          ))}
        </div>
      </div>

      {/* URL or slug */}
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
      ) : (
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

      {/* Keyword filter (ATS only — LinkedIn already has this in the URL) */}
      {!isLinkedIn && (
        <>
          <div>
            <label className="label">Keywords <span className="text-slate-500">(optional)</span></label>
            <input
              type="text"
              className="input"
              value={keywords}
              onChange={(e) => setKeywords(e.target.value)}
              placeholder="senior, backend, python"
            />
            <p className="text-xs text-slate-500 mt-1">Comma-separated. Only jobs whose title or description contains any of these will be scored.</p>
          </div>
          <div>
            <label className="label">Location Filter <span className="text-slate-500">(optional)</span></label>
            <input
              type="text"
              className="input"
              value={locationFilter}
              onChange={(e) => setLocationFilter(e.target.value)}
              placeholder="Remote"
            />
          </div>
        </>
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
