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
  // A FormData body must carry its own multipart Content-Type, including the
  // boundary the browser generates. Setting application/json over it produces
  // a request the server cannot parse and a 422 that names a missing field
  // rather than the wrong header, so the default is skipped rather than
  // overridden — an override merged from `init.headers` could not remove it.
  const isForm = typeof FormData !== "undefined" && init?.body instanceof FormData;
  try {
    response = await fetch(`${BASE}${path}`, {
      ...init,
      headers: isForm
        ? { ...(init?.headers ?? {}) }
        : { "Content-Type": "application/json", ...(init?.headers ?? {}) },
    });
  } catch {
    // A refused connection is the usual case here and has one cause worth
    // naming: the backend is not running.
    throw new ApiError(0, "Can't reach the Exam Bank API. Is it running?");
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

/** The question lifecycle, as core/bank.py defines it.
 *
 * Fetched rather than restated here: STATUS_TRANSITIONS is enforced by
 * Question.transition, and a second copy in the UI would offer moves the
 * model refuses - a 409 arriving from a button that should not exist.
 */
export interface Lifecycle {
  statuses: string[];
  transitions: Record<string, string[]>;
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
  /** Course furniture — how to use the guide, checking the environment.
   *  Skipped when generating from a whole course; picked deliberately, it
   *  is still read. */
  frontMatter: boolean;
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
  /** How many were asked for, so the UI can say "7 of 12". */
  requested: number;
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

/** One question shape: how many answers are right, and how many wrong. */
export interface QuestionFormat {
  keys: number;
  distractors: number;
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
  /** Shapes to cycle through. Empty means every question takes the same one. */
  formats?: QuestionFormat[];
  custom_instructions?: string;
  shuffle_formats?: boolean;
  model?: string;
}

/** A field-level problem with a question: what stops it being gradeable.
 *
 *  Defined once here because both halves of the app produce these. The editor
 *  computes them in the browser while an author types (`problemsWith`); import
 *  gets them from the server, computed by `core/validation.py`. Both are held
 *  to `tests/fixtures/question_problems.json`, so the messages are identical
 *  wherever they appear. */
export interface Problem {
  field: string;
  message: string;
}

/** One question read out of an uploaded file, with everything known against
 *  it: whether it can be graded, and whether the bank already has it. */
export interface ImportedQuestion {
  question: Question;
  problems: Problem[];
  duplicate_of: string;
  duplicate_stem: string;
  duplicate_score: number;
}

/** What a file turned out to hold. Nothing has been saved at this point. */
export interface ImportPreview {
  filename: string;
  format: string;
  formatLabel: string;
  /** Something true about this format that changes what the author must do
   *  next — the plain-text reader guessing a key from position, most of all.
   *  Empty for formats that carry everything a question needs. */
  formatNote: string;
  count: number;
  gradeable: number;
  duplicates: number;
  questions: ImportedQuestion[];
}

export interface ImportResult {
  saved: number;
  ids: string[];
  refused: Array<{ stem: string; reason: string }>;
}

/** One question that exists in both the bank and the course, but differs. */
export interface QuestionChange {
  id: string;
  fields: string[];
}

/** What publishing would do to a course's exam.json — or, after a write,
 *  what it did. The server computes this; nothing here is inferred. */
export interface PublishPlan {
  courseId: string;
  path: string;
  /** The hash of the file this plan was made against. Passed back on the
   *  write, so a publish cannot land on a file somebody else has since
   *  saved — the Content Editor writes this same file in whole. */
  sourceSha: string;
  isNoop: boolean;
  beforeCount: number;
  afterCount: number;
  added: string[];
  removed: string[];
  changed: QuestionChange[];
  unchanged: number;
  reordered: boolean;
  /** Key NAMES the merge left alone. Several hold credentials, so the server
   *  sends names only — the point is to show they survived. */
  preservedKeys: string[];
  /** Both empty unless the description's pool-size numeral has to move. The
   *  Content Manager's build check fails when the prose misstates the pool,
   *  so this is the one piece of authored text a publish may touch. */
  descriptionBefore: string;
  descriptionAfter: string;
  written?: boolean;
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

  lifecycle: () => request<Lifecycle>("/api/lifecycle"),

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

  /** Parse an uploaded file and report what is in it. Writes nothing.
   *
   *  No Content-Type is set: the browser has to supply the multipart boundary
   *  itself, and `request` would otherwise force application/json and the
   *  upload would arrive unparseable. */
  previewImport: (file: File) => {
    const form = new FormData();
    form.append("file", file);
    return request<ImportPreview>("/api/import/preview", {
      method: "POST",
      body: form,
    });
  },
  /** Save the chosen questions. They land as drafts whatever the file said. */
  commitImport: (
    questions: Question[],
    certification_id = "",
    topic = "",
  ) =>
    request<ImportResult>("/api/import/commit", {
      method: "POST",
      body: JSON.stringify({ questions, certification_id, topic }),
    }),

  /** What publishing would change in the course's exam.json. Writes nothing. */
  planPublish: (slug: string, certification_id: string, status = "approved") =>
    request<PublishPlan>(
      `/api/courses/${encodeURIComponent(slug)}/exam/questions/plan`,
      { method: "POST", body: JSON.stringify({ certification_id, status }) },
    ),
  /** Replace the course's questions. `expect_sha` comes from a plan, and the
   *  server refuses the write without it — so this cannot be called first. */
  publish: (
    slug: string,
    certification_id: string,
    expect_sha: string,
    status = "approved",
  ) =>
    request<PublishPlan>(`/api/courses/${encodeURIComponent(slug)}/exam/questions`, {
      method: "POST",
      body: JSON.stringify({ certification_id, status, expect_sha }),
    }),

  /** Export is a file download, so it is a URL the browser fetches, not JSON. */
  exportUrl: (format: string, filters: QuestionFilters = {}) =>
    `${BASE}/api/export/${format}${query({ ...filters })}`,
};
