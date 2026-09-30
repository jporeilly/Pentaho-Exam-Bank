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
  courses: {
    path: string;
    configured: boolean;
    /** The Content Manager whose courses these are, from its package.json.
     *  Empty when it cannot be read. Optional: an older backend omits it. */
    contentManagerVersion?: string;
  };
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
  /** "course" = the order the workshops teach it (the pool's authored
   *  order); "updated" = most recently edited first. */
  sort?: "course" | "updated";
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

/** A page in the Documentation screen's list. `slug` is its repo-relative
 *  path without ".md" ("README", "docs/guides/02-courses"). */
export interface DocItem {
  slug: string;
  title: string;
  section: string;
  summary: string;
  words: number;
  path: string;
}

export interface DocIndex {
  sections: Array<{ name: string; items: DocItem[] }>;
  count: number;
}

/** A heading and the id links use for it. Ids are decided by the backend,
 *  once, by GitHub's rule; the screen matches each rendered heading to this
 *  list by its source `line` rather than slugging the text a second way. */
export interface DocHeading {
  level: number;
  text: string;
  id: string;
  line: number;
}

export interface DocPage extends DocItem {
  /** The markdown, less the page's own "# " title line. */
  content: string;
  headings: DocHeading[];
}

export interface DocHit {
  slug: string;
  page: string;
  section: string;
  heading: string;
  /** Where on the page the section starts; "" is the top. */
  anchor: string;
  snippet: string;
  score: number;
}

export interface DocSearchResult {
  query: string;
  /** How many sections were looked through. Lets an empty result read as
   *  "not in the docs" rather than "docs not loaded", which otherwise look
   *  identical. */
  sectionsSearched: number;
  results: DocHit[];
}

export interface ChatTurn {
  role: "user" | "assistant";
  content: string;
}

/** What an answer was built from. `A1…` are this app's pages and open in
 *  Documentation; `P1…` are docs.pentaho.com pages and open in the browser. */
export interface ChatSource {
  id: string;
  kind: "app" | "pentaho";
  title: string;
  heading: string;
  slug: string;
  anchor: string;
  url: string;
  snippet: string;
  /** Whether the answer cites it. One it was given and did not use is shown
   *  fainter. */
  cited: boolean;
}

export interface ChatGrounding {
  app: { searched: boolean; found: number };
  pentaho: {
    searched: boolean;
    found: number;
    host: string;
    ms?: number;
    /** Why the search failed; the answer went ahead without it. */
    error?: string;
    /** Why it was not searched at all. */
    reason?: string;
  };
}

/** One turn's answer. `answered` is false when neither source found
 *  anything — the model was then never called, because asked with nothing to
 *  read it answers from what it knows in general, which reads exactly like an
 *  answer from the documentation. */
export interface ChatAnswer {
  answered: boolean;
  answer: string;
  sources: ChatSource[];
  grounding: ChatGrounding;
  provider?: string;
  model?: string;
}

export interface DocsMcpStatus {
  enabled: boolean;
  url: string;
  ok: boolean;
  server: string;
  version: string;
  tools: string[];
  ms: number | null;
  /** Whether the tool AI Chat calls is among the server's tools. */
  searchTool: boolean;
  error: string;
}

export interface BackupFile {
  name: string;
  sizeKb: number;
  created: string;
}

export interface DatabaseStatus {
  database: {
    exists: boolean;
    path: string;
    questions?: number;
    certifications?: number;
    size_kb?: number;
  };
  backups: BackupFile[];
}

/** What a bulk deletion would remove.
 *
 *  `everything` is true when no filter narrows the set — the server refuses
 *  that unless it is asked for explicitly, because an empty filter is far
 *  more often a cleared one than a request to empty the bank. */
export interface DeletionPlan {
  total: number;
  everything: boolean;
  byStatus: Record<string, number>;
  byCertification: Array<{ id: string; name: string; count: number }>;
  /** A few stems, so the set is recognisable rather than just a number. */
  sample: string[];
}

export interface DeletionFilters {
  status?: string;
  topic?: string;
  certification_id?: string;
  difficulty?: string;
  bloom_level?: string;
}

/** The settings an author may change. Deliberately not the whole config:
 *  the app also stores state it manages for itself, and the server refuses
 *  to write anything outside this set. */
export interface Settings {
  sme_name: string;
  ai_provider: string;
  anthropic_model: string;
  openai_model: string;
  ollama_url: string;
  ollama_model: string;
  ollama_enabled: boolean;
  ollama_num_ctx: number;
  docs_mcp_enabled: boolean;
  docs_mcp_url: string;
  pcm_courses_dir: string;
  output_folder: string;
  duplicate_threshold: number;
  validation_threshold: number;
  questions_per_page: number;
  default_difficulty: string;
  default_bloom_level: string;
  auto_export_on_save: boolean;
  default_export_format: string;
  auto_backup_enabled: boolean;
  auto_backup_interval_hours: number;
  auto_backup_max_count: number;
}

