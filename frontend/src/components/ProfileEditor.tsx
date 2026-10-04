"use client";

import { useState, KeyboardEvent } from "react";
import { api, Profile, type ResumeSkills, type Seniority, type SeniorityLevel } from "@/lib/api";

const SENIORITY_OPTIONS: { id: SeniorityLevel; label: string }[] = [
  { id: "internship", label: "Internship" },
  { id: "entry", label: "Junior / Entry level" },
  { id: "associate", label: "Associate" },
  { id: "mid", label: "Mid-level" },
  { id: "senior", label: "Senior" },
  { id: "staff", label: "Staff/Principal" },
  { id: "director", label: "Director" },
  { id: "executive", label: "Executive" },
];

interface TagListProps {
  label: string;
  description?: string;
  items: string[];
  onChange: (items: string[]) => void;
  color?: "blue" | "green" | "red" | "purple";
}

const colorMap = {
  blue: "bg-blue-900 text-blue-300 border-blue-700",
  green: "bg-emerald-900 text-emerald-300 border-emerald-700",
  red: "bg-red-900 text-red-300 border-red-700",
  purple: "bg-purple-900 text-purple-300 border-purple-700",
};

function TagList({ label, description, items, onChange, color = "blue" }: TagListProps) {
  const [input, setInput] = useState("");

  const add = () => {
    const val = input.trim();
    if (val && !items.includes(val)) onChange([...items, val]);
    setInput("");
  };

  const onKey = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Enter") { e.preventDefault(); add(); }
    if (e.key === "Backspace" && !input && items.length > 0) {
      onChange(items.slice(0, -1));
    }
  };

  return (
    <div>
      <label className="label">{label}</label>
      {description && <p className="text-xs text-slate-500 mb-2">{description}</p>}
      <div className="flex flex-wrap gap-1.5 mb-2 min-h-[32px]">
        {items.map((item) => (
          <span key={item} className={`tag border ${colorMap[color]}`}>
            {item}
            <button
              type="button"
              onClick={() => onChange(items.filter((i) => i !== item))}
              className="ml-1 hover:text-slate-900 dark:hover:text-white transition-colors"
            >
              ×
            </button>
          </span>
        ))}
      </div>
      <input
        type="text"
        className="input text-sm"
        value={input}
        onChange={(e) => setInput(e.target.value)}
        onKeyDown={onKey}
        onBlur={add}
        placeholder="Type and press Enter"
      />
    </div>
  );
}

interface Props {
  initial: Profile;
  resumeSkills: ResumeSkills | null;
  onSaved: () => void;
}

const RESUME_SKILL_GROUPS: { key: keyof ResumeSkills; label: string }[] = [
  { key: "languages", label: "Languages" },
  { key: "frameworks", label: "Frameworks" },
  { key: "tools", label: "Tools & platforms" },
  { key: "other", label: "Other" },
];

function ResumeSkillsSummary({ skills }: { skills: ResumeSkills | null }) {
  const groups = RESUME_SKILL_GROUPS
    .map((group) => ({ ...group, values: skills?.[group.key] ?? [] }))
    .filter((group) => group.values.length > 0);

  return (
    <section className="rounded-lg border border-brand/30 bg-brand/5 p-4 space-y-3">
      <div className="flex items-start justify-between gap-3 flex-wrap">
        <div>
          <h4 className="font-medium text-slate-900 dark:text-white">Skills from your CV</h4>
          <p className="text-xs text-slate-600 dark:text-slate-400 mt-1 max-w-xl">
            These are parsed when you upload your CV and used to reject a posting when an explicit required technology is not listed here. They are not the same as job preferences below.
          </p>
        </div>
        <a href="/resume" className="btn-secondary text-sm whitespace-nowrap">Edit skills in Resume</a>
      </div>
      {groups.length > 0 ? (
        <div className="space-y-2">
          {groups.map((group) => (
            <div key={group.key} className="flex items-start gap-2 flex-wrap">
              <span className="text-xs font-medium text-slate-600 dark:text-slate-400 w-28 pt-1">{group.label}</span>
              {group.values.map((skill) => (
                <span key={`${group.key}-${skill}`} className="tag border bg-white dark:bg-slate-800 text-slate-700 dark:text-slate-200 border-slate-300 dark:border-slate-600">{skill}</span>
              ))}
            </div>
          ))}
        </div>
      ) : (
        <p className="text-sm text-slate-600 dark:text-slate-400">
          No skills saved yet. Upload your CV or add them in Resume so the matcher can verify required technologies.
        </p>
      )}
    </section>
  );
}

