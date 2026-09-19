const BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

function token() {
  if (typeof window === "undefined") return null;
  return localStorage.getItem("jwt");
}

async function req<T>(
  path: string,
  options: RequestInit = {}
): Promise<T> {
  const jwt = token();
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(options.headers as Record<string, string>),
  };
  if (jwt) headers["Authorization"] = `Bearer ${jwt}`;

  const res = await fetch(`${BASE}${path}`, { ...options, headers });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail ?? "Request failed");
  }
  return res.json();
}

async function reqBlob(path: string, options: RequestInit = {}): Promise<Blob> {
  const jwt = token();
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(options.headers as Record<string, string>),
  };
  if (jwt) headers["Authorization"] = `Bearer ${jwt}`;
  const res = await fetch(`${BASE}${path}`, { ...options, headers });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail ?? "Request failed");
  }
  return res.blob();
}

export const api = {
  // Auth
  signup: (email: string, password: string) =>
    req<{ token: string; user: User }>("/auth/signup", {
      method: "POST",
      body: JSON.stringify({ email, password }),
    }),
  login: (email: string, password: string) =>
    req<{ token: string; user: User }>("/auth/login", {
      method: "POST",
      body: JSON.stringify({ email, password }),
    }),
  me: () => req<User>("/auth/me"),

  // Searches
  getSearches: () => req<Search[]>("/searches"),
  createSearch: (data: CreateSearchPayload) =>
    req<Search>("/searches", { method: "POST", body: JSON.stringify(data) }),
  patchSearch: (id: string, active: boolean) =>
    req<Search>(`/searches/${id}`, { method: "PATCH", body: JSON.stringify({ active }) }),
  deleteSearch: (id: string) =>
    req<void>(`/searches/${id}`, { method: "DELETE" }),

  // Profile
  getProfile: () => req<Profile>("/profile"),
  updateProfile: (data: Partial<Profile>) =>
    req<{ updated: boolean }>("/profile", { method: "PUT", body: JSON.stringify(data) }),

  // Telegram
  startTelegramLink: () =>
    req<{ code: string; instructions: string; expires_in_minutes: number }>("/telegram/start-link", {
      method: "POST",
    }),

  // Jobs
  getJobs: (minScore = 0, limit = 20, applied?: boolean, dismissed?: boolean) =>
    req<{ items: Job[]; count: number }>(
      `/jobs?min_score=${minScore}&limit=${limit}${applied !== undefined ? `&applied=${applied}` : ""}${dismissed !== undefined ? `&dismissed=${dismissed}` : ""}`
    ),
  createInterviewBrief: (jobId: string) =>
    req<InterviewBrief>(`/jobs/${encodeURIComponent(jobId)}/interview-brief`, { method: "POST" }),
  setJobApplied: (jobId: string, applied: boolean) =>
    req<{ job_id: string; applied: boolean }>(`/jobs/${encodeURIComponent(jobId)}/applied`, {
      method: "PATCH",
      body: JSON.stringify({ applied }),
    }),
  setJobDismissed: (jobId: string, dismissed: boolean) =>
    req<{ job_id: string; dismissed: boolean }>(`/jobs/${encodeURIComponent(jobId)}/dismissed`, {
      method: "PATCH",
      body: JSON.stringify({ dismissed }),
    }),

  // Scraper
  runScraper: () => req<{ triggered: boolean }>("/scraper/run", { method: "POST" }),
  rescoreJobs: () => req<{ triggered: boolean }>("/scraper/run?mode=rescore", { method: "POST" }),

  // Interviews
  getInterviews: () => req<Interview[]>("/interviews"),
  createInterview: (data: Omit<Interview, "interview_id" | "user_id" | "created_at" | "updated_at">) =>
    req<Interview>("/interviews", { method: "POST", body: JSON.stringify(data) }),
  patchInterview: (id: string, data: Partial<Pick<Interview, "stage" | "scheduled_at" | "location" | "notes">>) =>
    req<Interview>(`/interviews/${id}`, { method: "PATCH", body: JSON.stringify(data) }),
  deleteInterview: (id: string) =>
    req<void>(`/interviews/${id}`, { method: "DELETE" }),
  draftFollowup: (id: string) =>
    req<{ subject: string; body: string }>(`/interviews/${id}/followup`, { method: "POST" }),

  // Resume Builder
  parseResumeFile: (file: File) => {
    const jwt = token();
    const form = new FormData();
    form.append("file", file);
    return fetch(`${BASE}/resume/parse`, {
      method: "POST",
      headers: jwt ? { Authorization: `Bearer ${jwt}` } : {},
      body: form,
    }).then(async (res) => {
      if (!res.ok) { const e = await res.json().catch(() => ({ detail: res.statusText })); throw new Error(e.detail); }
      return res.json() as Promise<ResumeData>;
    });
  },
  parseResumeDriveUrl: (driveUrl: string) => {
    const jwt = token();
    const form = new FormData();
    form.append("drive_url", driveUrl);
    return fetch(`${BASE}/resume/parse`, {
      method: "POST",
      headers: jwt ? { Authorization: `Bearer ${jwt}` } : {},
      body: form,
    }).then(async (res) => {
      if (!res.ok) { const e = await res.json().catch(() => ({ detail: res.statusText })); throw new Error(e.detail); }
      return res.json() as Promise<ResumeData>;
    });
  },
  getResume: () => req<Partial<ResumeData>>("/resume"),
  saveResume: (data: ResumeData) =>
    req<{ saved: boolean }>("/resume", { method: "PUT", body: JSON.stringify(data) }),
  generateResume: (resume: ResumeData, template: ResumeTemplate, compile = true) =>
    reqBlob("/resume/generate", {
      method: "POST",
      body: JSON.stringify({ resume, template, compile }),
    }),
  checkResume: (body: { resume?: ResumeData; job_description?: string; job_id?: string }) =>
    req<ResumeCheckResult>("/resume/check", { method: "POST", body: JSON.stringify(body) }),
  atsCheck: (body: { template: ResumeTemplate; job_description?: string; job_id?: string }) =>
    req<AtsCheckResult>("/resume/ats-check", { method: "POST", body: JSON.stringify(body) }),
  expandProfile: () => req<ExpandResult>("/resume/expand", { method: "POST" }),
  upskill: (body: { job_description?: string; job_id?: string }) =>
    req<UpskillResult>("/resume/upskill", { method: "POST", body: JSON.stringify(body) }),
  answerCareerQuestion: (body: { question: string; job_description?: string; job_id?: string }) =>
    req<{ answer: string }>("/resume/career-answer", { method: "POST", body: JSON.stringify(body) }),
  tailorResume: (body: { job_description?: string; job_id?: string }) =>
    req<ResumeData>("/resume/tailor", { method: "POST", body: JSON.stringify(body) }),
  translateResume: (language: string) =>
    req<ResumeData>("/resume/translate", { method: "POST", body: JSON.stringify({ language }) }),
  generateCoverLetter: (body: { job_description?: string; job_id?: string }) =>
    req<{ letter: string }>("/resume/cover-letter", { method: "POST", body: JSON.stringify(body) }),
  downloadCoverLetter: (resume: ResumeData, letter: string, compile = true) =>
    reqBlob("/resume/cover-letter/generate", {
      method: "POST",
      body: JSON.stringify({ resume, letter, compile }),
    }),
  saveCvHistory: (body: { company: string; role: string; template: ResumeTemplate; language?: string; job_id?: string; resume: ResumeData }) =>
    req<CvHistoryEntry>("/resume/history", { method: "POST", body: JSON.stringify(body) }),
  getCvHistory: () => req<CvHistoryEntry[]>("/resume/history"),
  downloadCvHistory: (created_at: string) =>
    reqBlob("/resume/history/download", { method: "POST", body: JSON.stringify({ created_at }) }),
  deleteCvHistory: (created_at: string) =>
    req<{ deleted: string }>(`/resume/history?created_at=${encodeURIComponent(created_at)}`, { method: "DELETE" }),
};

