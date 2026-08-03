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
  const { user, loading } = useAuth();
  const router = useRouter();
  const [profile, setProfile] = useState<Profile | null>(null);
  const [fetching, setFetching] = useState(true);

  useEffect(() => {
    if (!loading && !user) router.replace("/");
  }, [user, loading, router]);

  useEffect(() => {
    if (!user) return;
    api.getProfile().then((p) => {
      setProfile({ ...EMPTY_PROFILE, ...p, score_threshold: user.score_threshold });
    }).finally(() => setFetching(false));
  }, [user]);

  if (loading || !user) return null;

  return (
    <>
      <Nav />
      <main className="max-w-2xl mx-auto px-4 py-6 space-y-6">
        <h1 className="font-semibold text-white text-lg">Settings</h1>

        <TelegramLink />

        {fetching ? (
          <div className="card">
            <p className="text-slate-400 text-sm">Loading profile…</p>
          </div>
        ) : (
          <ProfileEditor
            initial={profile ?? EMPTY_PROFILE}
            onSaved={() => {}}
          />
        )}
      </main>
    </>
  );
}