export default function ProfileEditor({ initial, resumeSkills, onSaved }: Props) {
  const [profile, setProfile] = useState<Profile>(initial);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [saved, setSaved] = useState(false);
  const [refreshingMatches, setRefreshingMatches] = useState(false);
  const [refreshMessage, setRefreshMessage] = useState("");

  const set = (key: keyof Profile) => (val: string[] | number | Seniority | null) =>
    setProfile((p) => ({ ...p, [key]: val }));

  const toggleSeniority = (level: SeniorityLevel) => {
    setProfile((current) => {
      const selected = current.target_seniorities.includes(level)
        ? current.target_seniorities.filter((item) => item !== level)
        : [...current.target_seniorities, level];
      // Keep the old single-value field in sync so older API deployments and
      // any external clients still have a useful fallback.
      return { ...current, target_seniorities: selected, seniority: selected[0] ?? "" };
    });
  };

  const handleSave = async () => {
    setSaving(true);
    setError("");
    try {
      await api.updateProfile(profile);
      setSaved(true);
      setTimeout(() => setSaved(false), 2000);
      onSaved();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Error saving profile");
    } finally {
      setSaving(false);
    }
  };

  const handleRefreshMatches = async () => {
    setRefreshingMatches(true);
    setRefreshMessage("");
    try {
      await api.refreshJobsForCv();
      setRefreshMessage("Active jobs are being re-evaluated with your saved CV. Refresh Jobs in a few minutes.");
    } catch (err: unknown) {
      setRefreshMessage(err instanceof Error ? `Couldn’t refresh matches: ${err.message}` : "Couldn’t refresh matches.");
    } finally {
      setRefreshingMatches(false);
    }
  };

  return (
    <div className="card space-y-5">
      <h3 className="font-medium text-slate-900 dark:text-white">Candidate Profile</h3>

      <ResumeSkillsSummary skills={resumeSkills} />

      <div className="flex items-center justify-between gap-3 flex-wrap rounded-lg border border-slate-200 dark:border-slate-700 p-3">
        <p className="text-xs text-slate-600 dark:text-slate-400 max-w-lg">
          New postings use these skills automatically. To re-check active results already in Jobs after changing your CV, start an explicit refresh (up to 150 evaluations; no Telegram resend).
        </p>
        <button type="button" onClick={handleRefreshMatches} disabled={refreshingMatches} className="btn-secondary text-sm whitespace-nowrap">
          {refreshingMatches ? "Refreshing…" : "Re-check active jobs"}
        </button>
        {refreshMessage && <p className="w-full text-xs text-slate-600 dark:text-slate-400">{refreshMessage}</p>}
      </div>

      <TagList
        label="Job must-haves"
        description="Requirements you want a role to meet. Your own skills are managed from the CV section above."
        items={profile.must_have}
        onChange={set("must_have")}
        color="green"
      />
      <TagList
        label="Job nice-to-haves"
        description="Role requirements that are valuable but not essential."
        items={profile.nice_to_have}
        onChange={set("nice_to_have")}
        color="blue"
      />
      <TagList
        label="Deal Breakers"
        description="If any of these are present, the job is automatically skipped."
        items={profile.deal_breakers}
        onChange={set("deal_breakers")}
        color="red"
      />
      <TagList
        label="Prefer"
        description="Boosts score — startup, remote, equity, etc."
        items={profile.prefer}
        onChange={set("prefer")}
        color="purple"
      />

      <fieldset>
        <legend className="label">Levels you want to see</legend>
        <p className="text-xs text-slate-500 mb-2">
          Select every level you would consider. A posting whose title clearly says Senior, Staff or Lead is filtered
          before scoring when it is not selected. This avoids LinkedIn&apos;s broad “Mid-Senior” bucket mixing them.
        </p>
        <div className="grid grid-cols-2 sm:grid-cols-3 gap-2">
          {SENIORITY_OPTIONS.map((option) => (
            <label key={option.id} className="flex items-center gap-2 text-sm text-slate-700 dark:text-slate-300 cursor-pointer">
              <input
                type="checkbox"
                checked={profile.target_seniorities.includes(option.id)}
                onChange={() => toggleSeniority(option.id)}
                className="accent-brand"
              />
              {option.label}
            </label>
          ))}
        </div>
      </fieldset>

      <div>
        <label className="label" htmlFor="max-required-years">Maximum required experience</label>
        <p className="text-xs text-slate-500 mb-2">
          Don&apos;t show jobs that explicitly require more than this many years. Leave blank for no cap. This is applied before AI scoring and Telegram notifications.
        </p>
        <input
          id="max-required-years"
          type="number"
          min={1}
          max={40}
          inputMode="numeric"
          value={profile.max_required_years ?? ""}
          onChange={(event) => {
            const value = event.target.value;
            set("max_required_years")(value === "" ? null : Number(value));
          }}
          placeholder="e.g. 3"
          className="input max-w-40"
        />
      </div>

      <TagList
        label="Eligible Regions"
        description="Where you can legally/practically work remote from — e.g. Argentina, LATAM, Worldwide. If set, postings that read as remote-but-restricted to somewhere else (e.g. 'Remote — Germany only') are automatically filtered out before scoring, unless one of these words also appears in the posting."
        items={profile.eligible_regions}
        onChange={set("eligible_regions")}
        color="blue"
      />

      <div>
        <label className="label">Score Threshold</label>
        <p className="text-xs text-slate-500 mb-2">
          Only send Telegram notifications for jobs scoring above this.
        </p>
        <div className="flex items-center gap-3">
          <input
            type="range"
            min={0}
            max={100}
            value={profile.score_threshold}
            onChange={(e) => set("score_threshold")(Number(e.target.value))}
            className="flex-1 accent-brand"
          />
          <span className="text-sm font-mono w-12 text-right text-slate-900 dark:text-white">
            {profile.score_threshold}/100
          </span>
        </div>
      </div>

      {error && <p className="text-red-400 text-sm">{error}</p>}

      <button onClick={handleSave} disabled={saving} className="btn-primary">
        {saved ? "Saved!" : saving ? "Saving…" : "Save Profile"}
      </button>
    </div>
  );
}
