/**
 * The Report: one exam's breakdown at a time, the way the exam reviews read
 * them.
 *
 * For the chosen exam: how deep its questions go on Bloom's taxonomy, whether
 * it clears the bar for its certification level, how that splits across the
 * workshops, where each question sits in review, what to do about it, and
 * every question at its level.
 *
 * All the arithmetic is the server's (`core/report.py`). This pane only
 * draws. The bar check and the findings in particular are not recomputed
 * here: two copies of the rules would disagree the first time one changed,
 * and the one on screen would be the one nobody tested.
 */
import { useCallback, useEffect, useMemo, useState } from "react";

import { api, ApiError, type Report, type ReportExam, type ReportSummary } from "./api";

const pct = (part: number, whole: number) => (whole ? Math.round((part / whole) * 100) : 0);

/** Which step of the ramp a level takes — its place in Bloom's order. */
function tone(levels: string[], level: string): number {
  const i = levels.indexOf(level);
  return i < 0 ? 0 : i + 1;
}

function BloomBar({ levels, summary, tall = false }: {
  levels: string[];
  summary: ReportSummary;
  tall?: boolean;
}) {
  const n = summary.questions;
  const label = levels.map((l) => `${l} ${summary.byBloom[l] ?? 0}`).join(", ");
  return (
    <div className={"bloom-bar" + (tall ? " tall" : "")} role="img" aria-label={label}>
      {levels.map((level) => {
        const v = summary.byBloom[level] ?? 0;
        if (!v) return null;
        return (
          <span
            key={level}
            className={`bloom-seg tone-${tone(levels, level)}`}
            style={{ flexGrow: v }}
            title={`${level}: ${v} (${pct(v, n)}%)`}
          >
            {v / n > 0.08 ? v : ""}
          </span>
        );
      })}
    </div>
  );
}

function Tiles({ exam }: { exam: ReportExam }) {
  const n = exam.questions;
  const tiles = [
    { k: "Questions", c: "indigo", v: String(n), s: exam.exam ? `${exam.exam.pool} in the course file` : "in the bank" },
    { k: "Apply or above", c: "teal", v: `${pct(exam.applyPlus, n)}%`, s: `${exam.applyPlus} of ${n}` },
    { k: "Analyze or above", c: "blue", v: `${pct(exam.analyzePlus, n)}%`, s: `${exam.analyzePlus} of ${n}` },
    { k: "Scenario-led", c: "violet", v: `${pct(exam.scenarioLed, n)}%`, s: `${exam.scenarioLed} set a situation` },
    exam.exam
      ? {
          k: "Draw headroom",
          c: "amber",
          v: `${pct(exam.exam.pool - exam.exam.draw, exam.exam.pool)}%`,
          s: `${exam.exam.draw} drawn from ${exam.exam.pool}`,
        }
      : { k: "Draw headroom", c: "amber", v: "–", s: "course file not read" },
    { k: "Approved", c: "green", v: String(exam.byStatus.approved ?? 0), s: `of ${n} questions` },
  ];
  return (
    <div className="report-tiles">
      {tiles.map((t) => (
        <div className={`report-tile c-${t.c}`} key={t.k}>
          <div className="k">{t.k}</div>
          <div className="v">{t.v}</div>
          <div className="s">{t.s}</div>
        </div>
      ))}
    </div>
  );
}

