import { useEffect, useRef, useState } from "react";

import {
  api,
  ApiError,
  type Certification,
  type Course,
  type GenerateRequest,
  type Job,
  type Lab,
  type Question,
  type QuestionFormat,
} from "./api";

// The backend owns these and validates against them, naming the valid set in
// its error, so drift shows up as a readable message rather than silently.
const DIFFICULTIES = ["Easy", "Medium", "Hard"];
const BLOOM_LEVELS = ["Remember", "Understand", "Apply", "Analyze", "Evaluate", "Create"];

const POLL_MS = 900;

// Mirrors the backend's _num_word, which spells these out in the stem.
const NUMBER_WORDS: Record<number, string> = { 1: "one", 2: "two", 3: "three", 4: "four" };

/** What a format row holds while it is being edited. The author thinks in
 *  TOTAL options; the API takes the wrong ones, so the conversion happens
 *  once, on send, rather than on every keystroke. */
interface FormatRow {
  keys: number;
  total: number;
}

function toRequestFormats(rows: FormatRow[]): QuestionFormat[] {
  return rows
    .map((r) => ({ keys: r.keys, distractors: r.total - r.keys }))
    .filter((f) => f.keys >= 1 && f.distractors >= 1);
}

/**
 * Generate questions from a course, then keep the ones worth keeping.
 *
 * Generating and saving are deliberately separate steps. A model's output is
 * a proposal: the job holds its questions until they have been looked at, and
 * generating a hundred must not put a hundred in the bank.
 */
