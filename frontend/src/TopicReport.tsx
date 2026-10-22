import { useEffect, useState } from "react";

import {
  api,
  ApiError,
  type ResultsFilters,
  type TopicAdvice,
  type TopicReport as Report,
  type TopicReportCourse,
  type TopicRow,
} from "./api";
import { Formatted } from "./inlineFormat";

const pct = (v: number | null) => (v === null ? "–" : `${Math.round(v * 100)}%`);

/**
 * Where candidates go wrong: wrong answers by topic and by module for each
 * course, under the same filters as the rest of the Results tab. A topic is
 * the one the bank holds for the question. The bar is the row's wrong answers
 * against the course's worst row; the rate beside it says how often the row
 * is missed. Rows with too few answers are dimmed, as in the question table.
 * "Analyse with AI" sends the report's numbers (never anything about
 * candidates) to the configured AI provider and shows its reading.
 */
export function TopicReport({ filters, refresh }: { filters: ResultsFilters; refresh: number }) {
  const [report, setReport] = useState<Report | null>(null);
  const [error, setError] = useState("");
  const [by, setBy] = useState<"topics" | "modules">("topics");

  useEffect(() => {
    let live = true;
    api
      .resultsTopics(filters)
      .then((r) => {
        if (live) {
          setReport(r);
          setError("");
        }
      })
      .catch((e: unknown) => live && setError(e instanceof ApiError ? e.message : String(e)));
    return () => {
      live = false;
    };
  }, [filters, refresh]);

  const courses = report?.courses ?? [];
  if (error) return <div className="banner">{error}</div>;
  if (!report || courses.length === 0) return null;

  return (
    <section className="results-exam topic-report">
      <div className="report-head">
        <h3>Where candidates go wrong</h3>
        <span className="muted">
          {report.wrong} wrong of {report.answers} answers
        </span>
        <div className="grow" />
        <div className="topic-seg" role="group" aria-label="Group by">
          <button className={by === "topics" ? "" : "secondary"} onClick={() => setBy("topics")}>
            By topic
          </button>
          <button className={by === "modules" ? "" : "secondary"} onClick={() => setBy("modules")}>
            By module
          </button>
        </div>
      </div>
      {courses.map((c) => (
        <CourseTable key={c.courseId} course={c} by={by} minAnswers={report.minAnswers} />
      ))}
      <AdvicePanel filters={filters} />
    </section>
  );
}

function CourseTable({
  course,
  by,
  minAnswers,
}: {
  course: TopicReportCourse;
  by: "topics" | "modules";
  minAnswers: number;
}) {
  const rows = course[by];
  const most = Math.max(1, ...rows.map((r) => r.wrong));
  return (
    <div className="card report-table topic-course">
      <div className="topic-course-head">
        <strong>{course.name}</strong>
        <span className="muted">
          {course.attempts} attempt{course.attempts === 1 ? "" : "s"} · {course.wrong} wrong of{" "}
          {course.answers} answers ({pct(course.wrongRate)})
        </span>
      </div>
      <table>
        <thead>
          <tr>
            <th>{by === "topics" ? "Topic" : "Module"}</th>
            <th style={{ width: 70, textAlign: "right" }}>Questions</th>
            <th style={{ width: 70, textAlign: "right" }}>Answers</th>
            <th style={{ width: 240 }}>Wrong answers</th>
            <th style={{ width: 80, textAlign: "right" }} title="Wrong answers as a share of the answers given">
              Wrong %
            </th>
            <th>Most missed</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r: TopicRow) => (
            <tr
              key={r.label}
              className={r.thin ? "results-thin" : undefined}
              title={r.thin ? `Fewer than ${minAnswers} answers: shown, not judged.` : undefined}
            >
              <td>{r.label}</td>
              <td className="num">{r.questions}</td>
              <td className="num">{r.answers}</td>
              <td>
                <div
                  className="topic-bar"
                  role="img"
                  aria-label={`${r.wrong} wrong, ${pct(r.shareOfWrong)} of the course's wrong answers`}
                >
                  <span className="topic-fill">
                    <i style={{ width: `${Math.round((r.wrong / most) * 100)}%` }} />
                  </span>
                  <em>
                    {r.wrong} <span className="faint">· {pct(r.shareOfWrong)}</span>
                  </em>
                </div>
              </td>
              <td className="num">{pct(r.wrongRate)}</td>
              <td>
                {r.worstQuestions.map((q) => (
                  <div key={q.id} className="topic-worst">
                    <span className="mono faint">{q.id}</span> {q.wrong}/{q.answers}
                    {q.stem && (
                      <span className="faint">
                        {" "}
                        · <Formatted text={q.stem.length > 70 ? `${q.stem.slice(0, 70)}…` : q.stem} />
                      </span>
                    )}
                  </div>
                ))}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function AdvicePanel({ filters }: { filters: ResultsFilters }) {
  const [advice, setAdvice] = useState<TopicAdvice | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  // A new filter makes the reading about a different report.
  useEffect(() => {
    setAdvice(null);
    setError("");
  }, [filters]);

  async function run() {
    setBusy(true);
    setError("");
    try {
      setAdvice(await api.resultsTopicAdvice(filters));
    } catch (e: unknown) {
      setError(e instanceof ApiError ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="card topic-advice">
      <div className="toolbar">
        <h4 className="grow">AI reading</h4>
        <button className="info" disabled={busy} onClick={run}>
          {busy ? "Analysing…" : advice ? "Analyse again" : "Analyse with AI"}
        </button>
      </div>
      <p className="muted">
        Sends this report&rsquo;s numbers (topic names, counts and the most-missed questions) to
        your AI provider; no candidate data is stored, so none is sent. Check its advice against
        the questions before changing anything.
      </p>
      {error && <div className="banner">{error}</div>}
      {advice && (
        <div role="region" aria-label="AI reading">
          <p>{advice.summary}</p>
          {advice.suggestions.length > 0 && (
            <ul className="topic-suggestions">
              {advice.suggestions.map((s, i) => (
                <li key={i}>
                  <span className={`topic-priority ${s.priority}`}>{s.priority}</span>{" "}
                  <strong>{s.topic}</strong> <span className="faint">({s.course})</span>
                  <div>{s.advice}</div>
                  {s.questionIds.length > 0 && <div className="mono faint">{s.questionIds.join(", ")}</div>}
                </li>
              ))}
            </ul>
          )}
          {advice.dropped > 0 && (
            <p className="faint">
              {advice.dropped} suggestion{advice.dropped === 1 ? "" : "s"} named something not in the
              report and {advice.dropped === 1 ? "was" : "were"} left out.
            </p>
          )}
          {advice.model && (
            <p className="faint">
              Written by {advice.provider} · {advice.model}
            </p>
          )}
        </div>
      )}
    </div>
  );
}