export interface SettingsResponse {
  settings: Settings;
  /** Whether each provider's key is present in the environment. Booleans
   *  only — this app has never stored a key and never sends one. */
  providerKeys: Record<string, boolean>;
  /** Fields an environment variable governs. Changing one here does not
   *  last: it is saved and then overridden again on the next start. */
  envOverridden: string[];
  envNames: Record<string, string>;
  choices: {
    providers: string[];
    difficulties: string[];
    bloomLevels: string[];
    pageSizes: number[];
    exportFormats: { format: string; label: string }[];
  };
  paths: { database: string; config: string };
  /** Where auto-export writes now, and what it last did. */
  autoExport: { target: string; at: string; path: string; count: number; error: string };
  /** What the last automatic backup did. */
  autoBackup: { at: string; path: string; pruned: number; error: string };
}

/** One topic's share of a weighted exam: what it was owed, what it had, and
 *  what it ended up contributing. */
export interface TopicOutcome {
  topic: string;
  weight: number;
  wanted: number;
  available: number;
  selected: number;
  /** Questions it could not supply. */
  short: number;
  /** Questions it supplied on another topic's behalf. */
  lent: number;
}

/** What the paper would actually contain.
 *
 *  `honoured` is the one an author needs: the selection redistributes
 *  silently, so a 40/30/30 exam can come back 40/45/15 and the only place
 *  that is visible is here, before it is printed. */
export interface ExamPlan {
  requested: number;
  selected: number;
  shortfall: number;
  redistributed: number;
  honoured: boolean;
  topics: TopicOutcome[];
}

export interface ExamTopic {
  topic: string;
  questionCount: number;
}

/** The shape of the paper, before the bank has had a say in it. */
export interface ExamRequest {
  certification_ids: string[];
  total_questions: number;
  topic_weights: Record<string, number>;
  difficulties?: string[];
  statuses?: string[];
  randomize?: boolean;
  seed?: number | null;
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
  /** On a plan: whether the exam could also be pushed to the courses repo
   *  installed apps sync from, and to which course version; if not, why. */
  push?: PushPreview;
  /** On a write made with push: what happened at each stage. */
  pushed?: PushResult;
}

export interface PushPreview {
  available: boolean;
  reason?: string;
  versionFrom?: string;
  versionTo?: string;
  coursesRepo?: string;
}

export interface PushResult {
  versionFrom?: string;
  versionTo?: string;
  coursesRepo?: string;
  changelog?: string;
  authoring?: { commit?: string; pushed?: boolean };
  courses?: { commit?: string; pushed?: boolean; upToDate?: boolean };
  /** Set when a stage failed; the exam file is written either way. */
  error?: string;
  failedAt?: string;
}

// ── Calls ───────────────────────────────────────────────────────────

/** One course in a sync plan. */
export interface SyncCourse {
  slug: string;
  title: string;
  examSha: string;
  certificationId: string;
  certificationName: string;
  adopted: boolean;
  inCourse: number;
  new: number;
  changed: number;
  unchanged: number;
  unusable: { id: string; stem: string; reason: string }[];
  /** Ids another course also claims. Refused, never written. */
  conflicts: { id: string; stem: string; reason: string }[];
  changedIds: string[];
  error: string;
}

/** What adopting every course would do to the bank. */
export interface SyncPlan {
  coursesDir: string;
  token: string;
  courses: SyncCourse[];
  totalNew: number;
  totalChanged: number;
  totalUnchanged: number;
  totalUnusable: number;
  totalConflicts: number;
}

export interface SyncResult {
  added: number;
  updated: number;
  skippedChanged: number;
  courses: { slug: string; added: number; updated: number; skipped: number }[];
  token: string;
}

/** One thing an AI reviewer says is wrong. */
export interface AiFinding {
  field: string;
  value: string;
  issue: string;
  severity: "error" | "warning";
}

/** What `/ai/review` reports. Answer faults are kept apart from
 *  proofreading: "the key is also true of option C" and "a comma is
 *  missing" are not the same kind of news. */
export interface AiReview {
  answers: AiFinding[];
  prose: AiFinding[];
  /** The bank's own deterministic validator, which owes nothing to a
   *  model and is worth showing beside its opinion. */
  gradeable: { field: string; message: string }[];
  /** Where the question breaks the house form (core/stem_text.py): a
   *  question in the scenario, statements or a count in the stem. */
  form?: { field: string; message: string }[];
}

/** The bank's fixed lists, as the server validates them. */
export interface Vocabulary {
  statuses: string[];
  statusLabels: Record<string, string>;
  difficulties: string[];
  bloomLevels: string[];
}

