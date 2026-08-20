"use client";

import { useState, useRef, useCallback, useEffect } from "react";
import { useAuth } from "@/lib/auth";
import { useRouter } from "next/navigation";
import {
  api,
  type ResumeData,
  type ResumeTemplate,
  type ResumeCheckResult,
  type ResumeExperience,
  type ResumeEducation,
  type ResumeProject,
} from "@/lib/api";

// ── Empty defaults ────────────────────────────────────────────────────────────

const EMPTY_RESUME: ResumeData = {
  name: "", email: "", phone: "", location: "",
  linkedin: "", github: "", website: "", summary: "",
  experience: [], education: [],
  skills: { languages: [], frameworks: [], tools: [], other: [] },
  projects: [], certifications: [],
};

const EMPTY_EXP: ResumeExperience = {
  title: "", company: "", location: "", start_date: "", end_date: "", bullets: [""],
};
const EMPTY_EDU: ResumeEducation = {
  degree: "", school: "", location: "", year: "", gpa: "",
};
const EMPTY_PROJ: ResumeProject = {
  name: "", description: "", url: "", bullets: [""],
};

// ── Template metadata ─────────────────────────────────────────────────────────

const TEMPLATES: { id: ResumeTemplate; label: string; desc: string; badge: string; output: string }[] = [
  {
    id: "typst-modern",
    label: "Modern",
    desc: "Clean two-column layout with blue section headers. Inspired by jxpeng98/Typst-CV-Resume.",
    badge: "Typst",
    output: "PDF",
  },
  {
    id: "typst-silver",
    label: "Silver Dev",
    desc: "Minimal, developer-focused layout. Compact and ATS-friendly. Based on silver-dev-cv.",
    badge: "Typst",
    output: "PDF",
  },
  {
    id: "latex-us",
    label: "US Tech",
    desc: "Classic US software engineering resume (Jake's Resume style). Best for FAANG applications.",
    badge: "LaTeX",
    output: ".tex",
  },
];

// ── Chip input ────────────────────────────────────────────────────────────────

function ChipInput({
  label, items, onChange,
}: { label: string; items: string[]; onChange: (v: string[]) => void }) {
  const [input, setInput] = useState("");
  const add = () => {
    const v = input.trim();
    if (v && !items.includes(v)) onChange([...items, v]);
    setInput("");
  };
  return (
    <div>
      <label className="block text-xs text-slate-400 mb-1">{label}</label>
      <div className="flex flex-wrap gap-1.5 mb-2">
        {items.map((item) => (
          <span key={item} className="flex items-center gap-1 bg-slate-700 text-slate-200 text-xs px-2 py-0.5 rounded-full">
            {item}
            <button onClick={() => onChange(items.filter((i) => i !== item))} className="text-slate-400 hover:text-white">×</button>
          </span>
        ))}
      </div>
      <div className="flex gap-2">
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); add(); } }}
          placeholder={`Add ${label.toLowerCase()}...`}
          className="flex-1 bg-slate-800 border border-slate-600 rounded px-2 py-1 text-sm text-white placeholder-slate-500 focus:outline-none focus:border-brand"
        />
        <button onClick={add} className="px-3 py-1 bg-slate-700 hover:bg-slate-600 text-sm rounded text-slate-300">+</button>
      </div>
    </div>
  );
}

// ── Text input helper ─────────────────────────────────────────────────────────

function Field({
  label, value, onChange, placeholder = "", multiline = false,
}: { label: string; value: string; onChange: (v: string) => void; placeholder?: string; multiline?: boolean }) {
  return (
    <div>
      <label className="block text-xs text-slate-400 mb-1">{label}</label>
      {multiline ? (
        <textarea
          value={value}
          onChange={(e) => onChange(e.target.value)}
          placeholder={placeholder}
          rows={3}
          className="w-full bg-slate-800 border border-slate-600 rounded px-3 py-2 text-sm text-white placeholder-slate-500 focus:outline-none focus:border-brand resize-none"
        />
      ) : (
        <input
          type="text"
          value={value}
          onChange={(e) => onChange(e.target.value)}
          placeholder={placeholder}
          className="w-full bg-slate-800 border border-slate-600 rounded px-3 py-2 text-sm text-white placeholder-slate-500 focus:outline-none focus:border-brand"
        />
      )}
    </div>
  );
}

// ── Score ring ────────────────────────────────────────────────────────────────

