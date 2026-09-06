"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/lib/auth";
import { api, Profile } from "@/lib/api";
import Nav from "@/components/Nav";
import TelegramLink from "@/components/TelegramLink";
import ProfileEditor from "@/components/ProfileEditor";

const EMPTY_PROFILE: Profile = {
  must_have: [],
  nice_to_have: [],
  deal_breakers: [],
  prefer: [],
  score_threshold: 75,
};

export default function SettingsPage() {
  const { user, loading, refresh } = useAuth();
  const router = useRouter();
  const [profile, setProfile] = useState<Profile | null>(null);
  const [fetching, setFetching] = useState(true);

  useEffect(() => {
    if (!loading && !user) router.replace("/");
  }, [user, loading, router]);

  useEffect(() => {
    if (!user) return;
    api.getProfile().then((p) => {
      // GET /profile already merges score_threshold from the users table (always
      // fresh, re-fetched per request server-side) — trust it as-is. Overriding it
      // with the auth context's `user.score_threshold` used the *cached* value from
      // login/last refresh(), which is exactly what caused the threshold to appear
      // to "reset" after a save: the save wrote the new value to the DB, but nothing
      // refreshed the cached `user` object, so this page kept clobbering the correct
      // fetched value with the stale one.
      setProfile({ ...EMPTY_PROFILE, ...p });
    }).finally(() => setFetching(false));
  }, [user]);

  if (loading || !user) return null;

  return (
    <>
      <Nav />
      <main className="max-w-2xl mx-auto px-4 py-6 space-y-6">
        <h1 className="font-semibold text-slate-900 dark:text-white text-lg">Settings</h1>

        <TelegramLink />

        {fetching ? (
          <div className="card">
            <p className="text-slate-600 dark:text-slate-400 text-sm">Loading profile…</p>
          </div>
        ) : (
          <ProfileEditor
            initial={profile ?? EMPTY_PROFILE}
            onSaved={() => { refresh(); }}
          />
        )}
      </main>
    </>
  );
}