export function GeneratePane({
  initialCourse = "",
  onCommitted,
}: {
  /** A course slug the app was opened for; chosen before anything is picked. */
  initialCourse?: string;
  onCommitted?: () => void;
}) {
  const [courses, setCourses] = useState<Course[]>([]);
  const [labs, setLabs] = useState<Lab[]>([]);
  const [certifications, setCertifications] = useState<Certification[]>([]);

  const [form, setForm] = useState<GenerateRequest>({
    course_slug: initialCourse,
    lab_slug: "",
    certification_id: "",
    total: 20,
    difficulty: "Medium",
    bloom_levels: ["Apply"],
    num_keys: 1,
    num_distractors: 3,
    custom_instructions: "",
    shuffle_formats: false,
  });

  const [formatRows, setFormatRows] = useState<FormatRow[]>([]);
  const [job, setJob] = useState<Job | null>(null);
  const [jobId, setJobId] = useState("");
  const [keep, setKeep] = useState<Set<string>>(new Set());
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [saved, setSaved] = useState("");

  const set = <K extends keyof GenerateRequest>(key: K, value: GenerateRequest[K]) =>
    setForm((f) => ({ ...f, [key]: value }));

  useEffect(() => {
    api.courses().then(setCourses).catch(() => setCourses([]));
    api.certifications().then(setCertifications).catch(() => setCertifications([]));
  }, []);

  // Pick up a run that is already going. A course takes the better part of an
  // hour, and the job lives in the backend, not in this component — so
  // reloading the page, or opening it in a second tab, or starting the run
  // from somewhere else, should all show the run rather than an idle form
  // with no sign that anything is happening.
  useEffect(() => {
    if (jobId) return;
    let live = true;
    api
      .jobs()
      .then((all) => {
        const running = all.find((j) => j.status === "running");
        if (live && running) setJobId(running.id);
      })
      .catch(() => undefined);
    return () => {
      live = false;
    };
    // Only on mount: once a job is being followed, the poll below owns it.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Labs belong to the chosen course, so the selected lab has to be dropped
  // when the course changes — otherwise a stale lab slug is sent for a course
  // that has never heard of it.
  useEffect(() => {
    if (!form.course_slug) {
      setLabs([]);
      return;
    }
    let live = true;
    api
      .labs(form.course_slug)
      .then((l) => live && setLabs(l))
      .catch(() => live && setLabs([]));
    return () => {
      live = false;
    };
  }, [form.course_slug]);

  // Poll while the job runs. The interval is cleared when the job finishes and
  // on unmount — a timer left running would keep calling setState on a
  // component that is gone, and keep hitting the API for a job nobody is
  // watching.
  const pollRef = useRef<number | null>(null);
  useEffect(() => {
    if (!jobId) return;

    const stop = () => {
      if (pollRef.current !== null) {
        clearInterval(pollRef.current);
        pollRef.current = null;
      }
    };

    const tick = async () => {
      try {
        const next = await api.job(jobId);
        setJob(next);
        if (next.status !== "running") {
          stop();
          // Everything generated starts selected: the author is reviewing a
          // proposal, and unticking what is wrong is less work than ticking
          // everything that is right.
          setKeep(new Set(next.result.map((q) => q.id)));
        }
      } catch (e: unknown) {
        stop();
        setError(e instanceof ApiError ? e.message : String(e));
      }
    };

    void tick();
    pollRef.current = window.setInterval(() => void tick(), POLL_MS);
    return stop;
  }, [jobId]);

  async function start() {
    setError("");
    setSaved("");
    setJob(null);
    setKeep(new Set());
    setBusy(true);
    try {
      const { jobId: id } = await api.generate({
        ...form,
        formats: toRequestFormats(formatRows),
      });
      setJobId(id);
    } catch (e: unknown) {
      setError(e instanceof ApiError ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  async function cancel() {
    if (!jobId) return;
    try {
      await api.cancelJob(jobId);
    } catch (e: unknown) {
      setError(e instanceof ApiError ? e.message : String(e));
    }
  }

  async function commit() {
    if (!jobId) return;
    setBusy(true);
    setError("");
    try {
      const { saved: count, refused = [] } = await api.commitJob(
        jobId,
        [...keep],
        form.certification_id ?? "",
      );
      // A question nobody can answer is refused, as import refuses one; say
      // which and why rather than let the count quietly come up short.
      const why = refused.map((r) => `"${r.stem}" (${r.reason})`).join("; ");
      setSaved(
        `Saved ${count} question${count === 1 ? "" : "s"} to the bank.` +
          (refused.length
            ? ` Not saved, because ${refused.length === 1 ? "it" : "they"} could not be graded: ${why}`
            : ""),
      );
      setJob(null);
      setJobId("");
      setKeep(new Set());
      onCommitted?.();
    } catch (e: unknown) {
      setError(e instanceof ApiError ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  const running = job?.status === "running";
  const finished = job && job.status !== "running";
  const percent =
    job && job.progress.total > 0
      ? Math.min(100, Math.round((job.progress.current / job.progress.total) * 100))
      : 0;

  return (
    <div>
      <div className="card" style={{ marginBottom: 16 }}>
        <div className="toolbar">
          <label className="muted" htmlFor="gen-course">
            Course
          </label>
          <select
            id="gen-course"
            value={form.course_slug}
            onChange={(e) => {
              set("course_slug", e.target.value);
              set("lab_slug", "");
            }}
          >
            <option value="">Choose a course…</option>
            {courses.map((c) => (
              <option key={c.slug} value={c.slug}>
                {c.title}
              </option>
            ))}
          </select>

          <label className="muted" htmlFor="gen-lab">
            Lab
          </label>
          <select
            id="gen-lab"
            value={form.lab_slug}
            disabled={!form.course_slug}
            onChange={(e) => set("lab_slug", e.target.value)}
          >
            <option value="">Whole course</option>
            {labs.map((l) => (
              <option key={l.slug} value={l.slug}>
                {/* Named as skipped rather than hidden: reading the whole
                    course leaves it out, but picking it deliberately reads
                    it, and a lab that just vanished would look like a bug. */}
                {l.frontMatter ? `${l.title} (skipped in a whole-course run)` : l.title}
              </option>
            ))}
          </select>

          <label className="muted" htmlFor="gen-cert">
            File under
          </label>
          <select
            id="gen-cert"
            value={form.certification_id}
            onChange={(e) => set("certification_id", e.target.value)}
          >
            <option value="">No certification</option>
            {certifications.map((c) => (
              <option key={c.id} value={c.id}>
                {c.name}
              </option>
            ))}
          </select>
        </div>

        <div className="toolbar">
          <label className="muted" htmlFor="gen-total">
            Questions
          </label>
          <input
            id="gen-total"
            type="number"
            min={1}
            max={500}
            style={{ width: 80 }}
            value={form.total}
            onChange={(e) => set("total", Number(e.target.value))}
          />

          <label className="muted" htmlFor="gen-difficulty">
            Difficulty
          </label>
          <select
            id="gen-difficulty"
            value={form.difficulty}
            onChange={(e) => set("difficulty", e.target.value)}
          >
            {DIFFICULTIES.map((d) => (
              <option key={d}>{d}</option>
            ))}
          </select>

          <label className="muted">
            <input
              type="checkbox"
              checked={form.shuffle_formats}
              onChange={(e) => set("shuffle_formats", e.target.checked)}
              disabled={formatRows.length < 2}
              title={
                formatRows.length < 2
                  ? "Add a second format first — there is nothing to mix"
                  : "Deal the formats out at random rather than in order"
              }
            />{" "}
            Mix formats
          </label>
        </div>

        <FormatRows rows={formatRows} onChange={setFormatRows} />

        <div className="toolbar">
          <span className="muted">Bloom&rsquo;s</span>
          {BLOOM_LEVELS.map((level) => {
            const on = (form.bloom_levels ?? []).includes(level);
            return (
              <label key={level} className={on ? "" : "faint"}>
                <input
                  type="checkbox"
                  checked={on}
                  onChange={(e) => {
                    const current = new Set(form.bloom_levels ?? []);
                    if (e.target.checked) current.add(level);
                    else current.delete(level);
                    // At least one has to stay: an empty list would send the
                    // backend nothing to spread across the sections.
                    set("bloom_levels", current.size ? [...current] : [level]);
                  }}
                />{" "}
                {level}
              </label>
            );
          })}
        </div>

        <div className="toolbar">
          <input
            className="grow"
            placeholder="Extra instructions for the model (optional)"
            value={form.custom_instructions}
            onChange={(e) => set("custom_instructions", e.target.value)}
          />
          <button onClick={start} disabled={!form.course_slug || busy || running}>
            {running ? "Generating…" : "Generate"}
          </button>
          {running && (
            <button className="secondary" onClick={cancel}>
              Cancel
            </button>
          )}
        </div>
      </div>

      {error && <div className="banner">{error}</div>}
      {saved && <div className="banner warn">{saved}</div>}

      {job && (
        <div className="card" style={{ marginBottom: 16 }}>
          <div className="toolbar" style={{ marginBottom: 8 }}>
            <strong>
              {job.status === "running"
                ? "Generating"
                : job.status === "done"
                  ? // "7 of 12" when the model returned fewer than asked, so a
                    // shortfall is visible rather than looking like the plan.
                    job.requested && job.count < job.requested
                    ? `Generated ${job.count} of ${job.requested}`
                    : `Generated ${job.count}`
                  : job.status === "cancelled"
                    ? "Cancelled"
                    : "Failed"}
            </strong>
            <span className="muted">{job.progress.message}</span>
            <span className="spacer" />
            {job.progress.total > 0 && (
              <span className="muted">
                {job.progress.current}/{job.progress.total}
              </span>
            )}
          </div>
          <div
            role="progressbar"
            aria-valuenow={percent}
            aria-valuemin={0}
            aria-valuemax={100}
            style={{ height: 4, background: "var(--bg-input)", borderRadius: 2 }}
          >
            <div
              style={{
                width: `${percent}%`,
                height: "100%",
                background: "var(--accent)",
                borderRadius: 2,
                transition: "width .3s",
              }}
            />
          </div>
          {job.status === "error" && <div className="banner" style={{ marginTop: 10 }}>{job.error}</div>}
        </div>
      )}

      {finished && job.result.length > 0 && (
        <Review
          questions={job.result}
          keep={keep}
          onToggle={(id) =>
            setKeep((previous) => {
              const next = new Set(previous);
              if (next.has(id)) next.delete(id);
              else next.add(id);
              return next;
            })
          }
          onAll={(all) => setKeep(all ? new Set(job.result.map((q) => q.id)) : new Set())}
          onCommit={commit}
          busy={busy}
        />
      )}

      {finished && job.result.length === 0 && job.status === "done" && (
        <div className="empty">
          The model returned nothing usable from that material.
        </div>
      )}
    </div>
  );
}

/**
 * The shapes a run should produce.
 *
 * One row is one question shape and the run cycles through them, so a single
 * run can mix "choose one of four" with "choose two of five". With no rows
 * every question takes the same shape — which is why "Mix formats" is
 * disabled until there are two: shuffling one repeated shape changes nothing,
 * and a control that does nothing is worse than one that is greyed out.
 */
function FormatRows({
  rows,
  onChange,
}: {
  rows: FormatRow[];
  onChange: (rows: FormatRow[]) => void;
}) {
  const update = (index: number, patch: Partial<FormatRow>) =>
    onChange(rows.map((r, i) => (i === index ? { ...r, ...patch } : r)));

  return (
    <div className="toolbar" style={{ alignItems: "flex-start" }}>
      <span className="muted" style={{ paddingTop: 7 }}>
        Formats
      </span>
      <div style={{ flex: 1 }}>
        {rows.length === 0 && (
          <div className="faint" style={{ paddingTop: 7 }}>
            Every question: one correct answer of four. Add a format to mix shapes.
          </div>
        )}
        {rows.map((row, i) => (
          <div key={i} className="toolbar" style={{ marginBottom: 6 }}>
            <label className="muted" htmlFor={`fmt-keys-${i}`}>
              Choose
            </label>
            <input
              id={`fmt-keys-${i}`}
              type="number"
              min={1}
              max={4}
              style={{ width: 58 }}
              value={row.keys}
              onChange={(e) => update(i, { keys: Number(e.target.value) })}
            />
            <label className="muted" htmlFor={`fmt-distractors-${i}`}>
              of
            </label>
            <input
              id={`fmt-distractors-${i}`}
              type="number"
              min={2}
              max={8}
              style={{ width: 58 }}
              // Bound to a real field, not to `keys + distractors`. A derived
              // value cannot be cleared: emptying it recomputed a number,
              // which reappeared in the box, and the next keystroke appended
              // to it — clear-then-type-5 gave 25.
              value={row.total}
              onChange={(e) => update(i, { total: Number(e.target.value) })}
            />
            <span className="faint">
              {/* How a candidate sees the count. The stem itself holds only the
                  question (core/stem_text.py); the Content Manager adds this
                  from the number of correct answers, spelling small numbers
                  out. */}
              {`shown as “(Choose ${NUMBER_WORDS[row.keys] ?? row.keys})”`}
            </span>
            <button
              className="secondary"
              onClick={() => onChange(rows.filter((_, j) => j !== i))}
              aria-label={`Remove format ${i + 1}`}
            >
              Remove
            </button>
          </div>
        ))}
        <button
          className="secondary"
          onClick={() =>
            onChange([...rows, rows.length ? { keys: 2, total: 5 } : { keys: 1, total: 4 }])
          }
        >
          Add a format
        </button>
      </div>
    </div>
  );
}

function Review({
  questions,
  keep,
  onToggle,
  onAll,
  onCommit,
  busy,
}: {
  questions: Question[];
  keep: Set<string>;
  onToggle: (id: string) => void;
  onAll: (all: boolean) => void;
  onCommit: () => void;
  busy: boolean;
}) {
  return (
    <div>
      <div className="toolbar">
        <strong>Review</strong>
        <span className="muted">
          {keep.size} of {questions.length} selected
        </span>
        <button className="secondary" onClick={() => onAll(true)}>
          Select all
        </button>
        <button className="secondary" onClick={() => onAll(false)}>
          Select none
        </button>
        <span className="spacer" />
        <button onClick={onCommit} disabled={busy || keep.size === 0}>
          Save {keep.size} to the bank
        </button>
      </div>

      {questions.map((q) => (
        <div key={q.id} className="card" style={{ marginBottom: 10 }}>
          <label style={{ display: "flex", gap: 10, alignItems: "flex-start" }}>
            <input
              type="checkbox"
              checked={keep.has(q.id)}
              onChange={() => onToggle(q.id)}
              aria-label={`Keep: ${q.stem}`}
              style={{ marginTop: 4 }}
            />
            <span style={{ flex: 1 }}>
              {q.scenario && <div className="muted">{q.scenario}</div>}
              <div style={{ fontWeight: 600, margin: "3px 0" }}>{q.stem}</div>
              <ul style={{ margin: "6px 0", paddingLeft: 20 }}>
                {(q.option_order.length ? q.option_order : [q.key, ...q.distractors]).map(
                  (option, i) => {
                    const correct =
                      q.question_type === "multi" ? q.keys.includes(option) : option === q.key;
                    return (
                      <li key={i} style={{ color: correct ? "var(--ok)" : "var(--text-dim)" }}>
                        {option}
                        {correct && " ✓"}
                      </li>
                    );
                  },
                )}
              </ul>
              {q.explanation && (
                <div className="faint" style={{ fontSize: 12 }}>
                  {q.explanation}
                </div>
              )}
              <div className="faint" style={{ fontSize: 12, marginTop: 4 }}>
                {q.topic} · {q.difficulty} · {q.bloom_level}
                {q.tags.includes("key-not-validated") && (
                  // The question could not be anchored to anything in the
                  // course material, so it may be about something the course
                  // does not cover. Note this says nothing about whether the
                  // ANSWER is right — that cannot be checked here, and every
                  // question needs a human read before it is trusted.
                  <strong style={{ color: "var(--warn)" }}> · not anchored to the course material</strong>
                )}
              </div>
            </span>
          </label>
        </div>
      ))}
    </div>
  );
}
