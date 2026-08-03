"use client";

import { useEffect, useState, Suspense } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { useAuth } from "@/lib/auth";
import { api, Interview, InterviewStage } from "@/lib/api";
import Nav from "@/components/Nav";
import KanbanBoard from "@/components/KanbanBoard";

interface NewForm {
  company: string;
  role: string;
  scheduled_at: string;
  location: string;
  notes: string;
  job_id: string | null;
  job_score: number | null;
  job_url: string | null;
}

const EMPTY_FORM: NewForm = {
  company: "", role: "", scheduled_at: "", location: "", notes: "",
  job_id: null, job_score: null, job_url: null,
};

function InterviewsContent() {
  const { user, loading } = useAuth();
  const router = useRouter();
  const params = useSearchParams();

  const [interviews, setInterviews] = useState<Interview[]>([]);
  const [fetching, setFetching] = useState(true);
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState<NewForm>(EMPTY_FORM);
  const [saving, setSaving] = useState(false);
  const [formError, setFormError] = useState("");

  useEffect(() => {
    if (!loading && !user) router.replace("/");
  }, [user, loading, router]);

  // Pre-fill from ?job_id=&company=&role=&score=&url= (deep link from JobCard)
  useEffect(() => {
    const company = params.get("company");
    const role = params.get("role");
    if (company || role) {
      setForm((f) => ({
        ...f,
        company: decodeURIComponent(company ?? ""),
        role: decodeURIComponent(role ?? ""),
        job_id: params.get("job_id"),
        job_score: params.get("score") ? Number(params.get("score")) : null,
        job_url: params.get("url") ? decodeURIComponent(params.get("url")!) : null,
      }));
      setShowForm(true);
    }
  }, [params]);

  useEffect(() => {
    if (!user) return;
    api.getInterviews().then(setInterviews).finally(() => setFetching(false));
  }, [user]);

  const handleStageChange = async (id: string, stage: InterviewStage) => {
    setInterviews((prev) => prev.map((i) => (i.interview_id === id ? { ...i, stage } : i)));
    await api.patchInterview(id, { stage });
  };

  const handleDelete = async (id: string) => {
    setInterviews((prev) => prev.filter((i) => i.interview_id !== id));
    await api.deleteInterview(id);
  };

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!form.company.trim() || !form.role.trim()) {
      setFormError("Company and role are required");
      return;
    }
    setSaving(true);
    setFormError("");
    try {
      const created = await api.createInterview({
        company: form.company.trim(),
        role: form.role.trim(),
        stage: "applied",
        scheduled_at: form.scheduled_at || null,
        location: form.location || null,
        notes: form.notes,
        job_id: form.job_id,
        job_score: form.job_score,
        job_url: form.job_url,
      });
      setInterviews((prev) => [created, ...prev]);
      setForm(EMPTY_FORM);
      setShowForm(false);
    } catch (err: unknown) {
      setFormError(err instanceof Error ? err.message : "Error creating interview");
    } finally {
      setSaving(false);
    }
  };

  if (loading || !user) return null;

  const activeCount = interviews.filter((i) => !["accepted", "rejected", "withdrawn"].includes(i.stage)).length;

  return (
    <>
      <Nav />
      <main className="max-w-6xl mx-auto px-4 py-6 space-y-6">
        <div className="flex items-center justify-between flex-wrap gap-3">
          <div>
            <h1 className="font-semibold text-white text-lg">Interview Tracker</h1>
            <p className="text-xs text-slate-500 mt-0.5">{activeCount} active · {interviews.length} total</p>
          </div>
          {!showForm && (
            <button onClick={() => setShowForm(true)} className="btn-primary text-sm">
              + New Interview
            </button>
          )}
        </div>

        {/* New interview form */}
        {showForm && (
          <form onSubmit={handleCreate} className="card space-y-3 max-w-xl">
            <h3 className="font-medium text-white">New Interview</h3>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="label">Company *</label>
                <input
                  type="text" className="input" required
                  value={form.company}
                  onChange={(e) => setForm((f) => ({ ...f, company: e.target.value }))}
                  placeholder="Anthropic"
                />
              </div>
              <div>
                <label className="label">Role *</label>
                <input
                  type="text" className="input" required
                  value={form.role}
                  onChange={(e) => setForm((f) => ({ ...f, role: e.target.value }))}
                  placeholder="Software Engineer"
                />
              </div>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="label">Date & Time</label>
                <input
                  type="datetime-local" className="input"
                  value={form.scheduled_at}
                  onChange={(e) => setForm((f) => ({ ...f, scheduled_at: e.target.value }))}
                />
              </div>
              <div>
                <label className="label">Location</label>
                <input
                  type="text" className="input"
                  value={form.location}
                  onChange={(e) => setForm((f) => ({ ...f, location: e.target.value }))}
                  placeholder="Zoom / San Francisco"
                />
              </div>
            </div>
            <div>
              <label className="label">Notes</label>
              <textarea
                className="input resize-none h-20 text-sm"
                value={form.notes}
                onChange={(e) => setForm((f) => ({ ...f, notes: e.target.value }))}
                placeholder="Interview format, topics to prep..."
              />
            </div>
            {form.job_id && (
              <p className="text-xs text-brand">
                Linked to job score: {form.job_score}/100
                {form.job_url && (
                  <> · <a href={form.job_url} target="_blank" rel="noopener noreferrer" className="underline">View job</a></>
                )}
              </p>
            )}
            {formError && <p className="text-red-400 text-sm">{formError}</p>}
            <div className="flex gap-2">
              <button type="submit" disabled={saving} className="btn-primary text-sm">
                {saving ? "Creating…" : "Create"}
              </button>
              <button type="button" onClick={() => { setShowForm(false); setForm(EMPTY_FORM); }} className="btn-ghost text-sm">
                Cancel
              </button>
            </div>
          </form>
        )}

        {/* Kanban */}
        {fetching ? (
          <p className="text-slate-400 text-sm">Loading…</p>
        ) : interviews.length === 0 ? (
          <div className="card text-center py-16">
            <p className="text-slate-400">No interviews tracked yet.</p>
            <p className="text-slate-500 text-xs mt-1">
              Click &quot;+ New Interview&quot; or use &quot;Track Interview&quot; on any job card.
            </p>
          </div>
        ) : (
          <KanbanBoard
            interviews={interviews}
            onStageChange={handleStageChange}
            onDelete={handleDelete}
          />
        )}
      </main>
    </>
  );
}

export default function InterviewsPage() {
  return (
    <Suspense>
      <InterviewsContent />
    </Suspense>
  );
}
