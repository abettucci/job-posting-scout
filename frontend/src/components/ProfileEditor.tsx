"use client";

import { useState, KeyboardEvent } from "react";
import { api, Profile, type Seniority, type SeniorityLevel } from "@/lib/api";

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
  onSaved: () => void;
}

export default function ProfileEditor({ initial, onSaved }: Props) {
  const [profile, setProfile] = useState<Profile>(initial);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [saved, setSaved] = useState(false);

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

  return (
    <div className="card space-y-5">
      <h3 className="font-medium text-slate-900 dark:text-white">Candidate Profile</h3>

      <TagList
        label="Must Have"
        description="Required skills or conditions — missing any of these lowers the score significantly."
        items={profile.must_have}
        onChange={set("must_have")}
        color="green"
      />
      <TagList
        label="Nice to Have"
        description="Preferred but not required."
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
