/**
 * The HTTP client for the Python backend.
 *
 * Every call goes through `request`, which turns a failure into an `ApiError`
 * carrying the message the server sent. The API is deliberate about those
 * messages — an unknown course names the ones that exist, a certification that
 * still holds questions says how many would be orphaned — so showing the
 * server's text is almost always better than anything invented here.
 */

const BASE = import.meta.env.VITE_API_BASE ?? "";

export class ApiError extends Error {
  constructor(
    readonly status: number,
    message: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${BASE}${path}`, {
      ...init,
      headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
    });
  } catch {
    // A refused connection is the usual case here and has one cause worth
    // naming: the backend is not running.
    throw new ApiError(0, "Can't reach the Question Bank API. Is it running?");
  }
  if (!response.ok) {
    let detail = `${response.status} ${response.statusText}`;
    try {
      const body = await response.json();
      if (typeof body?.detail === "string") detail = body.detail;
    } catch {
      /* a non-JSON error body leaves the status line as the message */
    }
    throw new ApiError(response.status, detail);
  }
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

function query(params: Record<string, string | number | boolean | undefined>): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value === undefined || value === "") continue;
    search.set(key, String(value));
  }
  const text = search.toString();
  return text ? `?${text}` : "";
}

// ── Shapes ──────────────────────────────────────────────────────────

/** What the app was opened for, when something launched it with a course in
 *  mind (the Content Editor's Questions button). Both parts are hints. */
export interface LaunchContext {
  /** The requested course slug; "" when nothing was handed over. */
  course: string;
  /** Whether that slug resolves against the courses directory right now. */
  courseKnown: boolean;
  courseTitle: string;
  /** Present only when the handed-over checkout is not the configured one. */
  repoDisagreement: { handedOver: string; configured: string; using: string } | null;
}

export interface Health {
  version: string;
  database: { path: string; exists: boolean; questions: number; certifications: number };
  provider: { provider: string; ok: boolean; model: string; detail: string; models?: string[] };
  courses: { path: string; configured: boolean };
  launch: LaunchContext;
}

export interface Question {
  id: string;
  scenario: string;
  stem: string;
  question_type: "single" | "multi";
  key: string;
  keys: string[];
  key_source_text: string;
  distractors: string[];
  option_order: string[];
  explanation: string;
  topic: string;
  tags: string[];
  difficulty: string;
  bloom_level: string;
  certification_id: string;
  /** Position in the course pool this came from; -1 when generated. */
  pool_order: number;
  status: string;
  assigned_sme: string;
  review_history: Array<Record<string, string>>;
  version_history: Array<Record<string, string>>;
  updated_at: string;
}

export interface QuestionPage {
  items: Question[];
  total: number;
  limit: number;
  offset: number;
}

export interface Certification {
  id: string;
  name: string;
  description: string;
  sourceType: string;
  sourceRef: string;
  questionCount: number;
}

export interface Course {
  slug: string;
  title: string;
  hasExam: boolean;
  questionCount: number;
}

export interface Lab {
  slug: string;
  title: string;
}

export interface Section {
  index: number;
  title: string | null;
  characters: number;
  /** True when this section is longer than the model can read in one go.
   *  Ollama truncates silently, so the author has to be told. */
  exceedsContext: boolean;
  preview: string;
}

/** What the configured model can actually take in. `chars` is 0 when no
 *  context window is configured, in which case nothing is flagged. */
export interface ContextBudget {
  chars: number;
  numCtx: number;
  model: string;
}

export interface CourseSections {
  budget: ContextBudget;
  sections: Section[];
}

export interface Job {
  id: string;
  kind: string;
  status: "running" | "done" | "error" | "cancelled";
  progress: { current: number; total: number; message: string };
  count: number;
  result: Question[];
  error: string;
}

export interface QuestionFilters {
  text?: string;
  topic?: string;
  difficulty?: string;
  bloom_level?: string;
  status?: string;
  certification_id?: string;
  assigned_sme?: string;
  tags?: string;
  limit?: number;
  offset?: number;
}

export interface GenerateRequest {
  course_slug: string;
  lab_slug?: string;
  certification_id?: string;
  total?: number;
  difficulty?: string;
  bloom_levels?: string[];
  num_keys?: number;
  num_distractors?: number;
  custom_instructions?: string;
  shuffle_formats?: boolean;
  model?: string;
}

// ── Calls ───────────────────────────────────────────────────────────

export const api = {
  health: () => request<Health>("/api/health"),
  stats: () => request<Record<string, unknown>>("/api/stats"),

  questions: (filters: QuestionFilters = {}) =>
    request<QuestionPage>(`/api/questions${query({ ...filters })}`),
  question: (id: string) => request<Question>(`/api/questions/${encodeURIComponent(id)}`),
  updateQuestion: (id: string, changes: Partial<Question> & { editor?: string }) =>
    request<Question>(`/api/questions/${encodeURIComponent(id)}`, {
      method: "PUT",
      body: JSON.stringify(changes),
    }),
  setStatus: (id: string, status: string, sme_name = "", comment = "") =>
    request<Question>(`/api/questions/${encodeURIComponent(id)}/status`, {
      method: "POST",
      body: JSON.stringify({ status, sme_name, comment }),
    }),
  deleteQuestion: (id: string) =>
    request<{ ok: boolean }>(`/api/questions/${encodeURIComponent(id)}`, { method: "DELETE" }),

  certifications: () => request<Certification[]>("/api/certifications"),

  courses: () => request<Course[]>("/api/courses"),
  labs: (slug: string) => request<Lab[]>(`/api/courses/${encodeURIComponent(slug)}/labs`),
  sections: (slug: string, lab = "") =>
    request<CourseSections>(`/api/courses/${encodeURIComponent(slug)}/sections${query({ lab })}`),

  generate: (body: GenerateRequest) =>
    request<{ jobId: string; sections: number }>("/api/generate", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  /** Every job, without results — a status list, not a payload. */
  jobs: () => request<Job[]>("/api/jobs"),
  job: (id: string) => request<Job>(`/api/jobs/${encodeURIComponent(id)}`),
  cancelJob: (id: string) =>
    request<{ ok: boolean }>(`/api/jobs/${encodeURIComponent(id)}/cancel`, { method: "POST" }),
  commitJob: (id: string, question_ids: string[] = [], certification_id = "") =>
    request<{ saved: number }>(`/api/jobs/${encodeURIComponent(id)}/commit`, {
      method: "POST",
      body: JSON.stringify({ question_ids, certification_id }),
    }),

  /** Export is a file download, so it is a URL the browser fetches, not JSON. */
  exportUrl: (format: string, filters: QuestionFilters = {}) =>
    `${BASE}/api/export/${format}${query({ ...filters })}`,
};
