import { useCallback, useEffect, useRef, useState } from "react";

import {
  api,
  ApiError,
  type Certification,
  type Question,
  type QuestionFilters,
} from "./api";
import { QuestionEditor } from "./QuestionEditor";
import { statusLabel, useVocabulary } from "./vocabulary";

// Until Settings answers. "Questions per page" was saved there and never read.
const DEFAULT_PAGE = 25;

/**
 * Browse what is in the bank.
 *
 * The 395 questions adopted from the courses had no editing tool anywhere
 * before this: the bank never kept what it exported, and the Content Editor
 * deliberately refuses to touch `questions`. This is the first screen that
 * shows them.
 */
export function BankPane({
  openCourse = "",
  onChanged,
}: {
  /** A course slug the app was opened for; its questions are shown first. */
  openCourse?: string;
  onChanged?: () => void;
}) {
  const [certifications, setCertifications] = useState<Certification[]>([]);
  const [questions, setQuestions] = useState<Question[] | null>(null);
  const [total, setTotal] = useState(0);
  const [offset, setOffset] = useState(0);
  const [error, setError] = useState("");

  // The question open in the editor. Held as the OBJECT rather than an id
  // so the editor can render immediately from the row already on screen -
  // fetching by id would blank the panel for a round trip on every click.
  const [editing, setEditing] = useState<Question | null>(null);

  // Guards against an out-of-order response overwriting a newer one.
  const latest = useRef(0);

  const [text, setText] = useState("");
  const [certification, setCertification] = useState("");
  const [status, setStatus] = useState("");
  // Course order by default. `pool_order` is the position each question held
  // in its course's exam.json, and the authors write a pool lab by lab, so
  // this is the order the workshops teach it - and topics come out as
  // contiguous blocks without the bank knowing anything about labs.
  const [sort, setSort] = useState<"course" | "updated">("course");
  const [pageSize, setPageSize] = useState(DEFAULT_PAGE);
  // Export in any format, starting on the default set in Settings.
  const [exportFormat, setExportFormat] = useState("csv");
  const [exportFormats, setExportFormats] = useState([{ format: "csv", label: "CSV" }]);
  const vocabulary = useVocabulary();

  useEffect(() => {
    api
      .settings()
      .then((r) => {
        const n = r?.settings?.questions_per_page;
        if (typeof n === "number" && n > 0) setPageSize(n);
        const formats = r?.choices?.exportFormats;
        if (Array.isArray(formats) && formats.length) setExportFormats(formats);
        const preferred = r?.settings?.default_export_format;
        if (preferred) setExportFormat(preferred);
      })
      .catch(() => {});
  }, []);

  const filters: QuestionFilters = {
    text,
    certification_id: certification,
    status,
    sort,
    limit: pageSize,
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
    // `sort` was missing here, so on the first page (offset already 0)
    // switching Course order / Recently updated changed nothing on screen.
  }, [text, certification, status, sort, offset, pageSize]);

  useEffect(load, [load]);

  // A certification records the course it was adopted from in sourceRef, so
  // "open on this course" is "filter to the certification that came from it".
  // Applied once, so clearing the filter afterwards sticks rather than
  // snapping back on the next render.
  const applied = useRef(false);
  useEffect(() => {
    api
      .certifications()
      .then((list) => {
        setCertifications(list);
        if (applied.current || !openCourse) return;
        applied.current = true;
        const match = list.find((c) => c.sourceRef === openCourse);
        if (match) setCertification(match.id);
      })
      .catch(() => setCertifications([]));
  }, [openCourse]);

  // Opened for a course the bank has never adopted. Saying so beats showing
  // an unexplained empty table, and the questions do exist — in the course's
  // exam.json, which nothing has brought in yet.
  const adopted = certifications.some((c) => c.sourceRef === openCourse);
  const notAdopted = Boolean(openCourse) && certifications.length > 0 && !adopted;

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
        <select
          value={sort}
          onChange={(e) =>
            changeFilter(() => setSort(e.target.value as "course" | "updated"))
          }
          title="Course order follows the workshops; the pool was authored lab by lab"
        >
          <option value="course">Course order</option>
          <option value="updated">Recently updated</option>
        </select>
        <select value={status} onChange={(e) => changeFilter(() => setStatus(e.target.value))}>
          <option value="">Any status</option>
          {vocabulary.statuses.map((s) => (
            <option key={s} value={s}>
              {statusLabel(vocabulary, s)}
            </option>
          ))}
        </select>
        <select
          value={exportFormat}
          onChange={(e) => setExportFormat(e.target.value)}
          title="The format to export in. The default is set in Settings."
          aria-label="Export format"
        >
          {exportFormats.map((f) => (
            <option key={f.format} value={f.format}>
              {f.label}
            </option>
          ))}
        </select>
        <a href={api.exportUrl(exportFormat, { text, certification_id: certification, status })}>
          <button className="secondary">Export</button>
        </a>
      </div>

      {notAdopted && (
        <div className="banner warn">
          <strong>
            <code>{openCourse}</code> has not been adopted into the bank yet.
          </strong>{" "}
          Its questions are still only in the course&rsquo;s{" "}
          <code>exam.json</code>. Bring them in with{" "}
          <code className="mono">
            venv\Scripts\python.exe scripts\migrate_pcm_exams.py {openCourse}
          </code>
          , which preserves their ids and order.
        </div>
      )}

      {error && <div className="banner">{error}</div>}

      {editing && (
        <QuestionEditor
          question={editing}
          onSaved={(q) => {
            // Patch the row in place rather than reloading: a reload
            // re-sorts by updated_at and the question the user is
            // editing jumps somewhere else on the page. Matched on the id
            // it had when opened too: moving a course question to another
            // module renames it, and the row must follow.
            const was = editing?.id;
            setQuestions(
              (rows) => rows?.map((r) => (r.id === q.id || r.id === was ? q : r)) ?? rows,
            );
            setEditing(q);
            onChanged?.();
          }}
          onDeleted={(id) => {
            setQuestions((rows) => rows?.filter((r) => r.id !== id) ?? rows);
            setTotal((n) => Math.max(0, n - 1));
            setEditing(null);
            onChanged?.();
          }}
          onClose={() => setEditing(null)}
        />
      )}

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
                <tr
                  key={q.id}
                  className={editing?.id === q.id ? "q-row selected" : "q-row"}
                  onClick={() => setEditing(q)}
                >
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
                    <button
                      className="secondary"
                      onClick={(e) => {
                        // The row opens the editor; this button must not
                        // also open it behind the confirm dialog.
                        e.stopPropagation();
                        remove(q);
                      }}
                    >
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
          onClick={() => setOffset(Math.max(0, offset - pageSize))}
        >
          Previous
        </button>
        <button
          className="secondary"
          disabled={offset + shown >= total}
          onClick={() => setOffset(offset + pageSize)}
        >
          Next
        </button>
      </div>
    </div>
  );
}
