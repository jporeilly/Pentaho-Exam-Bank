/**
 * The results database: a separate SQLite file the Results tab's records are
 * exported to, administered here beside the bank's own backups and deletion.
 *
 * Append copies the records that pass the filters (the same filter bar as the
 * Results tab); records already in the file are skipped. Truncate and delete
 * are count-first: the number is shown on the button, a checkbox must be
 * ticked, the server refuses if the count moved, and a safety backup is taken
 * before anything goes.
 */
import { useCallback, useEffect, useState } from "react";

import {
  api,
  ApiError,
  NO_RESULTS_FILTERS,
  type ResultsAttempts,
  type ResultsDbDeletePlan,
  type ResultsDbStatus,
  type ResultsFilters,
  type ResultsSchedule,
} from "./api";
import { filtersActive, FilterBar } from "./ResultsPane";

const KEY = "resultsDbPath";

function remembered(): string {
  try {
    return localStorage.getItem(KEY) ?? "";
  } catch {
    return "";
  }
}

export function ResultsDbAdmin() {
  const [path, setPath] = useState(remembered);
  const [status, setStatus] = useState<ResultsDbStatus | null>(null);
  const [options, setOptions] = useState<ResultsAttempts["options"] | undefined>();
  const [filters, setFilters] = useState<ResultsFilters>(NO_RESULTS_FILTERS);
  const [plan, setPlan] = useState<ResultsDbDeletePlan | null>(null);
  const [sure, setSure] = useState(false);
  const [sureAll, setSureAll] = useState(false);
  const [error, setError] = useState("");
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [label, setLabel] = useState("");
  const [sched, setSched] = useState<ResultsSchedule | null>(null);
  const [workbook, setWorkbook] = useState("");
  const [time, setTime] = useState("02:00");
  const [enabled, setEnabled] = useState(false);

  const refresh = useCallback(
    (p: string) =>
      api
        .resultsDbStatus(p)
        .then((s) => {
          setStatus(s);
          setError("");
        })
        .catch((e: unknown) => {
          setStatus(null);
          setError(e instanceof ApiError ? e.message : String(e));
        }),
    [],
  );

  useEffect(() => {
    void refresh(path);
    api
      .resultsSchedule()
      .then((r) => {
        if (!r || typeof r.time !== "string") return;
        setSched(r);
        setWorkbook(r.workbookPath ?? "");
        setTime(r.time);
        setEnabled(Boolean(r.enabled));
        if (!path && r.targetPath) setPath(r.targetPath);
      })
      .catch(() => undefined);
    api.resultsAttempts().then((a) => setOptions(a?.options)).catch(() => undefined);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // A count describes one selection; a new filter or file makes it stale.
  useEffect(() => {
    setPlan(null);
    setSure(false);
  }, [filters, path]);

  const target = path.trim() || status?.defaultPath || "";

  async function run<T>(work: () => Promise<T>, after: (r: T) => string) {
    setBusy(true);
    setError("");
    setNote("");
    try {
      const r = await work();
      setNote(after(r));
      try {
        localStorage.setItem(KEY, path.trim());
      } catch {
        /* a remembered path is a convenience */
      }
      await refresh(path);
      api.resultsSchedule().then((r) => r && typeof r.time === "string" && setSched(r)).catch(() => undefined);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  const n = (v: number, one: string) => `${v} ${one}${v === 1 ? "" : "s"}`;
  const filtered = filtersActive(filters);

  return (
    <section className="settings-section results-db">
      <h3>Results database</h3>
      <p className="faint section-hint">
        A separate SQLite file the Results tab&rsquo;s attempts and answers are exported to, kept
        apart from the question bank. Candidates are anonymous ids; no names or emails are in it.
      </p>

      {error && <div className="banner">{error}</div>}
      {note && (
        <div className="banner ok-note" role="status">
          {note}
        </div>
      )}

      <div className="toolbar">
        <label className="field grow">
          <span className="field-label">File</span>
          <input
            aria-label="Results database file"
            className="mono"
            value={path}
            placeholder={status?.defaultPath ?? "C:\\path\\to\\exam_results.db"}
            onChange={(e) => setPath(e.target.value)}
          />
        </label>
        <button className="secondary" disabled={busy} onClick={() => void refresh(path)}>
          Check file
        </button>
      </div>

      {status && (
        <dl className="paths">
          <dt>Holds</dt>
          <dd>
            {status.exists
              ? `${n(status.attempts, "attempt")}, ${n(status.answers, "answer")} — ${status.sizeKb} KB`
              : "No file yet; the first append creates it."}
          </dd>
        </dl>
      )}

      <h4>Daily load from the results workbook</h4>
      <p className="faint">
        Imports the downloaded results workbook (.xlsx) and appends its new attempts to the file
        above, once a day at the time set, while the app is open (or at the next check if it was
        closed then). Only new attempts are added, so a repeat load changes nothing. Replace the
        workbook at this path each day with the Sheet&rsquo;s latest download.
      </p>
      <div className="toolbar">
        <label className="field grow">
          <span className="field-label">Workbook (.xlsx)</span>
          <input
            aria-label="Results workbook path"
            className="mono"
            value={workbook}
            placeholder="C:\Users\you\Downloads\results.xlsx"
            onChange={(e) => setWorkbook(e.target.value)}
          />
        </label>
        <label className="field">
          <span className="field-label">Time</span>
          <input type="time" aria-label="Daily load time" value={time} onChange={(e) => setTime(e.target.value)} />
        </label>
        <label className="checkbox-inline">
          <input type="checkbox" checked={enabled} onChange={(e) => setEnabled(e.target.checked)} /> Load daily
        </label>
      </div>
      <div className="toolbar">
        <button
          className="secondary info"
          disabled={busy}
          onClick={() =>
            run(
              () => api.saveResultsSchedule({ enabled, workbookPath: workbook, targetPath: path.trim() || status?.defaultPath || "", time }),
              (r) => {
                setSched(r);
                return enabled ? `Daily load saved: every day at ${r.time}.` : "Saved. The daily load is off.";
              },
            )
          }
        >
          Save schedule
        </button>
        <button
          className="add"
          disabled={busy || !sched?.workbookPath}
          title="Load the saved workbook now; save the schedule first if you changed the path"
          onClick={() => run(() => api.runResultsLoad(), (r) => r.message)}
        >
          Load now
        </button>
      </div>
      {sched?.lastAttempt && (
        <p className={sched.lastOk ? "faint" : "banner"} role="status">
          Last load {sched.lastAttempt.replace("T", " ")}: {sched.lastMessage}
        </p>
      )}

      <h4>Add records</h4>
      <p className="faint">
        Copies the Results records that pass these filters into the file. Records it already holds
        are skipped, not overwritten.
      </p>
      <FilterBar filters={filters} onChange={setFilters} options={options} />
      <div className="toolbar">
        <button
          className="add"
          disabled={busy}
          onClick={() =>
            run(
              () => api.resultsDbAppend(path.trim(), filters),
              (r) =>
                `Added ${n(r.addedAttempts, "attempt")} and ${n(r.addedAnswers, "answer")}` +
                (r.skippedAttempts ? ` (${r.skippedAttempts} already there)` : "") +
                `. The file now holds ${n(r.totalAttempts, "attempt")}.`,
            )
          }
        >
          {filtered ? "Append matching records" : "Append all records"}
        </button>
      </div>

      <h4>Backups</h4>
      <div className="toolbar">
        <input
          aria-label="Results database backup label"
          value={label}
          placeholder="What is this backup for?"
          onChange={(e) => setLabel(e.target.value)}
        />
        <button
          className="add"
          disabled={busy || !status?.exists}
          onClick={() =>
            run(
              () => api.resultsDbBackup(path.trim(), label),
              (r) => {
                setLabel("");
                return `Backed up as ${r.name}.`;
              },
            )
          }
        >
          Back up results database
        </button>
      </div>
      {status && (status.backups?.length ?? 0) > 0 && (
        <table>
          <tbody>
            {status.backups.map((b) => (
              <tr key={b.name}>
                <td className="mono">{b.name}</td>
                <td className="faint">{b.created}</td>
                <td className="faint" style={{ textAlign: "right" }}>
                  {b.sizeKb} KB
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      <h4>Delete records</h4>
      <p className="faint">
        Uses the filters above. Nothing is deleted until you have seen the count; a backup is
        taken first.
      </p>
      <div className="toolbar">
        <button
          className="secondary info"
          disabled={busy || !status?.exists || !filtered}
          onClick={async () => {
            setBusy(true);
            setError("");
            setNote("");
            try {
              setPlan(await api.resultsDbDeletePreview(path.trim(), filters));
              setSure(false);
            } catch (e) {
              setPlan(null);
              setError(e instanceof ApiError ? e.message : String(e));
            } finally {
              setBusy(false);
            }
          }}
        >
          Count matching records
        </button>
        {!filtered && <span className="faint">Set a filter first; to remove everything use Truncate.</span>}
      </div>
      {plan && (
        <div className="plan card">
          {plan.attempts === 0 ? (
            <p>Nothing in the file matches those filters.</p>
          ) : (
            <>
              <h3>
                {n(plan.attempts, "attempt")} ({n(plan.answers, "answer")}) would be deleted
              </h3>
              <ul className="sample">
                {plan.sample.map((s) => (
                  <li key={s.attemptId}>
                    {s.day || "–"} · {s.candidateId || "no candidate"} · {s.courseId}
                  </li>
                ))}
              </ul>
              <label className="check danger-check">
                <input type="checkbox" checked={sure} onChange={(e) => setSure(e.target.checked)} />
                Yes — delete these {plan.attempts} from the results database
              </label>
              <div className="toolbar">
                <button
                  className="danger"
                  disabled={busy || !sure}
                  onClick={() =>
                    run(
                      () => api.resultsDbDelete(path.trim(), filters, plan.attempts),
                      (r) => {
                        setPlan(null);
                        setSure(false);
                        return (
                          `Deleted ${n(r.removedAttempts, "attempt")} and ${n(r.removedAnswers, "answer")}. ` +
                          `Safety backup: ${r.safetyBackup}.`
                        );
                      },
                    )
                  }
                >
                  {busy ? "Deleting…" : `Delete ${plan.attempts}`}
                </button>
                <span className="faint">Undo by restoring the safety backup file.</span>
              </div>
            </>
          )}
        </div>
      )}

      <h4>Truncate</h4>
      <p className="faint">Removes every record from the results database; the file stays. A backup is taken first.</p>
      <label className="check danger-check">
        <input
          type="checkbox"
          checked={sureAll}
          disabled={!status?.exists || status.attempts === 0}
          onChange={(e) => setSureAll(e.target.checked)}
        />
        Yes — remove all {status?.attempts ?? 0} attempts from the results database
      </label>
      <div className="toolbar">
        <button
          className="danger"
          disabled={busy || !sureAll || !status?.exists || status.attempts === 0}
          onClick={() =>
            run(
              () => api.resultsDbTruncate(path.trim(), status?.attempts ?? 0),
              (r) => {
                setSureAll(false);
                return (
                  `Removed ${n(r.removedAttempts, "attempt")} and ${n(r.removedAnswers, "answer")}. ` +
                  `Safety backup: ${r.safetyBackup}.`
                );
              },
            )
          }
        >
          Truncate results database
        </button>
        <span className="faint">{target && `File: ${target}`}</span>
      </div>
    </section>
  );
}
