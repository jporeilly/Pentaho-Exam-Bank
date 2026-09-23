/**
 * Bring a file of questions into the bank.
 *
 * Look-then-save, like publishing, and for the same reason: an import is
 * somebody else's work landing in the bank, often hundreds of rows at once,
 * and the two things that matter about it are invisible in the file itself.
 * Which questions cannot be graded — a missing key, a distractor identical to
 * the answer — and which ones the bank already has. Both are shown before
 * anything is saved, and neither is something an author can check by reading
 * a spreadsheet.
 *
 * Selection defaults to the questions worth keeping: gradeable, and not
 * already in the bank. A duplicate stays selectable, because "we reworded it"
 * is a real answer, but it takes a deliberate tick.
 */
import { useEffect, useMemo, useRef, useState } from "react";

import {
  api,
  ApiError,
  type Certification,
  type ImportedQuestion,
  type ImportPreview,
  type ImportResult,
} from "./api";

const ACCEPT = ".csv,.json,.xlsx,.xml,.txt";

function Stat({ n, label, tone = "" }: { n: number; label: string; tone?: string }) {
  return (
    <span className={`stat ${tone}`}>
      <strong>{n}</strong> {label}
    </span>
  );
}

export function ImportPane({ onImported }: { onImported?: () => void } = {}) {
  const [certifications, setCertifications] = useState<Certification[]>([]);
  const [certId, setCertId] = useState("");
  const [topic, setTopic] = useState("");

  const [preview, setPreview] = useState<ImportPreview | null>(null);
  const [keep, setKeep] = useState<Set<number>>(new Set());
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [done, setDone] = useState<ImportResult | null>(null);

  const fileInput = useRef<HTMLInputElement>(null);

  useEffect(() => {
    api
      .certifications()
      .then(setCertifications)
      .catch((e: unknown) => setError(e instanceof ApiError ? e.message : String(e)));
  }, []);

  async function choose(file: File | undefined) {
    if (!file) return;
    setBusy(true);
    setError("");
    setDone(null);
    setPreview(null);
    try {
      const result = await api.previewImport(file);
      setPreview(result);
      // Worth keeping by default: gradeable and not already here. Everything
      // else is a decision, and a pre-ticked decision is not one.
      setKeep(
        new Set(
          result.questions
            .map((q, i) => (q.problems.length === 0 && !q.duplicate_of ? i : -1))
            .filter((i) => i >= 0),
        ),
      );
    } catch (e) {
      setError(e instanceof ApiError ? e.message : String(e));
    } finally {
      setBusy(false);
      // Let the same file be chosen again after a fix, which the browser
      // otherwise suppresses because the value has not changed.
      if (fileInput.current) fileInput.current.value = "";
    }
  }

  function toggle(index: number) {
    setKeep((current) => {
      const next = new Set(current);
      if (next.has(index)) next.delete(index);
      else next.add(index);
      return next;
    });
  }

  const selectable = useMemo(
    () =>
      preview
        ? preview.questions
            .map((q, i) => (q.problems.length === 0 ? i : -1))
            .filter((i) => i >= 0)
        : [],
    [preview],
  );

  async function save() {
    if (!preview) return;
    setBusy(true);
    setError("");
    try {
      const chosen = [...keep]
        .sort((a, b) => a - b)
        .map((i) => preview.questions[i].question);
      const result = await api.commitImport(chosen, certId, topic.trim());
      setDone(result);
      setPreview(null);
      setKeep(new Set());
      onImported?.();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="card import">
      <p className="lede">
        Reads CSV, Excel, QTI 2.1, Moodle XML, a Content Manager{" "}
        <code className="mono">exam.json</code>, or this bank's own JSON export.
        Questions arrive as drafts — nothing is saved until you choose it.
      </p>

      <div className="toolbar">
        <input
          ref={fileInput}
          type="file"
          accept={ACCEPT}
          aria-label="Question file"
          disabled={busy}
          onChange={(e) => choose(e.target.files?.[0])}
        />
        {busy && !preview && <span className="faint">Reading…</span>}
      </div>

      {error && <div className="banner">{error}</div>}

      {done && (
        <div className="plan card">
          <h3>Imported</h3>
          <p>
            <strong>{done.saved}</strong>{" "}
            {done.saved === 1 ? "question" : "questions"} added to the bank as
            drafts.
          </p>
          {done.refused.length > 0 && (
            <>
              <p className="faint">
                {done.refused.length} could not be saved. The bank's editor
                would refuse these too, so they are listed rather than stored
                broken:
              </p>
              <ul className="refused">
                {done.refused.map((r, i) => (
                  <li key={i}>
                    <span className="mono">{r.stem || "(no stem)"}</span>
                    <div className="faint">{r.reason}</div>
                  </li>
                ))}
              </ul>
            </>
          )}
        </div>
      )}

      {preview && (
        <div className="plan card">
          <h3>
            <code className="mono">{preview.filename}</code> — {preview.formatLabel}
          </h3>

          {preview.formatNote && (
            // The plain-text reader guesses a key from position and the result
            // is perfectly gradeable, so nothing else in the app will ever
            // flag it. This banner is the only warning there is.
            <div className="banner warn">{preview.formatNote}</div>
          )}

          <p className="stats">
            <Stat n={preview.count} label="found" />
            <Stat n={preview.gradeable} label="gradeable" tone="ok" />
            {preview.count - preview.gradeable > 0 && (
              <Stat
                n={preview.count - preview.gradeable}
                label="cannot be graded"
                tone="bad"
              />
            )}
            {preview.duplicates > 0 && (
              <Stat n={preview.duplicates} label="already in the bank" tone="warn" />
            )}
          </p>

          <div className="field-row">
            <label className="field">
              <span className="field-label">Certification</span>
              <select value={certId} onChange={(e) => setCertId(e.target.value)}>
                <option value="">Leave unassigned</option>
                {certifications.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.name} — {c.questionCount}
                  </option>
                ))}
              </select>
            </label>
            <label className="field">
              <span className="field-label">Topic</span>
              <input
                value={topic}
                placeholder="Leave blank to keep each question's own"
                onChange={(e) => setTopic(e.target.value)}
              />
            </label>
          </div>

          <div className="toolbar">
            <button onClick={save} disabled={busy || keep.size === 0}>
              {busy ? "Saving…" : `Import ${keep.size} of ${preview.count}`}
            </button>
            <button
              className="secondary"
              onClick={() => setKeep(new Set(selectable))}
              disabled={busy}
            >
              Select all gradeable
            </button>
            <button
              className="secondary"
              onClick={() => setKeep(new Set())}
              disabled={busy}
            >
              Select none
            </button>
            {keep.size === 0 && <span className="faint">Nothing selected.</span>}
          </div>

          <table>
            <thead>
              <tr>
                <th style={{ width: 34 }} />
                <th>Question</th>
                <th style={{ width: 200 }}>Correct answer</th>
              </tr>
            </thead>
            <tbody>
              {preview.questions.map((q, i) => (
                <Row
                  key={i}
                  item={q}
                  checked={keep.has(i)}
                  onToggle={() => toggle(i)}
                />
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

function Row({
  item,
  checked,
  onToggle,
}: {
  item: ImportedQuestion;
  checked: boolean;
  onToggle: () => void;
}) {
  const broken = item.problems.length > 0;
  const answers =
    item.question.question_type === "multi"
      ? item.question.keys.join(", ")
      : item.question.key;

  return (
    <tr className={`q-row ${broken ? "broken" : ""}`}>
      <td>
        <input
          type="checkbox"
          checked={checked}
          // A question the server would refuse cannot be chosen. Leaving it
          // tickable would move the refusal to after the button.
          disabled={broken}
          onChange={onToggle}
          aria-label={`Import "${item.question.stem.slice(0, 40)}"`}
        />
      </td>
      <td>
        {item.question.stem || <span className="faint">(no stem)</span>}
        {item.problems.map((p) => (
          <div key={p.message} className="problem">
            {p.message}
          </div>
        ))}
        {item.duplicate_of && (
          <div className="duplicate">
            {item.duplicate_score}% match for one already in the bank:{" "}
            <span className="faint">“{item.duplicate_stem}”</span>
          </div>
        )}
      </td>
      <td className="faint">{answers || <span className="problem-inline">none</span>}</td>
    </tr>
  );
}