function BarCheck({ exam }: { exam: ReportExam }) {
  const bar = exam.bar;
  if (!bar) {
    return (
      <p className="muted report-none">
        {exam.level
          ? `No bar is defined for Level ${exam.level.number}.`
          : "This course states no level, so it is not scored against a bar. A try-it lab is not a rung on the certification ladder."}
      </p>
    );
  }
  return (
    <>
      <div className={"report-verdict " + (bar.clears ? "ok" : "bad")}>
        {bar.clears ? "Clears its bar" : "Misses its bar"}
      </div>
      <table className="report-criteria">
        <thead>
          <tr>
            <th>Criterion</th>
            <th>This exam</th>
            <th>Bar</th>
            <th>Result</th>
          </tr>
        </thead>
        <tbody>
          {bar.criteria.map((c) => {
            const onLine = c.got * 100 === c.bar * exam.questions;
            return (
              <tr key={c.criterion}>
                <td>{c.criterion}</td>
                <td className="num-left">
                  {c.percent}% <span className="faint">({c.got})</span>
                </td>
                <td className="num-left">
                  {c.kind === "floor" ? "≥" : "≤"} {c.bar}%
                </td>
                <td className={"result " + (c.ok ? "ok" : "bad")}>
                  {c.ok ? "Pass" : "Miss"}{" "}
                  <span className="faint">
                    {c.ok
                      ? onLine
                        ? "exactly on the line"
                        : ""
                      : c.kind === "floor"
                        ? `${c.gap} question${c.gap === 1 ? "" : "s"} short`
                        : `${c.gap} too many`}
                  </span>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </>
  );
}

const STATUS_NOTE: Record<string, string> = {
  draft: "as imported",
  sme_review: "awaiting a reviewer",
  revised: "reworked, back again",
  approved: "cleared for use",
  rejected: "sent back",
  retired: "withdrawn",
};

const SEVERITY_LABEL: Record<string, string> = {
  act: "Act", review: "Review", minor: "Minor", note: "Note", clear: "Clear",
};

export function ReportPane({ openCourse = "" }: { openCourse?: string }) {
  const [report, setReport] = useState<Report | null>(null);
  const [error, setError] = useState("");
  const [chosen, setChosen] = useState("");
  const [level, setLevel] = useState("All");

  const load = useCallback(() => {
    setError("");
    api
      .report()
      .then(setReport)
      .catch((e: unknown) => setError(e instanceof ApiError ? e.message : String(e)));
  }, []);
  useEffect(load, [load]);

  // The course the app was opened for, else the first exam. Resolved against
  // what the report actually holds so a stale choice cannot leave the pane
  // pointing at an exam that is no longer there.
  const exam = useMemo<ReportExam | null>(() => {
    if (!report || report.exams.length === 0) return null;
    return (
      report.exams.find((e) => e.certificationId === chosen) ??
      report.exams.find((e) => openCourse && e.sourceRef === openCourse) ??
      report.exams[0]
    );
  }, [report, chosen, openCourse]);

  const choose = (id: string) => {
    setChosen(id);
    setLevel("All");
  };

  if (error) {
    return (
      <div className="banner">
        {error}{" "}
        <button className="secondary" onClick={load}>
          Retry
        </button>
      </div>
    );
  }
  if (!report) return <div className="empty">Loading the report…</div>;
  if (!exam) {
    return (
      <div className="report">
        <h2>Report</h2>
        <div className="empty">
          The bank holds no questions yet. Import a course from the Courses tab and its exam will
          appear here.
        </div>
      </div>
    );
  }

  const levels = report.levels;
  const n = exam.questions;
  const mine = report.items.filter((i) => i.certificationId === exam.certificationId);
  const shown = level === "All" ? mine : mine.filter((i) => i.bloom === level);

  return (
    <div className="report">
      <div className="toolbar">
        <h2 className="grow">Report</h2>
        <button className="secondary" onClick={load}>
          Refresh
        </button>
      </div>
      <p className="lede">
        One exam at a time: how deep its questions go on Bloom&rsquo;s taxonomy, whether it clears
        the bar for its certification level, and where every question sits in review.
      </p>

      <div className="report-exams" role="group" aria-label="Exam">
        {report.exams.map((e) => (
          <button
            key={e.certificationId || "unfiled"}
            type="button"
            className="report-exam"
            aria-pressed={e.certificationId === exam.certificationId}
            onClick={() => choose(e.certificationId)}
          >
            <span className="name">{e.name}</span>
            <span className="meta">
              {e.questions} questions · {pct(e.applyPlus, e.questions)}% Apply+
              {e.level ? ` · Level ${e.level.number}` : ""}
            </span>
          </button>
        ))}
      </div>
      {report.emptyCourses > 0 && (
        <p className="faint report-aside">
          {report.emptyCourses} more course{report.emptyCourses === 1 ? "" : "s"} in the bank hold
          no questions.
        </p>
      )}
      {!report.coursesConfigured && (
        <div className="banner warn">
          No Content Manager courses directory is configured, so the level bar and draw headroom
          cannot be shown.
        </div>
      )}

      <div className="report-head">
        <h3>{exam.name}</h3>
        <span className="pill">
          {exam.level ? `Level ${exam.level.number} · ${exam.level.name}` : "No level"}
        </span>
        {exam.sourceRef && <span className="mono faint">{exam.sourceRef}</span>}
      </div>

      <Tiles exam={exam} />

      <section className="report-section">
        <h4>Bloom classification</h4>
        <div className="card">
          <BloomBar levels={levels} summary={exam} tall />
          <div className="bloom-scale" aria-hidden="true">
            <span>shallow</span>
            <span>deep</span>
          </div>
          <div className="bloom-levels">
            {levels.map((l) => {
              const v = exam.byBloom[l] ?? 0;
              return (
                <div className={"bloom-level" + (v ? "" : " zero")} key={l}>
                  <span className={`swatch tone-${tone(levels, l)}`} />
                  <span className="name">{l}</span>
                  <span className="count">
                    {v}
                    <small>{pct(v, n)}%</small>
                  </span>
                </div>
              );
            })}
          </div>
          <div className="bloom-split">
            <span>
              Recall <strong>{pct(exam.recall, n)}%</strong>
            </span>
            <span>
              Apply+ <strong>{pct(exam.applyPlus, n)}%</strong>
            </span>
            <span>
              Analyze+ <strong>{pct(exam.analyzePlus, n)}%</strong>
            </span>
            <span>
              Evaluate <strong>{exam.evaluate}</strong>
            </span>
            <span>
              Multi-select <strong>{exam.multi}</strong>
            </span>
            {exam.exam?.passMark != null && (
              <span>
                Pass mark <strong>{exam.exam.passMark}%</strong>
              </span>
            )}
            {exam.unknownBloom > 0 && (
              <span className="problem-inline">
                {exam.unknownBloom} with an unrecognised level
              </span>
            )}
          </div>
        </div>
      </section>

      <section className="report-section">
        <h4>{exam.bar ? `Level ${exam.bar.level} ${exam.bar.name} bar` : "Certification bar"}</h4>
        <div className="card">
          <BarCheck exam={exam} />
        </div>
      </section>

      <section className="report-section">
        <h4>By workshop</h4>
        <div className="card">
          {exam.topics.map((t) => (
            <div className="report-topic" key={t.topic}>
              <div>
                <div className="name">{t.topic || "(no workshop)"}</div>
                <div className="faint">
                  {t.questions} question{t.questions === 1 ? "" : "s"}
                </div>
              </div>
              <div className="figure">
                <strong>{pct(t.applyPlus, t.questions)}%</strong> Apply+
              </div>
              <BloomBar levels={levels} summary={t} />
            </div>
          ))}
        </div>
      </section>

      <section className="report-section">
        <h4>Review pipeline</h4>
        <div className="report-pipeline">
          {report.statuses.map((s) => {
            const v = exam.byStatus[s.id] ?? 0;
            return (
              <div className={`report-stage st-${s.id}` + (v ? "" : " zero")} key={s.id}>
                <div className="label">{s.label}</div>
                <div className="value">{v}</div>
                <div className="faint">{STATUS_NOTE[s.id] ?? ""}</div>
              </div>
            );
          })}
        </div>
      </section>

      <section className="report-section">
        <h4>Findings</h4>
        <div className="report-findings">
          {exam.findings.map((f) => (
            <div className={`report-finding sev-${f.severity}`} key={f.title}>
              <div className="sev">{SEVERITY_LABEL[f.severity] ?? f.severity}</div>
              <div>
                <div className="title">{f.title}</div>
                <p>{f.detail}</p>
                <p className="action">{f.action}</p>
              </div>
            </div>
          ))}
        </div>
      </section>

      <section className="report-section">
        <h4>Every question, as classified</h4>
        <div className="report-filter" role="group" aria-label="Filter by Bloom level">
          <button
            type="button"
            className="report-chip"
            aria-pressed={level === "All"}
            onClick={() => setLevel("All")}
          >
            All {mine.length}
          </button>
          {levels.map((l) => {
            const c = mine.filter((i) => i.bloom === l).length;
            if (!c) return null;
            return (
              <button
                key={l}
                type="button"
                className="report-chip"
                aria-pressed={level === l}
                onClick={() => setLevel(l)}
              >
                <span className={`swatch tone-${tone(levels, l)}`} />
                {l} {c}
              </button>
            );
          })}
        </div>
        <div className="card report-table">
          <table>
            <thead>
              <tr>
                <th>#</th>
                <th>Bloom</th>
                <th>Workshop</th>
                <th>Status</th>
                <th title="Opens with a scenario">Scen.</th>
                <th>Question</th>
              </tr>
            </thead>
            <tbody>
              {shown.map((q) => (
                <tr key={q.id}>
                  <td className="num">{q.poolOrder >= 0 ? q.poolOrder + 1 : "–"}</td>
                  <td>
                    <span className={`bloom-pill tone-${tone(levels, q.bloom)}`}>{q.bloom}</span>
                  </td>
                  <td className="muted nowrap">{q.topic}</td>
                  <td>
                    <span className={`pill ${q.status}`}>
                      {report.statuses.find((s) => s.id === q.status)?.label ?? q.status}
                    </span>
                  </td>
                  <td className={"scen" + (q.scenario ? " yes" : "")}>{q.scenario ? "✓" : "–"}</td>
                  <td>
                    <span className="stem">{q.stem}</span>
                    {q.multi && <span className="pill report-multi">select all</span>}
                    <div className="mono faint">{q.id}</div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="faint report-count" aria-live="polite">
          {level === "All"
            ? `Showing all ${mine.length} questions`
            : `Showing ${shown.length} of ${mine.length}, ${level} only`}
        </p>
      </section>
    </div>
  );
}
