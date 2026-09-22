/**
 * Edit one question: fix a key, reword a stem, move it through review.
 *
 * The options are the hard part and the reason this is not a form of flat
 * text fields. A question is a KEY (or several) plus DISTRACTORS, and the
 * two are only meaningful together: a distractor identical to the key
 * makes the item unanswerable, an empty key makes it ungradeable, and a
 * single-select question with two keys is not a thing the grader can
 * score. Those live here as inline problems rather than as a save that
 * fails, because the person editing wants to know before they commit.
 *
 * The lifecycle is ASKED FOR, not restated. `/api/lifecycle` returns the
 * same STATUS_TRANSITIONS table the model enforces, so the buttons offered
 * are exactly the moves that will be accepted.
 */
import { useEffect, useMemo, useState } from "react";
import { api, ApiError, type Lifecycle, type Question } from "./api";

/** A field-level problem, shown inline and blocking save. */
export interface Problem {
  field: string;
  message: string;
}

/**
 * Everything wrong with a question, as the grader would see it.
 *
 * Exported and pure so the rules are testable without rendering: these are
 * assertions about what a gradeable item IS, and they should not be
 * reachable only by driving a form.
 */
export function problemsWith(q: Question): Problem[] {
  const out: Problem[] = [];
  const stem = (q.stem ?? "").trim();
  if (!stem) out.push({ field: "stem", message: "A question needs a stem." });

  const keys = q.question_type === "multi" ? q.keys : [q.key];
  const live = keys.map((k) => (k ?? "").trim()).filter(Boolean);

  if (live.length === 0) {
    out.push({
      field: "keys",
      message: "Nothing is marked correct, so the question cannot be graded.",
    });
  }
  if (q.question_type === "multi" && live.length === 1) {
    out.push({
      field: "keys",
      message:
        "A select-all question with one correct answer grades the same as a " +
        "single-select one. Add another, or switch the type.",
    });
  }

  const distractors = (q.distractors ?? []).map((d) => (d ?? "").trim());
  if (distractors.some((d) => !d)) {
    out.push({ field: "distractors", message: "An empty option cannot be chosen." });
  }
  if (distractors.filter(Boolean).length === 0) {
    out.push({
      field: "distractors",
      message: "With no distractors the correct answer is the only option.",
    });
  }

  // A distractor that equals a key is the defect that survives review most
  // often: it reads fine in a list and is impossible to answer.
  const clash = distractors.filter((d) => d && live.some((k) => k.toLowerCase() === d.toLowerCase()));
  for (const d of new Set(clash)) {
    out.push({
      field: "distractors",
      message: `"${d}" is both correct and a distractor.`,
    });
  }

  const seen = new Map<string, number>();
  for (const d of distractors.filter(Boolean)) {
    const k = d.toLowerCase();
    seen.set(k, (seen.get(k) ?? 0) + 1);
  }
  for (const [text, n] of seen) {
    if (n > 1) {
      out.push({ field: "distractors", message: `"${text}" appears ${n} times.` });
    }
  }

  return out;
}

function Field({
  label,
  hint,
  children,
}: {
  label: string;
  hint?: string;
  children: React.ReactNode;
}) {
  return (
    <label className="field">
      <span className="field-label">{label}</span>
      {children}
      {hint && <span className="faint field-hint">{hint}</span>}
    </label>
  );
}

