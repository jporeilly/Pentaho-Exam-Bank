import { useCallback, useEffect, useRef, useState } from "react";

import {
  api,
  ApiError,
  NO_RESULTS_FILTERS,
  type ResultsAnalysis,
  type ResultsAttempt,
  type ResultsAttempts,
  type ResultsExam,
  type ResultsFilters,
  type ResultsImport,
  type ResultsItem,
} from "./api";
import { Formatted } from "./inlineFormat";
import { TopicReport } from "./TopicReport";

/**
 * How each question performs with real candidates.
 *
 * The results workbook (.xlsx, every tab) or the Detail tab as a CSV is
 * imported - names and emails are never kept. Every attempt is listed on its
 * own, so a candidate who sat an exam twice shows twice, as attempt 1 and 2.
 * Every question then shows its % correct, whether it separates strong
 * candidates from weak ones, and how often each option is picked; below a
 * minimum number of attempts the numbers are shown but not judged. The
 * filters (exam dates, course, candidate, result, attempt number) narrow
 * the attempt list and the question numbers together.
 */
export function ResultsPane() {
  const [analysis, setAnalysis] = useState<ResultsAnalysis | null>(null);
  const [attempts, setAttempts] = useState<ResultsAttempts | null>(null);
  const [filters, setFilters] = useState<ResultsFilters>(NO_RESULTS_FILTERS);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);
  const [onlyFlagged, setOnlyFlagged] = useState(false);
  const [service, setService] = useState<{ configured: boolean; env: string } | null>(null);
  const [refresh, setRefresh] = useState(0);
  const file = useRef<HTMLInputElement>(null);

  const load = useCallback(() => {
    Promise.all([api.resultsAnalysis("", filters), api.resultsAttempts(filters)])
      .then(([a, at]) => {
        setAnalysis(a);
        setAttempts(at);
        setRefresh((n) => n + 1);
        setError("");
      })
      .catch((e: unknown) => setError(e instanceof ApiError ? e.message : String(e)));
  }, [filters]);

  useEffect(load, [load]);
  useEffect(() => {
    api.resultsService().then(setService).catch(() => setService(null));
  }, []);

  async function pull() {
    setBusy(true);
    setError("");
    setNotice("");
    try {
      const r = await api.pullResults();
      setNotice(
        `Pulled ${r.rows} answers from ${r.attempts} attempt${r.attempts === 1 ? "" : "s"}` +
          ` (${r.added} new). The bank now holds ${r.totalResponses}.`,
      );
      load();
    } catch (e: unknown) {
      setError(e instanceof ApiError ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  async function importFile(f: File) {
    setBusy(true);
    setError("");
    setNotice("");
    try {
      if (/\.xlsx$/i.test(f.name)) {
        const r = await api.importResultsWorkbook(await readBase64(f));
        const tabs = r.sheets.filter((s) => s.kind !== "ignored").length;
        setNotice(
          `Read ${tabs} tab${tabs === 1 ? "" : "s"}: ${r.attempts} attempt${r.attempts === 1 ? "" : "s"}` +
            ` (${r.addedAttempts} new) and ${r.answers} answers (${r.added} new).` +
            ` The bank now holds ${r.totalAttempts} attempts.`,
        );
      } else {
        const r: ResultsImport = await api.importResults(await readText(f));
        setNotice(
          `Imported ${r.rows} answers from ${r.attempts} attempt${r.attempts === 1 ? "" : "s"}` +
            ` (${r.added} new). The bank now holds ${r.totalResponses}.`,
        );
      }
      load();
    } catch (e: unknown) {
      setError(e instanceof ApiError ? e.message : String(e));
    } finally {
      setBusy(false);
      if (file.current) file.current.value = "";
    }
  }

  const exams = analysis?.exams ?? [];

  return (
    <div>
      <div className="toolbar">
        <h2 className="grow">Results</h2>
        <label className="checkbox-inline">
          <input
            type="checkbox"
            checked={onlyFlagged}
            onChange={(e) => setOnlyFlagged(e.target.checked)}
          />{" "}
          Only flagged questions
        </label>
        <input
          ref={file}
          type="file"
          accept=".xlsx,.csv,text/csv,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
          aria-label="Results file"
          style={{ display: "none" }}
          onChange={(e) => {
            const f = e.target.files?.[0];
            if (f) void importFile(f);
          }}
        />
        <button
          className="secondary info"
          disabled={busy || !service?.configured}
          onClick={pull}
          title={
            service?.configured
              ? "Read the results straight from the results service"
              : `Needs the results service's admin secret (${service?.env ?? "an environment variable"})`
          }
        >
          Pull from results service
        </button>
        <button className="info" disabled={busy} onClick={() => file.current?.click()}>
          {busy ? "Working…" : "Import results workbook"}
        </button>
      </div>

      <p className="muted results-how">
        From the results Sheet: <strong>File › Download › Microsoft Excel (.xlsx)</strong>, and
        import that workbook here: every course tab&rsquo;s attempts and the Detail tab&rsquo;s
        answers come in together. (The Detail tab alone, downloaded as a CSV, still works.)
        Importing again later adds only the new attempts. Names and emails in the file are never
        kept; a candidate is shown by their anonymous id.
      </p>

      <FilterBar filters={filters} onChange={setFilters} options={attempts?.options} />

      {attempts && attempts.attempts.length > 0 && <AttemptList data={attempts} />}
      {attempts && attempts.attempts.length === 0 && attempts.options.courses.length > 0 && (
        <div className="card empty">No attempts match these filters.</div>
      )}

      {error && <div className="banner">{error}</div>}
      {notice && (
        <div className="banner ok-note" role="status">
          {notice}
        </div>
      )}

      <TopicReport filters={filters} refresh={refresh} />

      {analysis && exams.length === 0 && !filtersActive(filters) && (
        <div className="card empty">No results imported yet.</div>
      )}

      {exams.map((exam) => (
        <ExamResults
          key={exam.courseId}
          exam={exam}
          minAttempts={analysis!.minAttempts}
          onlyFlagged={onlyFlagged}
        />
      ))}
    </div>
  );
}

/** A picked file's text. FileReader rather than File.text(), which older
 *  webviews (and the test DOM) lack. */
function readText(f: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result ?? ""));
    reader.onerror = () => reject(reader.error);
    reader.readAsText(f);
  });
}

