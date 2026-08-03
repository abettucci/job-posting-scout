"use client";

import { useState } from "react";
import { api, Search } from "@/lib/api";

interface Props {
  onCreated: (s: Search) => void;
  onCancel: () => void;
}

export default function SearchForm({ onCreated, onCancel }: Props) {
  const [url, setUrl] = useState("");
  const [label, setLabel] = useState("");
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    try {
      new URL(url);
    } catch {
      setError("Enter a valid URL");
      return;
    }
    if (!label.trim()) {
      setError("Label is required");
      return;
    }
    setSaving(true);
    try {
      const search = await api.createSearch(url.trim(), label.trim());
      onCreated(search);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Error saving search");
    } finally {
      setSaving(false);
    }
  };

  return (
    <form onSubmit={handleSubmit} className="card space-y-3">
      <h3 className="font-medium text-white">New Search</h3>
      <div>
        <label className="label">LinkedIn Search URL</label>
        <input
          type="url"
          className="input"
          value={url}
          onChange={(e) => setUrl(e.target.value)}
          placeholder="https://www.linkedin.com/jobs/search/?keywords=..."
          required
        />
        <p className="text-xs text-slate-500 mt-1">
          Paste the URL from a LinkedIn Jobs search with all your filters set.
        </p>
      </div>
      <div>
        <label className="label">Label</label>
        <input
          type="text"
          className="input"
          value={label}
          onChange={(e) => setLabel(e.target.value)}
          placeholder="e.g. Python Engineer Remote US"
          required
        />
      </div>
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