function ScoreRing({ score, size = 80 }: { score: number; size?: number }) {
  const r = size / 2 - 6;
  const circ = 2 * Math.PI * r;
  const pct = score / 100;
  const color = score >= 75 ? "#22c55e" : score >= 50 ? "#f59e0b" : "#ef4444";
  return (
    <svg width={size} height={size}>
      <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="#334155" strokeWidth={6} />
      <circle
        cx={size / 2} cy={size / 2} r={r} fill="none"
        stroke={color} strokeWidth={6}
        strokeDasharray={`${circ * pct} ${circ * (1 - pct)}`}
        strokeLinecap="round"
        transform={`rotate(-90 ${size / 2} ${size / 2})`}
      />
      <text x={size / 2} y={size / 2 + 5} textAnchor="middle" fill="white" fontSize={size / 4} fontWeight="bold">{score}</text>
    </svg>
  );
}

// ── Main page ─────────────────────────────────────────────────────────────────

type Tab = "builder" | "tailor" | "checker";

export default function ResumePage() {
  const { user } = useAuth();
  const router = useRouter();

  useEffect(() => { if (!user) router.replace("/"); }, [user, router]);

  const [activeTab, setActiveTab] = useState<Tab>("builder");

  // Builder state
  const [step, setStep] = useState(1);
  const [resume, setResume] = useState<ResumeData>(EMPTY_RESUME);
  const [selectedTemplate, setSelectedTemplate] = useState<ResumeTemplate>("typst-modern");
  const [uploading, setUploading] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [saving, setSaving] = useState(false);
  const [driveUrl, setDriveUrl] = useState("");
  const [uploadMode, setUploadMode] = useState<"file" | "drive">("file");
  const [error, setError] = useState("");
  const fileRef = useRef<HTMLInputElement>(null);

  // Checker state
  const [checkJobDesc, setCheckJobDesc] = useState("");
  const [checkResult, setCheckResult] = useState<ResumeCheckResult | null>(null);
  const [checking, setChecking] = useState(false);
  const [checkError, setCheckError] = useState("");

  // Tailor state
  const [tailorJobId, setTailorJobId] = useState<string | null>(null);
  const [tailorJobDesc, setTailorJobDesc] = useState("");
  const [tailoring, setTailoring] = useState(false);
  const [tailorError, setTailorError] = useState("");
  const [tailoredActive, setTailoredActive] = useState(false);
  const [originalResume, setOriginalResume] = useState<ResumeData | null>(null);

  // Load saved resume on mount
  useEffect(() => {
    api.getResume().then((saved) => {
      if (saved && Object.keys(saved).length > 0) {
        setResume({ ...EMPTY_RESUME, ...saved });
        setStep(2); // skip upload if already have data
      }
    }).catch(() => {});

    const jobId = new URLSearchParams(window.location.search).get("tailor_job_id");
    if (jobId) {
      setTailorJobId(jobId);
      setActiveTab("tailor");
    }
  }, []);

  // ── Tailor CV for a job posting ─────────────────────────────────────────────

  const handleTailor = async () => {
    if (!tailorJobId && !tailorJobDesc.trim()) return;
    setTailoring(true);
    setTailorError("");
    try {
      const tailored = await api.tailorResume({
        job_id: tailorJobId ?? undefined,
        job_description: tailorJobId ? undefined : tailorJobDesc.trim(),
      });
      setOriginalResume(resume);
      setResume(tailored);
      setTailoredActive(true);
      setSelectedTemplate("typst-silver");
      setActiveTab("builder");
      setStep(3);
    } catch (e: unknown) {
      setTailorError(e instanceof Error ? e.message : "Could not tailor resume");
    } finally {
      setTailoring(false);
    }
  };

  const handleDiscardTailored = () => {
    if (originalResume) setResume(originalResume);
    setTailoredActive(false);
    setOriginalResume(null);
  };

  const availableTemplates = tailoredActive
    ? TEMPLATES.filter((t) => t.id === "typst-silver" || t.id === "latex-us")
    : TEMPLATES;

  // ── Step 1: Upload ──────────────────────────────────────────────────────────

  const handleFileUpload = useCallback(async (file: File) => {
    setUploading(true);
    setError("");
    try {
      const parsed = await api.parseResumeFile(file);
      setResume({ ...EMPTY_RESUME, ...parsed });
      setStep(2);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Upload failed");
    } finally {
      setUploading(false);
    }
  }, []);

  const handleDriveUpload = async () => {
    if (!driveUrl.trim()) return;
    setUploading(true);
    setError("");
    try {
      const parsed = await api.parseResumeDriveUrl(driveUrl.trim());
      setResume({ ...EMPTY_RESUME, ...parsed });
      setStep(2);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Could not fetch from Google Drive");
    } finally {
      setUploading(false);
    }
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    const file = e.dataTransfer.files[0];
    if (file) handleFileUpload(file);
  };

  // ── Resume field helpers ────────────────────────────────────────────────────

  const setField = (key: keyof ResumeData, value: unknown) =>
    setResume((r) => ({ ...r, [key]: value }));

  const setSkill = (key: keyof typeof resume.skills, value: string[]) =>
    setResume((r) => ({ ...r, skills: { ...r.skills, [key]: value } }));

  // ── Step 4: Generate ────────────────────────────────────────────────────────

  const handleGenerate = async () => {
    setGenerating(true);
    setError("");
    try {
      const blob = await api.generateResume(resume, selectedTemplate, true);
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = selectedTemplate === "latex-us" ? "resume.tex" : "resume.pdf";
      a.click();
      URL.revokeObjectURL(url);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Generation failed");
    } finally {
      setGenerating(false);
    }
  };

  const handleSaveAndContinue = async () => {
    setSaving(true);
    try {
      await api.saveResume(resume);
    } catch {
      // non-fatal
    } finally {
      setSaving(false);
    }
    setStep(3);
  };

  // ── Resume Checker ──────────────────────────────────────────────────────────

  const handleCheck = async () => {
    if (!checkJobDesc.trim()) return;
    setChecking(true);
    setCheckError("");
    setCheckResult(null);
    try {
      const result = await api.checkResume({ job_description: checkJobDesc });
      setCheckResult(result);
    } catch (e: unknown) {
      setCheckError(e instanceof Error ? e.message : "Check failed");
    } finally {
      setChecking(false);
    }
  };

  // ── Render ──────────────────────────────────────────────────────────────────

  return (
    <div className="max-w-3xl mx-auto px-4 py-8">
      {/* Tab switcher */}
      <div className="flex gap-1 mb-8 bg-slate-800/50 p-1 rounded-lg w-fit">
        {(["builder", "tailor", "checker"] as Tab[]).map((t) => (
          <button
            key={t}
            onClick={() => setActiveTab(t)}
            className={`px-5 py-2 rounded-md text-sm font-medium transition-colors capitalize ${
              activeTab === t ? "bg-brand text-white" : "text-slate-400 hover:text-white"
            }`}
          >
            {t === "builder" ? "Resume Builder" : t === "tailor" ? "Tailor CV" : "Resume Checker"}
          </button>
        ))}
      </div>

      {activeTab === "builder" && (
        <>
          {/* Progress bar */}
          <div className="flex items-center gap-2 mb-8">
            {[1, 2, 3, 4].map((s) => (
              <div key={s} className="flex items-center gap-2">
                <button
                  onClick={() => step > s && setStep(s)}
                  className={`w-8 h-8 rounded-full flex items-center justify-center text-sm font-semibold transition-colors ${
                    step === s
                      ? "bg-brand text-white"
                      : step > s
                      ? "bg-green-600 text-white cursor-pointer"
                      : "bg-slate-700 text-slate-400"
                  }`}
                >
                  {step > s ? "✓" : s}
                </button>
                {s < 4 && <div className={`flex-1 h-0.5 w-12 ${step > s ? "bg-green-600" : "bg-slate-700"}`} />}
              </div>
            ))}
            <div className="ml-2 text-sm text-slate-400">
              {["Upload", "Edit", "Template", "Download"][step - 1]}
            </div>
          </div>

          {error && (
            <div className="mb-4 p-3 bg-red-900/40 border border-red-700 rounded text-red-300 text-sm">{error}</div>
          )}

          {/* Step 1 — Upload */}
          {step === 1 && (
            <div className="space-y-6">
              <div>
                <h2 className="text-xl font-semibold mb-1">Import your CV</h2>
                <p className="text-slate-400 text-sm">Upload a PDF or DOCX and Claude will extract your data automatically.</p>
              </div>

              <div className="flex gap-2 mb-4">
                {(["file", "drive"] as const).map((m) => (
                  <button
                    key={m}
                    onClick={() => setUploadMode(m)}
                    className={`px-4 py-1.5 rounded-full text-sm transition-colors ${
                      uploadMode === m ? "bg-slate-600 text-white" : "text-slate-400 hover:text-white"
                    }`}
                  >
                    {m === "file" ? "File upload" : "Google Drive"}
                  </button>
                ))}
              </div>

              {uploadMode === "file" ? (
                <div
                  onDrop={handleDrop}
                  onDragOver={(e) => e.preventDefault()}
                  onClick={() => fileRef.current?.click()}
                  className="border-2 border-dashed border-slate-600 hover:border-brand rounded-xl p-12 text-center cursor-pointer transition-colors"
                >
                  <input
                    ref={fileRef}
                    type="file"
                    accept=".pdf,.doc,.docx"
                    className="hidden"
                    onChange={(e) => { const f = e.target.files?.[0]; if (f) handleFileUpload(f); }}
                  />
                  {uploading ? (
                    <p className="text-slate-400">Parsing with Claude...</p>
                  ) : (
                    <>
                      <div className="text-4xl mb-3">📄</div>
                      <p className="text-white font-medium">Drop your CV here or click to browse</p>
                      <p className="text-slate-500 text-sm mt-1">PDF or DOCX</p>
                    </>
                  )}
                </div>
              ) : (
                <div className="space-y-3">
                  <p className="text-sm text-slate-400">Paste a Google Drive share link (set access to "Anyone with the link").</p>
                  <div className="flex gap-2">
                    <input
                      type="url"
                      value={driveUrl}
                      onChange={(e) => setDriveUrl(e.target.value)}
                      placeholder="https://drive.google.com/file/d/..."
                      className="flex-1 bg-slate-800 border border-slate-600 rounded px-3 py-2 text-sm text-white placeholder-slate-500 focus:outline-none focus:border-brand"
                    />
                    <button
                      onClick={handleDriveUpload}
                      disabled={uploading || !driveUrl.trim()}
                      className="px-4 py-2 bg-brand hover:bg-brand/90 disabled:opacity-50 text-white text-sm rounded font-medium"
                    >
                      {uploading ? "Importing..." : "Import"}
                    </button>
                  </div>
                </div>
              )}

              <div className="text-center text-slate-500 text-sm">or</div>
              <button
                onClick={() => setStep(2)}
                className="w-full py-2.5 border border-slate-600 hover:border-slate-400 rounded-lg text-slate-300 text-sm transition-colors"
              >
                Start from scratch
              </button>
            </div>
          )}

          {/* Step 2 — Edit */}
          {step === 2 && (
            <div className="space-y-8">
              <h2 className="text-xl font-semibold">Review & edit your resume</h2>

              {/* Personal Info */}
              <section className="space-y-3">
                <h3 className="text-sm font-semibold text-slate-300 uppercase tracking-wide">Personal Information</h3>
                <div className="grid grid-cols-2 gap-3">
                  <Field label="Full Name" value={resume.name} onChange={(v) => setField("name", v)} />
                  <Field label="Email" value={resume.email} onChange={(v) => setField("email", v)} />
                  <Field label="Phone" value={resume.phone} onChange={(v) => setField("phone", v)} />
                  <Field label="Location" value={resume.location} onChange={(v) => setField("location", v)} />
                  <Field label="LinkedIn" value={resume.linkedin} onChange={(v) => setField("linkedin", v)} placeholder="linkedin.com/in/handle" />
                  <Field label="GitHub" value={resume.github} onChange={(v) => setField("github", v)} placeholder="github.com/handle" />
                  <div className="col-span-2">
                    <Field label="Website" value={resume.website} onChange={(v) => setField("website", v)} placeholder="yoursite.dev" />
                  </div>
                </div>
                <Field label="Professional Summary" value={resume.summary} onChange={(v) => setField("summary", v)} multiline placeholder="2-3 sentences about your expertise and goals..." />
              </section>

              {/* Experience */}
              <section className="space-y-4">
                <div className="flex items-center justify-between">
                  <h3 className="text-sm font-semibold text-slate-300 uppercase tracking-wide">Experience</h3>
                  <button
                    onClick={() => setField("experience", [...resume.experience, { ...EMPTY_EXP }])}
                    className="text-xs text-brand hover:underline"
                  >
                    + Add position
                  </button>
                </div>
                {resume.experience.map((exp, i) => (
                  <div key={i} className="bg-slate-800/60 border border-slate-700 rounded-lg p-4 space-y-3">
                    <div className="flex justify-between">
                      <span className="text-xs text-slate-500">Position {i + 1}</span>
                      <button
                        onClick={() => setField("experience", resume.experience.filter((_, j) => j !== i))}
                        className="text-xs text-red-400 hover:text-red-300"
                      >
                        Remove
                      </button>
                    </div>
                    <div className="grid grid-cols-2 gap-3">
                      <Field label="Job Title" value={exp.title} onChange={(v) => {
                        const updated = [...resume.experience]; updated[i] = { ...exp, title: v }; setField("experience", updated);
                      }} />
                      <Field label="Company" value={exp.company} onChange={(v) => {
                        const updated = [...resume.experience]; updated[i] = { ...exp, company: v }; setField("experience", updated);
                      }} />
                      <Field label="Location" value={exp.location} onChange={(v) => {
                        const updated = [...resume.experience]; updated[i] = { ...exp, location: v }; setField("experience", updated);
                      }} />
                      <div className="grid grid-cols-2 gap-2">
                        <Field label="Start" value={exp.start_date} onChange={(v) => {
                          const updated = [...resume.experience]; updated[i] = { ...exp, start_date: v }; setField("experience", updated);
                        }} placeholder="Jan 2020" />
                        <Field label="End" value={exp.end_date} onChange={(v) => {
                          const updated = [...resume.experience]; updated[i] = { ...exp, end_date: v }; setField("experience", updated);
                        }} placeholder="Present" />
                      </div>
                    </div>
                    <div>
                      <label className="block text-xs text-slate-400 mb-1">Bullets (one per line)</label>
                      <textarea
                        value={exp.bullets.join("\n")}
                        onChange={(e) => {
                          const updated = [...resume.experience];
                          updated[i] = { ...exp, bullets: e.target.value.split("\n") };
                          setField("experience", updated);
                        }}
                        rows={4}
                        className="w-full bg-slate-800 border border-slate-600 rounded px-3 py-2 text-sm text-white placeholder-slate-500 focus:outline-none focus:border-brand resize-none font-mono"
                        placeholder="Led team of 5 engineers to deliver X feature&#10;Reduced API latency by 40% via caching"
                      />
                    </div>
                  </div>
                ))}
              </section>

              {/* Education */}
              <section className="space-y-4">
                <div className="flex items-center justify-between">
                  <h3 className="text-sm font-semibold text-slate-300 uppercase tracking-wide">Education</h3>
                  <button
                    onClick={() => setField("education", [...resume.education, { ...EMPTY_EDU }])}
                    className="text-xs text-brand hover:underline"
                  >
                    + Add education
                  </button>
                </div>
                {resume.education.map((ed, i) => (
                  <div key={i} className="bg-slate-800/60 border border-slate-700 rounded-lg p-4 space-y-3">
                    <div className="flex justify-between">
                      <span className="text-xs text-slate-500">Education {i + 1}</span>
                      <button onClick={() => setField("education", resume.education.filter((_, j) => j !== i))} className="text-xs text-red-400 hover:text-red-300">Remove</button>
                    </div>
                    <div className="grid grid-cols-2 gap-3">
                      <Field label="Degree" value={ed.degree} onChange={(v) => { const u = [...resume.education]; u[i] = { ...ed, degree: v }; setField("education", u); }} placeholder="B.S. Computer Science" />
                      <Field label="School" value={ed.school} onChange={(v) => { const u = [...resume.education]; u[i] = { ...ed, school: v }; setField("education", u); }} />
                      <Field label="Location" value={ed.location} onChange={(v) => { const u = [...resume.education]; u[i] = { ...ed, location: v }; setField("education", u); }} />
                      <div className="grid grid-cols-2 gap-2">
                        <Field label="Year" value={ed.year} onChange={(v) => { const u = [...resume.education]; u[i] = { ...ed, year: v }; setField("education", u); }} placeholder="2020" />
                        <Field label="GPA" value={ed.gpa} onChange={(v) => { const u = [...resume.education]; u[i] = { ...ed, gpa: v }; setField("education", u); }} placeholder="3.8" />
                      </div>
                    </div>
                  </div>
                ))}
              </section>

              {/* Skills */}
              <section className="space-y-4">
                <h3 className="text-sm font-semibold text-slate-300 uppercase tracking-wide">Skills</h3>
                <div className="grid grid-cols-2 gap-4">
                  <ChipInput label="Programming Languages" items={resume.skills.languages} onChange={(v) => setSkill("languages", v)} />
                  <ChipInput label="Frameworks & Libraries" items={resume.skills.frameworks} onChange={(v) => setSkill("frameworks", v)} />
                  <ChipInput label="Tools & Platforms" items={resume.skills.tools} onChange={(v) => setSkill("tools", v)} />
                  <ChipInput label="Other" items={resume.skills.other} onChange={(v) => setSkill("other", v)} />
                </div>
              </section>

              {/* Projects */}
              <section className="space-y-4">
                <div className="flex items-center justify-between">
                  <h3 className="text-sm font-semibold text-slate-300 uppercase tracking-wide">Projects</h3>
                  <button onClick={() => setField("projects", [...resume.projects, { ...EMPTY_PROJ }])} className="text-xs text-brand hover:underline">+ Add project</button>
                </div>
                {resume.projects.map((p, i) => (
                  <div key={i} className="bg-slate-800/60 border border-slate-700 rounded-lg p-4 space-y-3">
                    <div className="flex justify-between">
                      <span className="text-xs text-slate-500">Project {i + 1}</span>
                      <button onClick={() => setField("projects", resume.projects.filter((_, j) => j !== i))} className="text-xs text-red-400 hover:text-red-300">Remove</button>
                    </div>
                    <div className="grid grid-cols-2 gap-3">
                      <Field label="Name" value={p.name} onChange={(v) => { const u = [...resume.projects]; u[i] = { ...p, name: v }; setField("projects", u); }} />
                      <Field label="URL" value={p.url} onChange={(v) => { const u = [...resume.projects]; u[i] = { ...p, url: v }; setField("projects", u); }} placeholder="github.com/user/repo" />
                      <div className="col-span-2">
                        <Field label="Description" value={p.description} onChange={(v) => { const u = [...resume.projects]; u[i] = { ...p, description: v }; setField("projects", u); }} />
                      </div>
                    </div>
                    <div>
                      <label className="block text-xs text-slate-400 mb-1">Bullets (one per line)</label>
                      <textarea
                        value={p.bullets.join("\n")}
                        onChange={(e) => { const u = [...resume.projects]; u[i] = { ...p, bullets: e.target.value.split("\n") }; setField("projects", u); }}
                        rows={3}
                        className="w-full bg-slate-800 border border-slate-600 rounded px-3 py-2 text-sm text-white placeholder-slate-500 focus:outline-none focus:border-brand resize-none font-mono"
                      />
                    </div>
                  </div>
                ))}
              </section>

              {/* Certifications */}
              <section className="space-y-4">
                <h3 className="text-sm font-semibold text-slate-300 uppercase tracking-wide">Certifications</h3>
                <ChipInput label="Certifications" items={resume.certifications} onChange={(v) => setField("certifications", v)} />
              </section>

              <div className="flex justify-between pt-4">
                <button onClick={() => setStep(1)} className="px-4 py-2 text-sm text-slate-400 hover:text-white">← Back</button>
                <button
                  onClick={handleSaveAndContinue}
                  disabled={saving}
                  className="px-6 py-2.5 bg-brand hover:bg-brand/90 disabled:opacity-50 text-white text-sm font-medium rounded-lg"
                >
                  {saving ? "Saving..." : "Save & choose template →"}
                </button>
              </div>
            </div>
          )}

          {/* Step 3 — Template selection */}
          {step === 3 && (
            <div className="space-y-6">
              {tailoredActive && (
                <div className="flex items-center justify-between gap-3 p-3 bg-brand/10 border border-brand/40 rounded-lg text-sm">
                  <span className="text-slate-200">🎯 This is a tailored version — not saved to your profile.</span>
                  <button onClick={handleDiscardTailored} className="text-brand hover:underline whitespace-nowrap">
                    Discard & restore original
                  </button>
                </div>
              )}
              <h2 className="text-xl font-semibold">Choose a template</h2>
              <div className="grid gap-4">
                {availableTemplates.map((tpl) => (
                  <button
                    key={tpl.id}
                    onClick={() => setSelectedTemplate(tpl.id)}
                    className={`text-left p-5 rounded-xl border-2 transition-all ${
                      selectedTemplate === tpl.id
                        ? "border-brand bg-brand/10"
                        : "border-slate-700 hover:border-slate-500"
                    }`}
                  >
                    <div className="flex items-start justify-between">
                      <div>
                        <div className="flex items-center gap-2 mb-1">
                          <span className="font-semibold text-white">{tpl.label}</span>
                          <span className="text-xs bg-slate-700 text-slate-300 px-2 py-0.5 rounded-full">{tpl.badge}</span>
                          <span className="text-xs bg-green-900/60 text-green-400 px-2 py-0.5 rounded-full">↓ {tpl.output}</span>
                        </div>
                        <p className="text-sm text-slate-400">{tpl.desc}</p>
                      </div>
                      <div className={`w-5 h-5 rounded-full border-2 mt-0.5 flex-shrink-0 ${
                        selectedTemplate === tpl.id ? "border-brand bg-brand" : "border-slate-500"
                      }`} />
                    </div>
                    {tpl.id === "latex-us" && (
                      <p className="text-xs text-amber-400 mt-2">
                        Downloads a .tex file — open in Overleaf or compile locally with pdflatex.
                      </p>
                    )}
                  </button>
                ))}
              </div>
              <div className="flex justify-between">
                <button onClick={() => setStep(2)} className="px-4 py-2 text-sm text-slate-400 hover:text-white">← Back</button>
                <button
                  onClick={() => setStep(4)}
                  className="px-6 py-2.5 bg-brand hover:bg-brand/90 text-white text-sm font-medium rounded-lg"
                >
                  Continue →
                </button>
              </div>
            </div>
          )}

          {/* Step 4 — Download */}
          {step === 4 && (
            <div className="space-y-6">
              {tailoredActive && (
                <div className="flex items-center justify-between gap-3 p-3 bg-brand/10 border border-brand/40 rounded-lg text-sm">
                  <span className="text-slate-200">🎯 This is a tailored version — not saved to your profile.</span>
                  <button onClick={handleDiscardTailored} className="text-brand hover:underline whitespace-nowrap">
                    Discard & restore original
                  </button>
                </div>
              )}
              <h2 className="text-xl font-semibold">Download your resume</h2>
              <div className="bg-slate-800/60 border border-slate-700 rounded-xl p-6 text-center space-y-4">
                <div className="text-5xl">
                  {selectedTemplate === "latex-us" ? "📄" : "📑"}
                </div>
                <div>
                  <p className="font-semibold text-white">
                    {TEMPLATES.find((t) => t.id === selectedTemplate)?.label} template
                  </p>
                  <p className="text-sm text-slate-400 mt-1">
                    {selectedTemplate === "latex-us"
                      ? "A .tex file ready to compile in Overleaf or with pdflatex"
                      : "A PDF compiled with Typst — opens in any PDF viewer"}
                  </p>
                </div>
                <button
                  onClick={handleGenerate}
                  disabled={generating}
                  className="px-8 py-3 bg-brand hover:bg-brand/90 disabled:opacity-50 text-white font-semibold rounded-lg transition-colors"
                >
                  {generating ? "Compiling..." : `Download ${selectedTemplate === "latex-us" ? ".tex" : "PDF"}`}
                </button>
                {selectedTemplate === "latex-us" && (
                  <div className="pt-2">
                    <a
                      href="https://www.overleaf.com/latex/templates"
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-sm text-brand hover:underline"
                    >
                      Open Overleaf to compile →
                    </a>
                  </div>
                )}
              </div>
              <div className="flex justify-between">
                <button onClick={() => setStep(3)} className="px-4 py-2 text-sm text-slate-400 hover:text-white">← Change template</button>
                <button
                  onClick={() => { setStep(2); }}
                  className="px-4 py-2 text-sm text-slate-400 hover:text-white"
                >
                  Edit resume →
                </button>
              </div>
            </div>
          )}
        </>
      )}

      {/* ── Tailor CV ──────────────────────────────────────────────────────── */}
      {activeTab === "tailor" && (
        <div className="space-y-6">
          <div>
            <h2 className="text-xl font-semibold mb-1">Tailor your CV for a job</h2>
            <p className="text-slate-400 text-sm">
              Claude rewrites your saved resume's summary and reorders/emphasizes your existing bullets and skills
              to match this job — it never invents experience, employers, or metrics that aren't already in your
              resume. Output as Typst (Silver Dev) or LaTeX.
            </p>
          </div>

          {tailorJobId ? (
            <div className="p-3 bg-slate-800/60 border border-slate-700 rounded-lg text-sm text-slate-300 flex items-center justify-between gap-3">
              <span>Tailoring for the job you selected from your job feed.</span>
              <button
                onClick={() => setTailorJobId(null)}
                className="text-xs text-slate-400 hover:text-white whitespace-nowrap"
              >
                Paste a description instead
              </button>
            </div>
          ) : (
            <div className="space-y-3">
              <label className="block text-sm text-slate-300 font-medium">Job Description</label>
              <textarea
                value={tailorJobDesc}
                onChange={(e) => setTailorJobDesc(e.target.value)}
                rows={8}
                placeholder="Paste the full job description here..."
                className="w-full bg-slate-800 border border-slate-600 rounded-lg px-4 py-3 text-sm text-white placeholder-slate-500 focus:outline-none focus:border-brand resize-y"
              />
            </div>
          )}

          {tailorError && (
            <div className="p-3 bg-red-900/40 border border-red-700 rounded text-red-300 text-sm">{tailorError}</div>
          )}

          <button
            onClick={handleTailor}
            disabled={tailoring || (!tailorJobId && !tailorJobDesc.trim())}
            className="px-6 py-2.5 bg-brand hover:bg-brand/90 disabled:opacity-50 text-white text-sm font-medium rounded-lg w-full"
          >
            {tailoring ? "Tailoring with Claude..." : "Generate tailored CV →"}
          </button>
        </div>
      )}

      {/* ── Resume Checker ──────────────────────────────────────────────────── */}
      {activeTab === "checker" && (
        <div className="space-y-6">
          <div>
            <h2 className="text-xl font-semibold mb-1">Resume Checker</h2>
            <p className="text-slate-400 text-sm">
              Paste a job description and Claude analyzes how well your saved resume matches — ATS score, skills gaps, quick wins.
            </p>
          </div>

          <div className="space-y-3">
            <label className="block text-sm text-slate-300 font-medium">Job Description</label>
            <textarea
              value={checkJobDesc}
              onChange={(e) => setCheckJobDesc(e.target.value)}
              rows={8}
              placeholder="Paste the full job description here..."
              className="w-full bg-slate-800 border border-slate-600 rounded-lg px-4 py-3 text-sm text-white placeholder-slate-500 focus:outline-none focus:border-brand resize-y"
            />
          </div>

          {checkError && (
            <div className="p-3 bg-red-900/40 border border-red-700 rounded text-red-300 text-sm">{checkError}</div>
          )}

          <button
            onClick={handleCheck}
            disabled={checking || !checkJobDesc.trim()}
            className="px-6 py-2.5 bg-brand hover:bg-brand/90 disabled:opacity-50 text-white text-sm font-medium rounded-lg w-full"
          >
            {checking ? "Analyzing with Claude..." : "Check my resume"}
          </button>

          {checkResult && (
            <div className="space-y-6 mt-4">
              {/* Score overview */}
              <div className="grid grid-cols-2 gap-4">
                <div className="bg-slate-800/60 border border-slate-700 rounded-xl p-5 flex items-center gap-4">
                  <ScoreRing score={checkResult.overall_score} size={72} />
                  <div>
                    <p className="text-xs text-slate-400 uppercase tracking-wide">Overall Match</p>
                    <p className="text-lg font-bold text-white">{checkResult.overall_score}/100</p>
                  </div>
                </div>
                <div className="bg-slate-800/60 border border-slate-700 rounded-xl p-5 flex items-center gap-4">
                  <ScoreRing score={checkResult.ats_score} size={72} />
                  <div>
                    <p className="text-xs text-slate-400 uppercase tracking-wide">ATS Score</p>
                    <p className="text-lg font-bold text-white">{checkResult.ats_score}/100</p>
                  </div>
                </div>
              </div>

              {/* Section scores */}
              <div className="grid grid-cols-2 gap-3">
                {Object.entries(checkResult.sections).map(([key, section]) => (
                  <div key={key} className="bg-slate-800/40 border border-slate-700 rounded-lg p-4">
                    <div className="flex justify-between items-center mb-2">
                      <span className="text-xs font-medium text-slate-300 capitalize">
                        {key.replace(/_/g, " ")}
                      </span>
                      <span className={`text-sm font-bold ${
                        section.score >= 75 ? "text-green-400" : section.score >= 50 ? "text-amber-400" : "text-red-400"
                      }`}>
                        {section.score}
                      </span>
                    </div>
                    <div className="w-full h-1 bg-slate-700 rounded-full mb-2">
                      <div
                        className={`h-1 rounded-full ${section.score >= 75 ? "bg-green-500" : section.score >= 50 ? "bg-amber-500" : "bg-red-500"}`}
                        style={{ width: `${section.score}%` }}
                      />
                    </div>
                    <p className="text-xs text-slate-400">{section.feedback}</p>
                    {section.missing && section.missing.length > 0 && (
                      <div className="mt-2 flex flex-wrap gap-1">
                        {section.missing.slice(0, 4).map((m) => (
                          <span key={m} className="text-xs bg-red-900/40 text-red-300 px-1.5 py-0.5 rounded">{m}</span>
                        ))}
                      </div>
                    )}
                    {section.missing_keywords && section.missing_keywords.length > 0 && (
                      <div className="mt-2 flex flex-wrap gap-1">
                        {section.missing_keywords.slice(0, 4).map((m) => (
                          <span key={m} className="text-xs bg-amber-900/40 text-amber-300 px-1.5 py-0.5 rounded">{m}</span>
                        ))}
                      </div>
                    )}
                  </div>
                ))}
              </div>

              {/* Summary */}
              <div className="bg-slate-800/40 border border-slate-700 rounded-lg p-4">
                <p className="text-sm text-slate-300">{checkResult.summary}</p>
              </div>

              {/* Strengths & Gaps */}
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <h4 className="text-sm font-semibold text-green-400 mb-2">Top Strengths</h4>
                  <ul className="space-y-1.5">
                    {checkResult.top_strengths.map((s) => (
                      <li key={s} className="flex items-start gap-2 text-sm text-slate-300">
                        <span className="text-green-500 mt-0.5">✓</span>{s}
                      </li>
                    ))}
                  </ul>
                </div>
                <div>
                  <h4 className="text-sm font-semibold text-red-400 mb-2">Critical Gaps</h4>
                  <ul className="space-y-1.5">
                    {checkResult.critical_gaps.map((g) => (
                      <li key={g} className="flex items-start gap-2 text-sm text-slate-300">
                        <span className="text-red-500 mt-0.5">✗</span>{g}
                      </li>
                    ))}
                  </ul>
                </div>
              </div>

              {/* Quick wins */}
              <div>
                <h4 className="text-sm font-semibold text-brand mb-3">Quick Wins</h4>
                <ol className="space-y-2">
                  {checkResult.quick_wins.map((w, i) => (
                    <li key={i} className="flex items-start gap-3 bg-slate-800/40 border border-slate-700 rounded-lg px-4 py-3">
                      <span className="text-brand font-bold text-sm mt-0.5">{i + 1}</span>
                      <span className="text-sm text-slate-200">{w}</span>
                    </li>
                  ))}
                </ol>
              </div>

              <button
                onClick={() => { setActiveTab("builder"); setStep(2); }}
                className="w-full py-2.5 border border-brand text-brand hover:bg-brand/10 rounded-lg text-sm font-medium transition-colors"
              >
                Edit resume based on feedback →
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