export interface User {
  user_id: string;
  email: string;
  telegram_chat_id: string | null;
  score_threshold: number;
  created_at: string;
}

export type SearchSource =
  | "linkedin"
  | "greenhouse"
  | "lever"
  | "ashby"
  | "workable"
  | "smartrecruiters"
  | "remoteok"
  | "workingnomads"
  | "remotive"
  | "arbeitnow"
  | "compujobs"
  | "onlinejobs"
  | "yc"
  | "multi_board";

export type Seniority = "" | "internship" | "entry" | "associate" | "mid" | "senior" | "staff" | "director" | "executive";

export interface Search {
  search_id: string;
  user_id: string;
  url: string;
  label: string;
  source: SearchSource;
  ats_slug: string;
  keywords: string;
  location_filter: string;
  job_title: string;
  seniority: Seniority;
  active: boolean;
  created_at: string;
}

export interface CreateSearchPayload {
  url?: string;
  label: string;
  source: SearchSource;
  ats_slug?: string;
  keywords?: string;
  location_filter?: string;
  job_title?: string;
  seniority?: Seniority;
}

export interface Profile {
  must_have: string[];
  nice_to_have: string[];
  deal_breakers: string[];
  prefer: string[];
  score_threshold: number;
  seniority: Seniority;
  eligible_regions: string[];
}

export type RegionScope = "worldwide" | "latam" | "restricted";

// Best-effort guess from the posting's own text (see shared/seniority.py's
// extract_company_size_hint) — never a verified employee count. Always
// surface it in the UI as an estimate, not a fact.
export type CompanySizeHint = "startup" | "midsize" | "enterprise";

