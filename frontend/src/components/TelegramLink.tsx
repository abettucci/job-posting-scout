"use client";

import { useState, useEffect } from "react";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";

export default function TelegramLink() {
  const { user, refresh } = useAuth();
  const [code, setCode] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  // Poll /auth/me every 5s while code is shown to detect when bot links the account
  useEffect(() => {
    if (!code) return;
    const interval = setInterval(async () => {
      await refresh();
    }, 5000);
    return () => clearInterval(interval);
  }, [code, refresh]);

  // Clear code once linked
  useEffect(() => {
    if (user?.telegram_chat_id && code) {
      setCode(null);
    }
  }, [user?.telegram_chat_id, code]);

  const startLink = async () => {
    setError("");
    setLoading(true);
    try {
      const res = await api.startTelegramLink();
      setCode(res.code);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Error generating code");
    } finally {
      setLoading(false);
    }
  };

  if (user?.telegram_chat_id) {
    return (
      <div className="card">
        <div className="flex items-center gap-2">
          <span className="w-2 h-2 rounded-full bg-emerald-400" />
          <span className="text-sm font-medium text-white">Telegram linked</span>
          <span className="text-xs text-slate-400">chat_id: {user.telegram_chat_id}</span>
        </div>
      </div>
    );
  }

  return (
    <div className="card space-y-3">
      <h3 className="font-medium text-white">Link Telegram</h3>
      <p className="text-sm text-slate-400">
        Connect your Telegram account to receive job notifications.
      </p>

      {!code ? (
        <>
          <button onClick={startLink} disabled={loading} className="btn-primary">
            {loading ? "Generating…" : "Generate Link Code"}
          </button>
          {error && <p className="text-red-400 text-sm">{error}</p>}
        </>
      ) : (
        <div className="space-y-3">
          <div className="bg-slate-900 rounded-lg p-4 text-center">
            <p className="text-xs text-slate-400 mb-1">Your code (expires in 10 min)</p>
            <p className="text-4xl font-mono font-bold tracking-widest text-brand">{code}</p>
          </div>
          <ol className="text-sm text-slate-300 space-y-1 list-decimal list-inside">
            <li>
              Open Telegram and find your bot{" "}
              <span className="text-brand">@JobScoutBot</span>
            </li>
            <li>
              Send the command:{" "}
              <code className="bg-slate-700 px-1.5 py-0.5 rounded text-xs font-mono">
                /start {code}
              </code>
            </li>
            <li>Wait — this page will update automatically once linked</li>
          </ol>
          <div className="flex items-center gap-2 text-xs text-slate-500">
            <div className="w-2 h-2 rounded-full bg-slate-500 animate-pulse" />
            Waiting for Telegram confirmation…
          </div>
        </div>
      )}
    </div>
  );
}