export function QuestionEditor({
  question,
  onSaved,
  onDeleted,
  onClose,
}: {
  question: Question;
  onSaved: (q: Question) => void;
  onDeleted: (id: string) => void;
  onClose: () => void;
}) {
  const [draft, setDraft] = useState<Question>(question);
  const [lifecycle, setLifecycle] = useState<Lifecycle | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [saved, setSaved] = useState(false);

  // A different question replaces the draft outright. Merging would keep
  // edits from the previous one and silently write them onto this one.
  useEffect(() => {
    setDraft(question);
    setError("");
    setSaved(false);
  }, [question]);

  useEffect(() => {
    api.lifecycle().then(setLifecycle).catch(() => setLifecycle(null));
  }, []);

  const problems = useMemo(() => problemsWith(draft), [draft]);
  const dirty = useMemo(
    () => JSON.stringify(draft) !== JSON.stringify(question),
    [draft, question],
  );

  function set<K extends keyof Question>(field: K, value: Question[K]) {
    setDraft((d) => ({ ...d, [field]: value }));
    setSaved(false);
  }

  function setDistractor(i: number, value: string) {
    const next = [...draft.distractors];
    next[i] = value;
    set("distractors", next);
  }

  async function save() {
    setBusy(true);
    setError("");
    try {
      const updated = await api.updateQuestion(draft.id, {
        scenario: draft.scenario,
        stem: draft.stem,
        question_type: draft.question_type,
        key: draft.key,
        keys: draft.keys,
        distractors: draft.distractors,
        explanation: draft.explanation,
        topic: draft.topic,
        difficulty: draft.difficulty,
        bloom_level: draft.bloom_level,
      });
      setDraft(updated);
      setSaved(true);
      onSaved(updated);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  async function move(status: string) {
    setBusy(true);
    setError("");
    try {
      const updated = await api.setStatus(draft.id, status);
      setDraft(updated);
      onSaved(updated);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  async function remove() {
    setBusy(true);
    setError("");
    try {
      await api.deleteQuestion(draft.id);
      onDeleted(draft.id);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : String(e));
      setBusy(false);
    }
  }

  const moves = lifecycle?.transitions[draft.status] ?? [];
  const forField = (name: string) => problems.filter((p) => p.field === name);

  return (
    <div className="editor card">
      <div className="toolbar">
        <strong>Edit question</strong>
        <code className="mono faint">{draft.id.slice(0, 12)}</code>
        <span className={`pill ${draft.status}`}>{draft.status.replace("_", " ")}</span>
        <span className="spacer" />
        <button className="secondary" onClick={onClose} disabled={busy}>
          Close
        </button>
      </div>

      {error && <div className="banner">{error}</div>}

      <Field label="Scenario" hint="Optional context shown above the question.">
        <textarea
          rows={2}
          value={draft.scenario}
          onChange={(e) => set("scenario", e.target.value)}
        />
      </Field>

      <Field label="Question">
        <textarea rows={3} value={draft.stem} onChange={(e) => set("stem", e.target.value)} />
      </Field>
      {forField("stem").map((p) => (
        <div key={p.message} className="problem">
          {p.message}
        </div>
      ))}

      <Field label="Type">
        <select
          value={draft.question_type}
          onChange={(e) => set("question_type", e.target.value as Question["question_type"])}
        >
          <option value="single">One correct answer</option>
          <option value="multi">Select all that apply</option>
        </select>
      </Field>

      {draft.question_type === "single" ? (
        <Field label="Correct answer">
          <input value={draft.key} onChange={(e) => set("key", e.target.value)} />
        </Field>
      ) : (
        <Field label="Correct answers" hint="One per line.">
          <textarea
            rows={3}
            value={draft.keys.join("\n")}
            onChange={(e) => set("keys", e.target.value.split("\n"))}
          />
        </Field>
      )}
      {forField("keys").map((p) => (
        <div key={p.message} className="problem">
          {p.message}
        </div>
      ))}

      <Field label="Distractors">
        <div className="options">
          {draft.distractors.map((d, i) => (
            <div key={i} className="option-row">
              <input value={d} onChange={(e) => setDistractor(i, e.target.value)} />
              <button
                className="secondary"
                onClick={() =>
                  set(
                    "distractors",
                    draft.distractors.filter((_, j) => j !== i),
                  )
                }
              >
                Remove
              </button>
            </div>
          ))}
          <button
            className="secondary"
            onClick={() => set("distractors", [...draft.distractors, ""])}
          >
            Add a distractor
          </button>
        </div>
      </Field>
      {forField("distractors").map((p) => (
        <div key={p.message} className="problem">
          {p.message}
        </div>
      ))}

      <Field label="Explanation" hint="Shown after the exam, never before.">
        <textarea
          rows={3}
          value={draft.explanation}
          onChange={(e) => set("explanation", e.target.value)}
        />
      </Field>

      <div className="field-row">
        <Field label="Topic">
          <input value={draft.topic} onChange={(e) => set("topic", e.target.value)} />
        </Field>
        <Field label="Difficulty">
          <select value={draft.difficulty} onChange={(e) => set("difficulty", e.target.value)}>
            {["Easy", "Medium", "Hard"].map((d) => (
              <option key={d}>{d}</option>
            ))}
          </select>
        </Field>
        <Field label="Bloom level">
          <select value={draft.bloom_level} onChange={(e) => set("bloom_level", e.target.value)}>
            {["Remember", "Understand", "Apply", "Analyze", "Evaluate", "Create"].map((b) => (
              <option key={b}>{b}</option>
            ))}
          </select>
        </Field>
      </div>

      <div className="toolbar editor-actions">
        <button onClick={save} disabled={busy || !dirty || problems.length > 0}>
          {busy ? "Saving…" : "Save"}
        </button>
        {saved && !dirty && <span className="muted">Saved</span>}
        {problems.length > 0 && (
          <span className="muted">
            {problems.length} problem{problems.length > 1 ? "s" : ""} to fix first
          </span>
        )}

        <span className="spacer" />

        {/* Only the moves the model will accept. See /api/lifecycle. */}
        {moves.map((m) => (
          <button key={m} className="secondary" onClick={() => move(m)} disabled={busy || dirty}>
            {m === "sme_review" ? "Send for review" : m.charAt(0).toUpperCase() + m.slice(1)}
          </button>
        ))}
        {dirty && moves.length > 0 && (
          <span className="faint">Save before changing status</span>
        )}

        <button className="secondary danger" onClick={remove} disabled={busy}>
          Delete
        </button>
      </div>
    </div>
  );
}
