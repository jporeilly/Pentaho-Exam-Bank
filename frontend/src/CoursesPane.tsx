import { useEffect, useState } from "react";

import { api, ApiError, type Course, type CourseSections, type Lab } from "./api";
import { SyncPanel } from "./SyncPanel";

/**
 * The courses the Content Manager has, and what is inside one.
 *
 * `questionCount` is the size of the pool already in the course's exam.json —
 * the questions that, until this app adopted them, had no editing tool at all.
 */
export function CoursesPane() {
  const [courses, setCourses] = useState<Course[] | null>(null);
  const [error, setError] = useState("");
  const [open, setOpen] = useState<string>("");

  const load = () => {
    api
      .courses()
      .then((c) => {
        setCourses(c);
        setError("");
      })
      .catch((e: unknown) => setError(e instanceof ApiError ? e.message : String(e)));
  };

  useEffect(load, []);

  if (error) return <div className="banner">{error}</div>;
  if (!courses) return <div className="empty">Loading courses…</div>;
  if (courses.length === 0)
    return <div className="empty">No courses found in the Content Manager.</div>;

  return (
    <>
    <SyncPanel onSynced={load} />
    <div className="card">
      <table>
        <thead>
          <tr>
            <th>Course</th>
            <th>Slug</th>
            <th style={{ width: 90, textAlign: "right" }}>Pool</th>
            <th style={{ width: 110 }} />
          </tr>
        </thead>
        <tbody>
          {courses.map((course) => (
            <CourseRow
              key={course.slug}
              course={course}
              expanded={open === course.slug}
              onToggle={() => setOpen(open === course.slug ? "" : course.slug)}
            />
          ))}
        </tbody>
      </table>
    </div>
    </>
  );
}

function CourseRow({
  course,
  expanded,
  onToggle,
}: {
  course: Course;
  expanded: boolean;
  onToggle: () => void;
}) {
  return (
    <>
      <tr>
        <td>{course.title}</td>
        <td className="mono muted">{course.slug}</td>
        <td className="num">
          {course.hasExam ? course.questionCount : <span className="faint">none</span>}
        </td>
        <td>
          <button className="secondary" onClick={onToggle}>
            {expanded ? "Hide" : "Contents"}
          </button>
        </td>
      </tr>
      {expanded && (
        <tr>
          <td colSpan={4} style={{ background: "var(--bg)" }}>
            <CourseContents slug={course.slug} />
          </td>
        </tr>
      )}
    </>
  );
}

/** A course's labs, and the sections a question could be generated from. */
function CourseContents({ slug }: { slug: string }) {
  const [labs, setLabs] = useState<Lab[] | null>(null);
  const [contents, setContents] = useState<CourseSections | null>(null);
  const [lab, setLab] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    let live = true;
    setError("");
    Promise.all([api.labs(slug), api.sections(slug, lab)])
      .then(([l, s]) => {
        if (!live) return;
        setLabs(l);
        setContents(s);
      })
      .catch((e: unknown) => {
        if (live) setError(e instanceof ApiError ? e.message : String(e));
      });
    // Ignore a response that arrives after the selection moved on.
    return () => {
      live = false;
    };
  }, [slug, lab]);

  if (error) return <div className="banner">{error}</div>;
  if (!labs || !contents) return <div className="muted">Reading the course…</div>;

  const { sections, budget } = contents;
  const oversized = sections.filter((s) => s.exceedsContext);

  return (
    <div>
      <div className="toolbar">
        <label className="muted" htmlFor={`lab-${slug}`}>
          Lab
        </label>
        <select id={`lab-${slug}`} value={lab} onChange={(e) => setLab(e.target.value)}>
          <option value="">All labs ({labs.length})</option>
          {labs.map((l) => (
            <option key={l.slug} value={l.slug}>
              {l.frontMatter ? `${l.title} (not examined)` : l.title}
            </option>
          ))}
        </select>
        <span className="muted">
          {sections.length} section{sections.length === 1 ? "" : "s"} with enough prose
          to write from
        </span>
      </div>

      {oversized.length > 0 && (
        // Ollama truncates an over-long section without saying so: the
        // questions come back thinner than the material deserved and nothing
        // explains why. Naming the model and the window makes the fix
        // obvious — a larger window, a smaller model, or split the section.
        <div className="banner warn">
          <strong>
            {oversized.length} section{oversized.length === 1 ? " is" : "s are"} longer
            than {budget.model || "the model"} can read in one go
          </strong>{" "}
          — the context is {budget.numCtx.toLocaleString()} tokens, which leaves about{" "}
          {budget.chars.toLocaleString()} characters for the source after the prompt.
          Anything past that is dropped silently, so questions from{" "}
          {oversized.length === 1 ? "it" : "them"} will only cover the beginning.
        </div>
      )}

      {sections.length === 0 ? (
        <div className="empty">
          Nothing here has enough prose to ground a question in.
        </div>
      ) : (
        <table>
          <thead>
            <tr>
              <th>Section</th>
              <th style={{ width: 120, textAlign: "right" }}>Chars</th>
            </tr>
          </thead>
          <tbody>
            {sections.map((section) => (
              <tr key={section.index}>
                <td>
                  {section.title ?? <span className="faint">untitled</span>}
                  {section.exceedsContext && (
                    <span
                      className="pill"
                      style={{
                        marginLeft: 8,
                        background: "var(--bg-input)",
                        color: "var(--warn)",
                      }}
                      title={`Longer than the ${budget.chars.toLocaleString()} characters that fit ${budget.model}'s context — the rest is dropped`}
                    >
                      truncated
                    </span>
                  )}
                  <div className="faint" style={{ fontSize: 12 }}>
                    {section.preview.slice(0, 140)}…
                  </div>
                </td>
                <td
                  className="num"
                  style={section.exceedsContext ? { color: "var(--warn)", fontWeight: 600 } : undefined}
                >
                  {section.characters.toLocaleString()}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
