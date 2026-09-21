import { useCallback, useEffect, useRef, useState } from "react";

import {
  api,
  ApiError,
  type Certification,
  type Question,
  type QuestionFilters,
} from "./api";

const PAGE = 25;

/**
 * Browse what is in the bank.
 *
 * The 395 questions adopted from the courses had no editing tool anywhere
 * before this: the bank never kept what it exported, and the Content Editor
 * deliberately refuses to touch `questions`. This is the first screen that
 * shows them.
 */
export function BankPane({ onChanged }: { onChanged?: () => void }) {
  const [certifications, setCertifications] = useState<Certification[]>([]);
  const [questions, setQuestions] = useState<Question[] | null>(null);
  const [total, setTotal] = useState(0);
  const [offset, setOffset] = useState(0);
  const [error, setError] = useState("");

  // Guards against an out-of-order response overwriting a newer one.
  const latest = useRef(0);

  const [text, setText] = useState("");
  const [certification, setCertification] = useState("");
  const [status, setStatus] = useState("");

  const filters: QuestionFilters = {
    text,
    certification_id: certification,
    status,
    limit: PAGE,
    offset,
  };

  const load = useCallback(() => {
    // Every keystroke starts a request, and they do not necessarily come back
    // in the order they were sent — a slow "cluster" landing after a fast
    // "clustered" would leave the wrong rows under the right search box. Each
    // run claims a ticket and only the newest one is allowed to set state.
    const ticket = ++latest.current;
    api
      .questions(filters)
      .then((page) => {
        if (ticket !== latest.current) return;
        setQuestions(page.items);
        setTotal(page.total);
        setError("");
      })
      .catch((e: unknown) => {
        if (ticket !== latest.current) return;
        setError(e instanceof ApiError ? e.message : String(e));
      });
    // The filter values are the dependency, not the object built from them,
    // which is new on every render.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [text, certification, status, offset]);

  useEffect(load, [load]);

  useEffect(() => {
    api.certifications().then(setCertifications).catch(() => setCertifications([]));
  }, []);

  // Any filter change puts us back on the first page: staying on page 4 of a
  // result set that now has one page shows an empty table and looks broken.
  const changeFilter = (apply: () => void) => {
    apply();
    setOffset(0);
  };

  async function remove(question: Question) {
    if (!confirm(`Delete "${question.stem.slice(0, 60)}"?`)) return;
    try {
      await api.deleteQuestion(question.id);
      load();
      onChanged?.();
    } catch (e: unknown) {
      setError(e instanceof ApiError ? e.message : String(e));
    }
  }

  const shown = questions?.length ?? 0;
  const from = total === 0 ? 0 : offset + 1;

  return (
    <div>
      <div className="toolbar">
        <input
          className="grow"
          placeholder="Search stems, scenarios, answers…"
          value={text}
          onChange={(e) => changeFilter(() => setText(e.target.value))}
        />
        <select
          value={certification}
          onChange={(e) => changeFilter(() => setCertification(e.target.value))}
        >
          <option value="">All certifications</option>
          {certifications.map((c) => (
            <option key={c.id} value={c.id}>
              {c.name} ({c.questionCount})
            </option>
          ))}
        </select>
        <select value={status} onChange={(e) => changeFilter(() => setStatus(e.target.value))}>
          <option value="">Any status</option>
          {["draft", "sme_review", "revised", "approved", "rejected", "retired"].map((s) => (
            <option key={s} value={s}>
              {s.replace("_", " ")}
            </option>
          ))}
        </select>
        <a href={api.exportUrl("csv", { text, certification_id: certification, status })}>
          <button className="secondary">Export CSV</button>
        </a>
      </div>

      {error && <div className="banner">{error}</div>}

      <div className="card">
        {!questions ? (
          <div className="empty">Loading…</div>
        ) : questions.length === 0 ? (
          <div className="empty">No questions match those filters.</div>
        ) : (
          <table>
            <thead>
              <tr>
                <th style={{ width: 110 }}>ID</th>
                <th>Question</th>
                <th style={{ width: 150 }}>Topic</th>
                <th style={{ width: 100 }}>Status</th>
                <th style={{ width: 60, textAlign: "right" }}>Order</th>
                <th style={{ width: 80 }} />
              </tr>
            </thead>
            <tbody>
              {questions.map((q) => (
                <tr key={q.id}>
                  <td className="mono faint">{q.id.slice(0, 12)}</td>
                  <td>
                    {q.stem}
                    <div className="faint" style={{ fontSize: 12 }}>
                      {q.question_type === "multi"
                        ? `${q.keys.length} correct`
                        : "1 correct"}{" "}
                      of {q.option_order.length || q.distractors.length + 1} ·{" "}
                      {q.difficulty} · {q.bloom_level}
                    </div>
                  </td>
                  <td className="muted">{q.topic}</td>
                  <td>
                    <span className={`pill ${q.status}`}>{q.status.replace("_", " ")}</span>
                  </td>
                  <td className="num">
                    {q.pool_order >= 0 ? q.pool_order : <span className="faint">—</span>}
                  </td>
                  <td>
                    <button className="secondary" onClick={() => remove(q)}>
                      Delete
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      <div className="toolbar" style={{ marginTop: 14 }}>
        <span className="muted">
          {total === 0 ? "Nothing to show" : `${from}–${offset + shown} of ${total}`}
        </span>
        <span className="spacer" />
        <button
          className="secondary"
          disabled={offset === 0}
          onClick={() => setOffset(Math.max(0, offset - PAGE))}
        >
          Previous
        </button>
        <button
          className="secondary"
          disabled={offset + shown >= total}
          onClick={() => setOffset(offset + PAGE)}
        >
          Next
        </button>
      </div>
    </div>
  );
}
