import { useCallback, useEffect, useRef, useState } from "react";

import {
  api,
  ApiError,
  type ResultsAnalysis,
  type ResultsExam,
  type ResultsImport,
  type ResultsItem,
} from "./api";
import { Formatted } from "./inlineFormat";

/**
 * How each question performs with real candidates.
 *
 * The results Sheet's Detail tab is imported as a CSV (emails are never
 * kept); every question then shows its % correct, whether it separates
 * strong candidates from weak ones, and how often each option is picked.
 * Below a minimum number of attempts the numbers are shown but not judged.
 */
export function ResultsPane() {
  const [analysis, setAnalysis] = useState<ResultsAnalysis | null>(null);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);
  const [onlyFlagged, setOnlyFlagged] = useState(false);
  const file = useRef<HTMLInputElement>(null);

  const load = useCallback(() => {
    api
      .resultsAnalysis()
      .then((a) => {
        setAnalysis(a);
        setError("");
      })
      .catch((e: unknown) => setError(e instanceof ApiError ? e.message : String(e)));
  }, []);

  useEffect(load, [load]);

  async function importFile(f: File) {
    setBusy(true);
    setError("");
    setNotice("");
    try {
      const r: ResultsImport = await api.importResults(await readText(f));
      setNotice(
        `Imported ${r.rows} answers from ${r.attempts} attempt${r.attempts === 1 ? "" : "s"}` +
          ` (${r.added} new). The bank now holds ${r.totalResponses}.`,
      );
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
          accept=".csv,text/csv"
          aria-label="Results CSV file"
          style={{ display: "none" }}
          onChange={(e) => {
            const f = e.target.files?.[0];
            if (f) void importFile(f);
          }}
        />
        <button className="info" disabled={busy} onClick={() => file.current?.click()}>
          {busy ? "Importing…" : "Import results CSV"}
        </button>
      </div>

      <p className="muted results-how">
        From the results Sheet: open the <strong>Detail</strong> tab, then{" "}
        <strong>File › Download › Comma-separated values</strong>, and import that file here.
        Importing it again later adds only the new attempts. Candidates&rsquo; emails in the
        file are never kept.
      </p>

      {error && <div className="banner">{error}</div>}
      {notice && (
        <div className="banner ok-note" role="status">
          {notice}
        </div>
      )}

      {analysis && exams.length === 0 && (
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