// "linkedin" = LinkedIn's own self-reported employee-count range (from the
// company's About page, see scraper/linkedin.py's fetch_linkedin_company_size)
// — still an estimate/bucket, not an audited headcount, but more authoritative
// than "description" (a regex guess over the posting's own text).
export type CompanySizeSource = "linkedin" | "description";

export type InterviewStage =
  | "applied" | "phone" | "technical" | "onsite" | "offer"
  | "accepted" | "rejected" | "withdrawn";

export interface Interview {
  interview_id: string;
  user_id: string;
  company: string;
  role: string;
  stage: InterviewStage;
  scheduled_at: string | null;
  location: string | null;
  notes: string;
  job_id: string | null;
  job_score: number | null;
  job_url: string | null;
  created_at: string;
  updated_at: string;
}

export interface Job {
  job_id: string;
  title: string;
  company: string;
  location: string;
  url: string;
  description?: string;
  posted_date: string | null;
  seniority_level: Seniority | null;
  min_years_experience: number | null;
  region_scope: RegionScope | null;
  company_size_hint: CompanySizeHint | null;
  company_size_source: CompanySizeSource | null;
  company_size_raw: string | null;
  // Best-effort {years, context} pairs pulled from the posting's own text —
  // e.g. {years: 5, context: "Python"} — see shared/seniority.py's
  // extract_experience_mentions. Never a verified/confirmed requirement.
  experience_mentions: { years: number; context: string }[];
  score: number;
  summary: string;
  reasons: string[];
  deal_breaker: boolean;
  recommendation: "APPLY" | "MAYBE" | "SKIP";
  notified: boolean;
  timestamp: string;
  // Older rows saved before this feature existed never got `applied` set at
  // all — treat undefined/missing the same as false everywhere this is read.
  applied?: boolean;
  applied_at?: string | null;
  dismissed?: boolean;
  dismissed_at?: string | null;
}

export interface InterviewBriefSource {
  title: string;
  summary: string;
  published_at: string;
  source: string;
  url: string;
}

export interface InterviewBriefItem {
  term?: string;
  metric?: string;
  name?: string;
  why_it_matters?: string;
  basis?: string;
}

export interface InterviewBrief {
  company: string;
  role: string;
  generated_at: string;
  overview: string;
  industry_concepts: InterviewBriefItem[];
  metrics_to_know: InterviewBriefItem[];
  recent_trends: string[];
  recent_launches: { item: string; evidence: string }[];
  pain_points_addressed: string[];
  open_challenges: string[];
  competitors: InterviewBriefItem[];
  business_model: string;
  revenue_drivers: string[];
  positioning: string;
  interview_angles: string[];
  evidence_gaps: string[];
  sources: InterviewBriefSource[];
}

// ── Resume Builder ────────────────────────────────────────────────────────────

export interface ResumeExperience {
  title: string;
  company: string;
  location: string;
  start_date: string;
  end_date: string;
  bullets: string[];
}

export interface ResumeEducation {
  degree: string;
  school: string;
  location: string;
  year: string;
  gpa: string;
}

export interface ResumeProject {
  name: string;
  description: string;
  url: string;
  bullets: string[];
}

export interface ResumeSkills {
  languages: string[];
  frameworks: string[];
  tools: string[];
  other: string[];
}

export interface ResumeData {
  name: string;
  email: string;
  phone: string;
  location: string;
  linkedin: string;
  github: string;
  website: string;
  summary: string;
  experience: ResumeExperience[];
  education: ResumeEducation[];
  skills: ResumeSkills;
  projects: ResumeProject[];
  certifications: string[];
}

export type ResumeTemplate = "typst-modern" | "typst-silver" | "latex-us";

export interface CvHistoryEntry {
  user_id: string;
  created_at: string;
  company: string;
  role: string;
  template: ResumeTemplate;
  language: string;
  job_id: string;
}

export interface ResumeCheckSection {
  score: number;
  feedback: string;
  missing?: string[];
  suggestions?: string[];
  missing_keywords?: string[];
}

export interface ResumeCheckResult {
  overall_score: number;
  ats_score: number;
  sections: {
    skills_match: ResumeCheckSection;
    experience_relevance: ResumeCheckSection;
    impact_metrics: ResumeCheckSection;
    keywords: ResumeCheckSection;
  };
  top_strengths: string[];
  critical_gaps: string[];
  quick_wins: string[];
  summary: string;
}

export interface AtsCheckResult {
  ats_score: number;
  missing_keywords: string[];
  summary: string;
  structural_issues: string[];
}

export interface ExpandResult {
  suggested_skills: ResumeSkills;
  suggested_projects: (ResumeProject & { source?: string })[];
  notes: string;
}

export interface UpskillGap {
  skill: string;
  why: string;
  priority: "high" | "medium" | "low";
  resources: string[];
  estimated_hours: number;
}

export interface UpskillResult {
  gaps: UpskillGap[];
  summary: string;
}