/** A proposed explanation. `unnamed` are options it never names. */
export interface AiExplanation {
  explanation: string;
  /** The course page it was grounded on, or "" when there was none. */
  groundedOn: string;
  unnamed: string[];
}

/** A proposed answer key: which options are correct, by their text. */
export interface AiAnswer {
  proposed: Question;
  changed: boolean;
  analysis: { option: string; correct: boolean; quote: string }[];
  groundedOn: string;
}

export interface AiRewrite {
  proposed: Question;
  problems: { field: string; message: string }[];
  /** The same form notes, for the proposal: a model can ignore the rule. */
  notes?: { field: string; message: string }[];
  unchanged: boolean;
}

/** Counts for one set of questions — the bank, an exam, or a workshop.
 *  Every Bloom level and status is present, zero or not. */
export interface ReportSummary {
  questions: number;
  byBloom: Record<string, number>;
  /** Questions whose level is not one the bank recognises. In the total,
   *  in no bar. */
  unknownBloom: number;
  applyPlus: number;
  analyzePlus: number;
  recall: number;
  evaluate: number;
  scenarioLed: number;
  multi: number;
  thin: number;
  byStatus: Record<string, number>;
}

export interface ReportCriterion {
  criterion: string;
  kind: "floor" | "ceiling";
  got: number;
  percent: number;
  bar: number;
  ok: boolean;
  /** How many questions short of a floor, or over a ceiling. */
  gap: number;
}

export interface ReportBar {
  level: number;
  name: string;
  criteria: ReportCriterion[];
  clears: boolean;
}

export interface ReportFinding {
  severity: "act" | "review" | "minor" | "note" | "clear";
  title: string;
  detail: string;
  action: string;
}

export interface ReportTopic extends ReportSummary {
  topic: string;
}

export interface ReportExam extends ReportSummary {
  certificationId: string;
  name: string;
  sourceRef: string;
  /** From the course's course.json. Null when it states none (a try-it lab)
   *  or no courses directory is configured. */
  level: { number: number; name: string } | null;
  /** From the course's exam.json. */
  exam: { pool: number; draw: number; passMark: number | null } | null;
  bar: ReportBar | null;
  findings: ReportFinding[];
  topics: ReportTopic[];
}

export interface ReportItem {
  id: string;
  certificationId: string;
  topic: string;
  bloom: string;
  status: string;
  scenario: boolean;
  multi: boolean;
  stem: string;
  poolOrder: number;
}

export interface Report extends ReportSummary {
  levels: string[];
  statuses: { id: string; label: string }[];
  coursesConfigured: boolean;
  exams: ReportExam[];
  /** Certifications holding no questions. */
  emptyCourses: number;
  /** Every question, in course order. */
  items: ReportItem[];
}

