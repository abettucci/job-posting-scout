"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";

export default function LinkedInSession() {
  const [blockedUntil, setBlockedUntil] = useState<string | null>(null);
  const [needsReconnect, setNeedsReconnect] = useState(false);
  const [liAt, setLiAt] = useState("");
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState("");

  useEffect(() => {
    api.getLinkedInSessionStatus()
      .then((status) => {
        setBlockedUntil(status.blocked_until);
        setNeedsReconnect(status.needs_reconnect);
      })
      .catch(() => {
        // The rest of Settings remains usable if this optional status fails.
      });
  }, []);

  const save = async () => {
    setMessage("");
    setSaving(true);
    try {
      await api.updateLinkedInSession(liAt);
      setLiAt("");
      setNeedsReconnect(false);
      setBlockedUntil(null);
      setMessage("LinkedIn session updated. The next scan will try the source again.");
    } catch (error: unknown) {
      setMessage(error instanceof Error ? error.message : "Could not update the LinkedIn session.");
    } finally {
      setSaving(false);
    }
  };

  return (
    <section className="card space-y-3">
      <div>
        <h2 className="font-medium text-slate-900 dark:text-white">LinkedIn source</h2>
        <p className="text-sm text-slate-600 dark:text-slate-400 mt-1">
          {needsReconnect
            ? "The saved LinkedIn session is unavailable from the scraper. Refresh it to re-enable this source."
            : "Use a current LinkedIn session only if you want this source included in your scans."}
        </p>
        {blockedUntil && (
          <p className="text-xs text-amber-700 dark:text-amber-300 mt-2">
            Automatic retry is paused until {new Date(blockedUntil).toLocaleString()}.
          </p>
        )}
      </div>
      <details className="text-sm text-slate-600 dark:text-slate-400">
        <summary className="cursor-pointer">How to refresh it</summary>
        <ol className="list-decimal ml-5 mt-2 space-y-1">
          <li>Sign in to LinkedIn normally in your own browser.</li>
          <li>Open browser developer tools, find the <code>li_at</code> cookie for <code>.linkedin.com</code>, and copy its value.</li>
          <li>Paste it below. It is sent only to Job Scout over HTTPS, stored in Secrets Manager, and never shown again.</li>
        </ol>
      </details>
      <label className="block text-sm font-medium text-slate-700 dark:text-slate-200">
        New <code>li_at</code> session
        <input
          value={liAt}
          onChange={(event) => setLiAt(event.target.value)}
          type="password"
          autoComplete="off"
          spellCheck={false}
          className="input mt-1"
          placeholder="Paste only the cookie value"
        />
      </label>
      <button type="button" onClick={save} disabled={saving || liAt.trim().length < 16} className="btn-primary disabled:opacity-50">
        {saving ? "Updating…" : "Update LinkedIn session"}
      </button>
      {message && <p role="status" className="text-sm text-slate-600 dark:text-slate-400">{message}</p>}
    </section>
  );
}
