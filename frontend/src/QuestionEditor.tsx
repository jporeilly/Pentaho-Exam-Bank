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
import {
  api,
  ApiError,
  type AiReview,
  type AiRewrite,
  type Lifecycle,
  type Problem,
  type Question,
} from "./api";

// `Problem` is defined in api.ts and re-exported here. Import reports the same
// shape from the server, computed by `core/validation.py` from the same rules,
// so two declarations would be two names for one contract.
export type { Problem };

/** Which moves exist comes from /api/lifecycle; what a button SAYS is ours.
 *  A verb for what pressing it does, not the name of where it lands. */
const MOVE_LABEL: Record<string, string> = {
  sme_review: "Send for review",
  draft: "Back to draft",
  revised: "Mark revised",
  approved: "Approve",
  rejected: "Reject",
  retired: "Retire",
};

const STATUS_NAME: Record<string, string> = {
  draft: "Draft",
  sme_review: "SME Review",
  revised: "Revised",
  approved: "Approved",
  rejected: "Rejected",
  retired: "Retired",
};

/** HH:MM, so a second save visibly says something new. */
function clock(): string {
  return new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
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

// ── The house form ───────────────────────────────────────────────────────
//
// The scenario is statements that set the scene; the question is the
// question and nothing else. Mirrors core/stem_text.py (form_notes), so the
// author sees it while typing rather than after a round trip; the same cases
// are pinned on both sides (tests/test_stem_text.py, QuestionEditor.test.tsx).
// Advice, not a problem: it does not stop a save.

const COUNT_WORDS =
  "(?:one|two|three|four|five|six|seven|eight|nine|ten|\\d+" +
  "|all(?:\\s+that\\s+apply)?|the\\s+(?:best|correct)\\s+(?:answer|option|response)s?)";
const COUNT_NOUN = "(?:\\s+(?:correct\\s+|best\\s+)?(?:answer|option|response|choice)s?)?";
const DIRECTIVE = new RegExp(
  "(?:\\s*[([]\\s*(?:choose|select|pick)\\b[^)\\]]*[)\\]]" +
    "|(?<=[?.!:)\\s])\\s*(?:choose|select|pick)\\s+" + COUNT_WORDS + COUNT_NOUN + "\\b" +
    ")\\s*[.!]?\\s*$",
  "i",
);
const ABBREVIATIONS = /\b(?:e\.g|i\.e|etc|vs|approx|incl|no)\./gi;

/** The stem without a trailing "(Choose one.)" / "Choose One." count. */
export function questionOnly(stem: string): string {
  let text = (stem ?? "").trimEnd();
  for (;;) {
    const cut = text.replace(DIRECTIVE, "").trimEnd();
    if (cut === text) return text;
    if (!cut) return (stem ?? "").trimEnd();
    text = cut;
  }
}

export function formNotes(q: Pick<Question, "scenario" | "stem">): Problem[] {
  const out: Problem[] = [];
  if ((q.scenario ?? "").includes("?")) {
    out.push({
      field: "scenario",
      message:
        "The scenario asks a question. A scenario is statements that set the scene; " +
        "the question belongs in the Question field.",
    });
  }
  const stem = q.stem ?? "";
  const question = questionOnly(stem).trim();
  if (question !== stem.trimEnd().trim()) {
    out.push({
      field: "stem",
      message: "Stem ends with a 'Choose …' count; the course adds its own, so Publish removes it",
    });
  }
  if (!question) return out;
  const body = question.replace(ABBREVIATIONS, "");
  if ((body.match(/\?/g) ?? []).length > 1) {
    out.push({ field: "stem", message: "The Question field asks more than one question. Ask one." });
  } else if (!question.endsWith("?")) {
    out.push({ field: "stem", message: "The question should be a question, ending in “?”." });
  }
  if (/[.!]\s+\S/.test(body)) {
    out.push({
      field: "stem",
      message:
        "The question opens with statements. Move them into the scenario and keep only " +
        "the question here.",
    });
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

  // The AI proposes; the author accepts. Neither endpoint writes, and
  // "Use this" only fills the form - the question is still saved by the
  // same button as any other edit. A model that wrote to the bank directly
  // would be the one contributor whose work nobody reviewed.
  const [aiBusy, setAiBusy] = useState<"" | "rewrite" | "review">("");
  const [aiError, setAiError] = useState("");
  const [proposal, setProposal] = useState<AiRewrite | null>(null);
  const [review, setReview] = useState<AiReview | null>(null);
  const [lifecycle, setLifecycle] = useState<Lifecycle | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  // What the last save or status move did, said until the next edit. It used
  // to be a flag the effect below cleared: a save hands the updated question
  // to the parent, the parent hands it back, and "Saved" was gone before it
  // was ever drawn.
  const [notice, setNotice] = useState("");

  // A different question replaces the draft outright. Merging would keep
  // edits from the previous one and silently write them onto this one.
  useEffect(() => {
    setDraft(question);
    setError("");
  }, [question]);

  // The notice belongs to the question it was about: cleared when a
  // DIFFERENT question opens, not when this one comes back updated.
  useEffect(() => {
    setNotice("");
  }, [question.id]);

  useEffect(() => {
    api.lifecycle().then(setLifecycle).catch(() => setLifecycle(null));
  }, []);

  const problems = useMemo(() => problemsWith(draft), [draft]);
  const notes = useMemo(() => formNotes(draft), [draft]);
  const notesFor = (name: string) => notes.filter((n) => n.field === name);
  const dirty = useMemo(
    () => JSON.stringify(draft) !== JSON.stringify(question),
    [draft, question],
  );

  function set<K extends keyof Question>(field: K, value: Question[K]) {
    setDraft((d) => ({ ...d, [field]: value }));
    setNotice("");
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
      setNotice(
        updated.status === "approved"
          ? `Saved at ${clock()}. Still approved: send it back for review if this change needs one.`
          : `Saved at ${clock()}`,
      );
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
      setNotice(`Moved to ${STATUS_NAME[updated.status] ?? updated.status}`);
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

  const runRewrite = async () => {
    setAiBusy("rewrite");
    setAiError("");
    setReview(null);
    try {
      setProposal(await api.aiRewrite(draft.id));
    } catch (e: unknown) {
      setAiError(e instanceof ApiError ? e.message : String(e));
    } finally {
      setAiBusy("");
    }
  };

  const runReview = async () => {
    setAiBusy("review");
    setAiError("");
    setProposal(null);
    try {
      setReview(await api.aiReview(draft.id));
    } catch (e: unknown) {
      setAiError(e instanceof ApiError ? e.message : String(e));
    } finally {
      setAiBusy("");
    }
  };

  /** Take the proposal into the form. Still unsaved: the author reads it
   *  in the fields they already know, and presses Save if they agree. */
  const acceptProposal = () => {
    if (!proposal) return;
    setDraft({ ...draft, ...proposal.proposed, id: draft.id });
    setProposal(null);
  };

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

      <Field
        label="Scenario"
        hint="Statements that set the scene, shown above the question. Not a question."
      >
        <textarea
          rows={2}
          value={draft.scenario}
          onChange={(e) => set("scenario", e.target.value)}
        />
      </Field>
      {notesFor("scenario").map((n) => (
        <div key={n.message} className="advice">
          {n.message}
        </div>
      ))}

      <Field
        label="Question"
        hint="Only the question, ending in “?”. The number to choose is added for you."
      >
        <textarea rows={3} value={draft.stem} onChange={(e) => set("stem", e.target.value)} />
      </Field>
      {forField("stem").map((p) => (
        <div key={p.message} className="problem">
          {p.message}
        </div>
      ))}
      {notesFor("stem").map((n) => (
        <div key={n.message} className="advice">
          {n.message}
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
        {notice && (
          <span className="saved-notice" role="status">
            ✓ {notice}
          </span>
        )}
        {problems.length > 0 && (
          <span className="muted">
            {problems.length} problem{problems.length > 1 ? "s" : ""} to fix first
          </span>
        )}

        <span className="spacer" />

        {/* Only the moves the model will accept. See /api/lifecycle. */}
        {moves.map((m) => (
          <button key={m} className="secondary" onClick={() => move(m)} disabled={busy || dirty}>
            {MOVE_LABEL[m] ?? m}
          </button>
        ))}
        {dirty && moves.length > 0 && (
          <span className="faint">Save before changing status</span>
        )}

        <button
          className="secondary"
          onClick={runRewrite}
          disabled={busy || aiBusy !== ""}
          title="Ask the model for a better wording. Nothing is saved until you do."
        >
          {aiBusy === "rewrite" ? "Rewriting…" : "AI rewrite"}
        </button>
        <button
          className="secondary"
          onClick={runReview}
          disabled={busy || aiBusy !== ""}
          title="Ask the model whether this can be answered correctly as written."
        >
          {aiBusy === "review" ? "Checking…" : "AI check answers"}
        </button>

        <button className="secondary danger" onClick={remove} disabled={busy}>
          Delete
        </button>
      </div>

      {aiError && <div className="banner" style={{ marginTop: 12 }}>{aiError}</div>}

      {proposal && (
        <div className="card" style={{ marginTop: 12 }}>
          <strong>Proposed rewrite</strong>
          {proposal.unchanged && (
            <p className="muted">The model returned this unchanged.</p>
          )}
          {proposal.proposed.scenario && (
            <p className="muted" style={{ marginTop: 8 }}>{proposal.proposed.scenario}</p>
          )}
          <p style={{ marginTop: 8 }}>{proposal.proposed.stem}</p>
          <ul className="muted" style={{ fontSize: "0.9em" }}>
            <li>Key: {proposal.proposed.key}</li>
            {proposal.proposed.distractors.map((d, i) => (
              <li key={i}>{d}</li>
            ))}
          </ul>
          {(proposal.notes ?? []).map((n) => (
            <div key={n.message} className="advice">
              {n.field === "scenario" ? "Scenario: " : "Question: "}
              {n.message}
            </div>
          ))}
          {proposal.problems.length > 0 && (
            <div className="banner" style={{ marginTop: 8 }}>
              This rewrite could not be graded:{" "}
              {proposal.problems.map((p) => p.message).join("; ")}
            </div>
          )}
          <div style={{ marginTop: 10, display: "flex", gap: 8 }}>
            <button onClick={acceptProposal} disabled={proposal.problems.length > 0}>
              Use this
            </button>
            <button className="secondary" onClick={() => setProposal(null)}>
              Discard
            </button>
            <span className="muted" style={{ alignSelf: "center" }}>
              Nothing is saved until you press Save.
            </span>
          </div>
        </div>
      )}

      {review && (
        <div className="card" style={{ marginTop: 12 }}>
          <strong>Answer check</strong>
          {review.answers.length === 0 && review.prose.length === 0 &&
            review.gradeable.length === 0 && (review.form ?? []).length === 0 && (
              <p className="muted">
                Nothing found. That is a second opinion, not a guarantee.
              </p>
            )}
          {review.gradeable.length > 0 && (
            <ul>
              {review.gradeable.map((g, i) => (
                <li key={`g${i}`} className="warn">
                  <strong>{g.field}:</strong> {g.message}{" "}
                  <span className="muted">(the bank&rsquo;s own check)</span>
                </li>
              ))}
            </ul>
          )}
          {(review.form ?? []).length > 0 && (
            <ul>
              {(review.form ?? []).map((f, i) => (
                <li key={`f${i}`} className="warn">
                  <strong>{f.field === "scenario" ? "scenario" : "question"}:</strong>{" "}
                  {f.message} <span className="muted">(the bank&rsquo;s own check)</span>
                </li>
              ))}
            </ul>
          )}
          {review.answers.length > 0 && (
            <ul>
              {review.answers.map((f, i) => (
                <li key={`a${i}`} className={f.severity === "error" ? "warn" : ""}>
                  <strong>{f.field}</strong>
                  {f.value && <> &mdash; &ldquo;{f.value}&rdquo;</>}: {f.issue}
                </li>
              ))}
            </ul>
          )}
          {review.prose.length > 0 && (
            <>
              <div className="muted" style={{ marginTop: 8 }}>Proofreading</div>
              <ul className="muted" style={{ fontSize: "0.9em" }}>
                {review.prose.map((f, i) => (
                  <li key={`p${i}`}>
                    <strong>{f.field}</strong>: {f.issue}
                  </li>
                ))}
              </ul>
            </>
          )}
        </div>
      )}
    </div>
  );
}