export const api = {
  health: () => request<Health>("/api/health"),
  stats: () => request<Record<string, unknown>>("/api/stats"),
  report: () => request<Report>("/api/report"),

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
  vocabulary: () => request<Vocabulary>("/api/vocabulary"),

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
    request<{ saved: number; refused?: { stem: string; reason: string }[] }>(
      `/api/jobs/${encodeURIComponent(id)}/commit`, {
      method: "POST",
      body: JSON.stringify({ question_ids, certification_id }),
    }),

  docsIndex: () => request<DocIndex>("/api/docs"),
  docsPage: (slug: string) => request<DocPage>(`/api/docs/page${query({ slug })}`),
  searchDocs: (q: string, limit = 20) =>
    request<DocSearchResult>(`/api/docs/search${query({ q, limit })}`),

  chat: (
    messages: ChatTurn[],
    sources: { appDocs: boolean; pentahoDocs: boolean },
    signal?: AbortSignal,
  ) =>
    request<ChatAnswer>("/api/chat", {
      method: "POST",
      body: JSON.stringify({ messages, ...sources }),
      signal,
    }),
  docsMcpStatus: (url = "") => request<DocsMcpStatus>(`/api/docs-mcp/status${query({ url })}`),
  /** Opens a docs.pentaho.com page in the system browser. The window has no
   *  way to do it itself: it is a webview without Tauri's APIs, where a
   *  target="_blank" link goes nowhere. */
  openUrl: (url: string) =>
    request<void>("/api/open-url", { method: "POST", body: JSON.stringify({ url }) }),

  databaseStatus: () => request<DatabaseStatus>("/api/admin/database"),
  createBackup: (label = "") =>
    request<{ name: string; backups: BackupFile[] }>("/api/admin/backups", {
      method: "POST",
      body: JSON.stringify({ label }),
    }),
  /** Replace the live database. The current one is backed up first and that
   *  backup's name comes back, so the restore itself can be undone. */
  restoreBackup: (name: string) =>
    request<{ restored: string; safetyBackup: string } & DatabaseStatus>(
      `/api/admin/backups/${encodeURIComponent(name)}/restore`,
      { method: "POST" },
    ),
  deleteBackup: (name: string) =>
    request<{ deleted: string; backups: BackupFile[] }>(
      `/api/admin/backups/${encodeURIComponent(name)}`,
      { method: "DELETE" },
    ),

  /** What a bulk deletion would remove. Deletes nothing. */
  previewDeletion: (filters: DeletionFilters) =>
    request<DeletionPlan>("/api/admin/questions/delete/preview", {
      method: "POST",
      body: JSON.stringify(filters),
    }),
  /** `expect_count` comes from the preview: a mismatch means the bank changed
   *  in between, and the server refuses rather than deleting a different set. */
  deleteQuestions: (
    filters: DeletionFilters,
    expect_count: number,
    everything = false,
  ) =>
    request<{ deleted: number }>("/api/admin/questions/delete", {
      method: "POST",
      body: JSON.stringify({ ...filters, expect_count, everything }),
    }),

  settings: () => request<SettingsResponse>("/api/settings"),
  /** Change the named settings. Anything not sent is left alone, and one bad
   *  value changes none of the others. */
  saveSettings: (settings: Partial<Settings>) =>
    request<SettingsResponse>("/api/settings", {
      method: "PUT",
      body: JSON.stringify({ settings }),
    }),

  /** Topics with questions, for the certifications being drawn from. */
  examTopics: (certification_ids: string[], statuses = "approved") =>
    request<ExamTopic[]>(
      `/api/exam/topics${query({
        certification_ids: certification_ids.join(","),
        statuses,
      })}`,
    ),
  /** What the paper would contain. Builds no PDF. */
  planExam: (body: ExamRequest) =>
    request<ExamPlan>("/api/exam/plan", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  /** The printable paper.
   *
   *  Fetched here rather than pointed at with a link, because the request is
   *  a POST carrying a weighting that does not fit in a URL — and because a
   *  failure has to surface as the server's message rather than as a browser
   *  tab showing raw JSON. */
  examPdf: async (body: ExamRequest & Record<string, unknown>): Promise<Blob> => {
    const response = await fetch(`${BASE}/api/exam/pdf`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }).catch(() => {
      throw new ApiError(0, "Can't reach the Exam Bank API. Is it running?");
    });
    if (!response.ok) {
      let detail = `${response.status} ${response.statusText}`;
      try {
        const parsed = await response.json();
        if (typeof parsed?.detail === "string") detail = parsed.detail;
      } catch {
        /* a non-JSON error body leaves the status line as the message */
      }
      throw new ApiError(response.status, detail);
    }
    return response.blob();
  },

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
    push = false,
  ) =>
    request<PublishPlan & { push?: PushResult }>(
      `/api/courses/${encodeURIComponent(slug)}/exam/questions`,
      {
        method: "POST",
        body: JSON.stringify({ certification_id, status, expect_sha, push }),
      },
    ).then((r) => ({ ...r, pushed: push ? (r.push as PushResult | undefined) : undefined })),

    /** What adopting every course's exam would do to the bank. Writes nothing. */
  planCourseSync: () => request<SyncPlan>("/api/courses/sync/plan", { method: "POST" }),
  /** Adopt what the plan described. `token` comes from the plan, and the
   *  server refuses without it - so this cannot be called first. */
  syncCourses: (token: string, overwrite_changed = false, only: string[] = []) =>
    request<SyncResult>("/api/courses/sync", {
      method: "POST",
      body: JSON.stringify({ token, overwrite_changed, only }),
    }),

  /** Propose a rewritten question. Writes nothing - the author accepts by
   *  saving, the same way any other edit is accepted. */
  aiRewrite: (id: string, instruction = "") =>
    request<AiRewrite>(`/api/questions/${encodeURIComponent(id)}/ai/rewrite`, {
      method: "POST",
      body: JSON.stringify({ instruction }),
    }),
  /** Check the answers, and proofread. Writes nothing. */
  aiReview: (id: string) =>
    request<AiReview>(`/api/questions/${encodeURIComponent(id)}/ai/review`, {
      method: "POST",
    }),
  /** Propose the explanation, from the course's pages. Writes nothing. */
  aiExplanation: (id: string) =>
    request<AiExplanation>(`/api/questions/${encodeURIComponent(id)}/ai/explanation`, {
      method: "POST",
    }),
  /** Propose which options are correct, from the course's pages. Writes nothing. */
  aiAnswer: (id: string) =>
    request<AiAnswer>(`/api/questions/${encodeURIComponent(id)}/ai/answer`, {
      method: "POST",
    }),

  /** Export is a file download, so it is a URL the browser fetches, not JSON. */
  exportUrl: (format: string, filters: QuestionFilters = {}) =>
    `${BASE}/api/export/${format}${query({ ...filters })}`,
};
