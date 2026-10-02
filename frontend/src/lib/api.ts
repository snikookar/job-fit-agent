// Typed client for the FastAPI backend. Types mirror backend/jobfit/schemas.py.

export const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export type Importance = "must" | "nice";

export interface Requirement {
  id: string;
  text: string;
  category: "skill" | "experience" | "education" | "language" | "location" | "other";
  importance: Importance;
  years: number | null;
}

export interface JobRequirements {
  title: string;
  company: string | null;
  location: string | null;
  remote: "onsite" | "hybrid" | "remote" | "unknown";
  visa_sponsorship: "yes" | "no" | "unknown";
  requirements: Requirement[];
}

export interface Chunk {
  id: string;
  source: string;
  section: string;
  text: string;
  date_range: string | null;
  tech_tags: string[];
}

export interface Evidence {
  requirement_id: string;
  chunk_id: string;
  quote: string;
  strength: number;
  retrieval_score: number;
  assessment: "full" | "partial" | "none" | null;
}

export interface RequirementScore {
  requirement_id: string;
  text: string;
  importance: Importance;
  weight: number;
  strength: number;
  contribution: number;
}

export interface ScoreBreakdown {
  score: number;
  must_coverage: number;
  items: RequirementScore[];
}

export interface Gap {
  requirement_id: string;
  text: string;
  importance: Importance;
  best_strength: number;
  suggestion: string;
}

export interface DraftSentence {
  text: string;
  evidence_ids: string[];
}

export interface Draft {
  bullets: DraftSentence[];
  cover_letter: DraftSentence[];
}

export type Section = "bullets" | "cover_letter";

export interface Verdict {
  section: Section;
  index: number;
  text: string;
  evidence_ids: string[];
  supported: boolean;
  p_supported: number;
  reason: string;
  checks: string[];
  edited_by_user?: boolean;
}

export interface TraceEntry {
  node: string;
  seconds: number;
  llm_calls: number;
  tokens: number;
}

export interface JobState {
  run_id?: string;
  job_url?: string | null;
  job_text?: string;
  job_source?: string;
  language?: string;
  requirements?: JobRequirements;
  evidence?: Record<string, Evidence[]>;
  score?: ScoreBreakdown;
  gaps?: Gap[];
  draft?: Draft;
  verdicts?: Verdict[];
  revision?: number;
  removed?: Verdict[];
  final_draft?: Draft;
  final_verdicts?: Verdict[];
  approved?: boolean;
  docx_path?: string;
  application_id?: number;
  trace?: TraceEntry[];
  next?: string[];
  awaiting_review?: boolean;
}

export type RunStatus = "running" | "awaiting_review" | "done" | "failed";

export interface RunRow {
  run_id: string;
  job_url: string | null;
  title: string | null;
  company: string | null;
  status: RunStatus;
  score: number | null;
  error: string | null;
  created_at: string | null;
}

export interface JobResponse {
  run: RunRow;
  state: JobState;
  chunks: Record<string, Chunk>;
  active: boolean;
}

export interface RunEvent {
  type: "node" | "interrupt" | "done" | "error";
  node: string | null;
  data: Record<string, unknown>;
  seq: number;
}

export interface Application {
  id: number;
  run_thread_id: string | null;
  title: string;
  company: string | null;
  url: string | null;
  location: string | null;
  status: string;
  score: number | null;
  has_docx: boolean;
  notes: string | null;
  created_at: string | null;
  updated_at: string | null;
}

export interface Health {
  status: string;
  writer: string;
  judge: string;
  embedder: string;
  reranker: string;
  database: string;
  offline_mode: boolean;
}

export interface ProfileSummary {
  info: Record<string, string>;
  sources: { source: string; chunks: number }[];
  total_chunks: number;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_URL}${path}`, init);
  if (!res.ok) {
    let message = `${res.status} ${res.statusText}`;
    try {
      const body = await res.json();
      if (typeof body.detail === "string") message = body.detail;
      else if (Array.isArray(body.detail)) message = body.detail.map((d: { msg: string }) => d.msg).join("; ");
    } catch {
      /* not JSON */
    }
    throw new Error(message);
  }
  return res.json() as Promise<T>;
}

const json = (method: string, body: unknown): RequestInit => ({
  method,
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(body),
});

export const api = {
  health: () => request<Health>("/api/health"),

  profile: () => request<ProfileSummary>("/api/profile"),
  chunks: (source?: string) =>
    request<Chunk[]>(`/api/profile/chunks${source ? `?source=${encodeURIComponent(source)}` : ""}`),
  uploadResume: (file: File) => {
    const form = new FormData();
    form.append("file", file);
    return request<{ source: string; chunks: number }>("/api/profile/resume", { method: "POST", body: form });
  },
  uploadProjects: (files: File[]) => {
    const form = new FormData();
    files.forEach((f) => form.append("files", f));
    return request<{ source: string; chunks: number }[]>("/api/profile/projects", { method: "POST", body: form });
  },
  connectGitHub: (target: string) =>
    request<{ source: string; chunks: number }[]>("/api/profile/github", json("POST", { target })),
  loadSample: () => request<{ source: string; chunks: number }[]>("/api/profile/sample", { method: "POST" }),
  setInfo: (info: Record<string, string>) => request<Record<string, string>>("/api/profile/info", json("PUT", info)),
  deleteSource: (source: string) =>
    request(`/api/profile/sources/${encodeURIComponent(source)}`, { method: "DELETE" }),
  deleteProfile: () => request("/api/profile", { method: "DELETE" }),

  startJob: (input: { url?: string; text?: string }) => request<{ run_id: string }>("/api/jobs", json("POST", input)),
  jobs: () => request<RunRow[]>("/api/jobs"),
  job: (runId: string) => request<JobResponse>(`/api/jobs/${runId}`),
  check: (runId: string, draft: Draft) => request<Verdict[]>(`/api/jobs/${runId}/check`, json("POST", { draft })),
  review: (runId: string, decision: { approved: boolean; draft?: Draft; keep_unsupported_edits?: boolean; note?: string }) =>
    request(`/api/jobs/${runId}/review`, json("POST", decision)),
  docxUrl: (runId: string) => `${API_URL}/api/jobs/${runId}/docx`,
  eventsUrl: (runId: string, after: number) => `${API_URL}/api/jobs/${runId}/events?after=${after}`,

  tracker: () => request<{ statuses: string[]; applications: Application[] }>("/api/tracker"),
  addApplication: (body: { title: string; company?: string; url?: string }) =>
    request<Application>("/api/tracker", json("POST", body)),
  updateApplication: (id: number, body: { status?: string; notes?: string }) =>
    request<Application>(`/api/tracker/${id}`, json("PATCH", body)),
  deleteApplication: (id: number) => request(`/api/tracker/${id}`, { method: "DELETE" }),
  applicationDocxUrl: (id: number) => `${API_URL}/api/tracker/${id}/docx`,
};

export const NODE_LABELS: Record<string, string> = {
  fetch_job: "Fetch posting",
  parse_requirements: "Extract requirements",
  match_evidence: "Find evidence",
  score: "Score fit",
  gap_analysis: "Analyze gaps",
  writer: "Write draft",
  grounding_judge: "Fact-check",
  human_review: "Your review",
  export: "Export .docx",
};