/** A picked file as base64 (the API takes JSON, so the bytes travel as text). */
function readBase64(f: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => {
      const bytes = new Uint8Array(reader.result as ArrayBuffer);
      let binary = "";
      for (let i = 0; i < bytes.length; i += 0x8000) {
        binary += String.fromCharCode(...bytes.subarray(i, i + 0x8000));
      }
      resolve(btoa(binary));
    };
    reader.onerror = () => reject(reader.error);
    reader.readAsArrayBuffer(f);
  });
}

export const filtersActive = (f: ResultsFilters) =>
  Object.keys(NO_RESULTS_FILTERS).some(
    (k) => f[k as keyof ResultsFilters] !== NO_RESULTS_FILTERS[k as keyof ResultsFilters],
  );

const isoDay = (d: Date) =>
  `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;

/** [from, to] for "the last n days", today included. */
function lastDays(n: number): [string, string] {
  const to = new Date();
  const from = new Date();
  from.setDate(to.getDate() - (n - 1));
  return [isoDay(from), isoDay(to)];
}

const ordinal = (n: number) =>
  n % 100 >= 11 && n % 100 <= 13
    ? "th"
    : (({ 1: "st", 2: "nd", 3: "rd" } as Record<number, string>)[n % 10] ?? "th");

/**
 * Filters for the attempt list and the question numbers below it. The two
 * date boxes open the browser's calendar; the presets fill both. The choices
 * come from every attempt, so narrowing one filter never empties another's.
 */
export function FilterBar({
  filters,
  onChange,
  options,
}: {
  filters: ResultsFilters;
  onChange: (f: ResultsFilters) => void;
  options: ResultsAttempts["options"] | undefined;
}) {
  if (!options || options.courses.length === 0) return null;
  const set = (patch: Partial<ResultsFilters>) => onChange({ ...filters, ...patch });
  const preset = (n: number) => {
    const [dateFrom, dateTo] = lastDays(n);
    set({ dateFrom, dateTo });
  };
  return (
    <div className="card results-filters" role="group" aria-label="Filter results">
      <div className="results-filter-row">
      <label className="field">
        <span>From</span>
        <input
          type="date"
          aria-label="From date"
          value={filters.dateFrom}
          max={filters.dateTo || undefined}
          onChange={(e) => set({ dateFrom: e.target.value })}
        />
      </label>
      <label className="field">
        <span>To</span>
        <input
          type="date"
          aria-label="To date"
          value={filters.dateTo}
          min={filters.dateFrom || undefined}
          onChange={(e) => set({ dateTo: e.target.value })}
        />
      </label>
      <div className="field">
        <span aria-hidden="true">&nbsp;</span>
        <div className="results-presets">
          <button className="secondary" onClick={() => preset(7)}>Last 7 days</button>
          <button className="secondary" onClick={() => preset(30)}>Last 30 days</button>
          <button className="secondary" onClick={() => set({ dateFrom: "", dateTo: "" })}>All dates</button>
        </div>
      </div>
      </div>
      <div className="results-filter-row">
      <label className="field">
        <span>Course</span>
        <select aria-label="Course" value={filters.course} onChange={(e) => set({ course: e.target.value })}>
          <option value="">All courses</option>
          {options.courses.map((c) => (
            <option key={c.id} value={c.id}>{c.name}</option>
          ))}
        </select>
      </label>
      <label className="field">
        <span>Candidate</span>
        <input
          list="results-candidates"
          aria-label="Candidate"
          placeholder="Any (cand_…)"
          value={filters.candidate}
          onChange={(e) => set({ candidate: e.target.value })}
        />
        <datalist id="results-candidates">
          {options.candidates.map((c) => <option key={c} value={c} />)}
        </datalist>
      </label>
      <label className="field">
        <span>Result</span>
        <select
          aria-label="Result"
          value={filters.passed}
          onChange={(e) => set({ passed: e.target.value as ResultsFilters["passed"] })}
        >
          <option value="">Pass and fail</option>
          <option value="pass">Passed</option>
          <option value="fail">Failed</option>
        </select>
      </label>
      <label className="field">
        <span>Attempt</span>
        <select
          aria-label="Attempt number"
          value={filters.attemptNo}
          onChange={(e) => set({ attemptNo: Number(e.target.value) })}
        >
          <option value={0}>Any attempt</option>
          {Array.from({ length: Math.max(options.maxAttemptNo, 1) }, (_, i) => i + 1).map((n) => (
            <option key={n} value={n}>
              {n === 1 ? "1st (first sitting)" : `${n}${ordinal(n)} (a retake)`}
            </option>
          ))}
        </select>
      </label>
      {filtersActive(filters) && (
        <div className="field">
          <span aria-hidden="true">&nbsp;</span>
          <button className="secondary" onClick={() => onChange(NO_RESULTS_FILTERS)}>
            Clear filters
          </button>
        </div>
      )}
      </div>
    </div>
  );
}

/** One row per attempt, newest first. A retake is its own row, marked "2 of 3". */
function AttemptList({ data }: { data: ResultsAttempts }) {
  const s = data.summary;
  return (
    <section className="results-exam">
      <div className="report-head">
        <h3>Attempts</h3>
        <span className="muted">
          {s.attempts} attempt{s.attempts === 1 ? "" : "s"}
          {s.candidates > 0 && ` · ${s.candidates} candidate${s.candidates === 1 ? "" : "s"}`}
          {" · "}
          {s.passed} passed · {s.failed} failed
          {s.meanPercentage !== null && ` · mean ${pct(s.meanPercentage)}`}
        </span>
      </div>
      <div className="card report-table">
        <table>
          <thead>
            <tr>
              <th style={{ width: 100 }}>Date</th>
              <th>Course</th>
              <th>Candidate</th>
              <th style={{ width: 90 }}>Attempt</th>
              <th style={{ width: 90, textAlign: "right" }}>Score</th>
              <th style={{ width: 80, textAlign: "right" }}>%</th>
              <th style={{ width: 90 }}>Result</th>
            </tr>
          </thead>
          <tbody>
            {data.attempts.map((a: ResultsAttempt) => (
              <tr key={a.attemptId}>
                <td>{a.day || "–"}</td>
                <td>{a.course}</td>
                <td className="mono faint">{a.candidateId || "–"}</td>
                <td>
                  {a.attemptNo === null ? (
                    "–"
                  ) : (
                    <>
                      {a.attemptNo}
                      {a.ofAttempts !== null && a.ofAttempts > 1 && (
                        <span className="faint"> of {a.ofAttempts}</span>
                      )}
                    </>
                  )}
                </td>
                <td className="num">
                  {a.score === null ? "–" : `${a.score}${a.total !== null ? ` / ${a.total}` : ""}`}
                </td>
                <td className="num">{pct(a.percentage)}</td>
                <td>
                  {a.passed === null ? (
                    "–"
                  ) : (
                    <span className={`pill ${a.passed ? "approved" : "rejected"}`}>
                      {a.passed ? "Passed" : "Failed"}
                    </span>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

const pct = (v: number | null) => (v === null ? "–" : `${Math.round(v * 100)}%`);
const day = (iso: string) => (iso ? iso.slice(0, 10) : "");

function ExamResults({
  exam,
  minAttempts,
  onlyFlagged,
}: {
  exam: ResultsExam;
  minAttempts: number;
  onlyFlagged: boolean;
}) {
  const serious = (it: ResultsItem) => it.flags.some((f) => f.level !== "info");
  const items = onlyFlagged ? exam.items.filter(serious) : exam.items;
  return (
    <section className="results-exam">
      <div className="report-head">
        <h3>{exam.name}</h3>
        <span className="muted">
          {exam.attempts} attempt{exam.attempts === 1 ? "" : "s"} · mean score {pct(exam.meanScore)}
          {exam.firstAttempt && ` · ${day(exam.firstAttempt)} to ${day(exam.lastAttempt)}`} ·{" "}
          {exam.judged} of {exam.items.length} questions have {minAttempts}+ attempts ·{" "}
          {exam.flagged} flagged
        </span>
      </div>
      <div className="card report-table">
        <table>
          <thead>
            <tr>
              <th style={{ width: 110 }}>ID</th>
              <th>Question</th>
              <th style={{ width: 70, textAlign: "right" }}>Attempts</th>
              <th style={{ width: 80, textAlign: "right" }}>Correct</th>
              <th
                style={{ width: 110, textAlign: "right" }}
                title="Does the question separate strong candidates from weak ones? From −1 to 1: above 0.3 is good, below 0.15 weak, below 0 means stronger candidates do worse."
              >
                Discrimination
              </th>
              <th style={{ width: 260 }}>Options picked</th>
            </tr>
          </thead>
          <tbody>
            {items.length === 0 && (
              <tr>
                <td colSpan={6} className="empty">
                  No flagged questions.
                </td>
              </tr>
            )}
            {items.map((it) => (
              <tr key={it.id} className={it.attempts < minAttempts ? "results-thin" : undefined}>
                <td className="mono faint">{it.id}</td>
                <td>
                  {it.stem ? <Formatted text={it.stem} /> : <span className="faint">(not in the bank)</span>}
                  {it.flags.map((f) => (
                    <div key={f.text} className={`results-flag ${f.level}`}>
                      {f.text}
                    </div>
                  ))}
                </td>
                <td className="num">{it.attempts}</td>
                <td className="num">
                  {pct(it.p)}
                  {it.suggestedDifficulty && it.suggestedDifficulty !== it.difficulty && (
                    <div className="faint" title={`Marked ${it.difficulty} in the bank`}>
                      plays {it.suggestedDifficulty.toLowerCase()}
                    </div>
                  )}
                </td>
                <td
                  className="num"
                  title={
                    it.upperP !== null && it.lowerP !== null
                      ? `Strongest quarter: ${pct(it.upperP)} correct; weakest quarter: ${pct(it.lowerP)}`
                      : undefined
                  }
                >
                  {it.discrimination === null ? "–" : it.discrimination.toFixed(2)}
                  {it.upperP !== null && it.lowerP !== null && (
                    <div className="faint">
                      {pct(it.upperP)} / {pct(it.lowerP)}
                    </div>
                  )}
                </td>
                <td>
                  <ul className="results-options">
                    {it.options.map((o) => (
                      <li key={o.text} className={o.correct ? "correct" : "wrong"}>
                        <span className="results-bar" style={{ width: `${Math.round(o.share * 100)}%` }} />
                        <span className="results-opt-text">
                          <Formatted text={o.text} />
                        </span>
                        <span className="results-opt-share">{pct(o.share)}</span>
                      </li>
                    ))}
                  </ul>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}
