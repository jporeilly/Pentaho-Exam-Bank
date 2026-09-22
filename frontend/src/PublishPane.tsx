/**
 * Publish the bank's questions back into a Content Manager course.
 *
 * This is the only pane that writes outside this app's own database, into a
 * file a second application owns — so it is built as look-then-write rather
 * than as a button. The server will not accept a write without the hash from
 * a plan, which means the diff below is not a courtesy: it is the thing that
 * makes the write possible at all.
 *
 * What the plan shows is deliberately concrete. "12 questions will be
 * published" tells an author nothing they can check. Three added, one
 * reworded, and the pass mark and intake untouched is something they can
 * agree or disagree with before a course changes underneath a learner.
 */
import { useEffect, useMemo, useState } from "react";

import {
  api,
  ApiError,
  type Certification,
  type Course,
  type PublishPlan,
} from "./api";

/** Statuses worth offering. Publishing drafts into a live course is not a
 *  thing to make easy, but it is occasionally what a rehearsal needs. */
const STATUSES = [
  { value: "approved", label: "Approved only" },
  { value: "sme_review", label: "In review" },
  { value: "draft", label: "Drafts" },
  { value: "", label: "Every status" },
];

function Count({ n, one, many }: { n: number; one: string; many: string }) {
  return (
    <span>
      <strong>{n}</strong> {n === 1 ? one : many}
    </span>
  );
}

export function PublishPane({ openCourse = "" }: { openCourse?: string }) {
  const [courses, setCourses] = useState<Course[]>([]);
  const [certifications, setCertifications] = useState<Certification[]>([]);
  const [slug, setSlug] = useState(openCourse);
  const [certId, setCertId] = useState("");
  const [status, setStatus] = useState("approved");

  const [plan, setPlan] = useState<PublishPlan | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [done, setDone] = useState<PublishPlan | null>(null);

  useEffect(() => {
    Promise.all([api.courses(), api.certifications()])
      .then(([c, certs]) => {
        setCourses(c);
        setCertifications(certs);
      })
      .catch((e: unknown) => setError(e instanceof ApiError ? e.message : String(e)));
  }, []);

  // A certification adopted from a course remembers which one, and the server
  // refuses a mismatched pair. Preselecting it saves the author from meeting
  // that refusal for a choice they never meant to make — including when they
  // change the course and the previous certification is left behind pointing
  // at the old one, which is how this was first written and which walked
  // straight into the refusal it exists to avoid.
  useEffect(() => {
    if (!slug || certifications.length === 0) return;
    const linked = certifications.find((c) => c.sourceRef === slug);
    const current = certifications.find((c) => c.id === certId);
    // A certification with no course of its own (sourceRef "") is a
    // deliberate choice to publish it somewhere, so it is left alone.
    const mismatched = Boolean(current?.sourceRef) && current?.sourceRef !== slug;
    if (linked && (!certId || mismatched)) setCertId(linked.id);
    else if (mismatched) setCertId("");
  }, [slug, certId, certifications]);

  // Any change to the selection invalidates the plan: it was computed for a
  // different question set, and its hash would authorise a write of it.
  useEffect(() => {
    setPlan(null);
    setDone(null);
    setError("");
  }, [slug, certId, status]);

  const course = useMemo(() => courses.find((c) => c.slug === slug), [courses, slug]);
  const chosen = Boolean(slug && certId);
  // A course with no exam is chosen but not publishable: the banner above
  // says why, so the button must not also claim something is unchosen.
  const ready = chosen && course?.hasExam !== false;

  async function makePlan() {
    setBusy(true);
    setError("");
    try {
      setPlan(await api.planPublish(slug, certId, status));
    } catch (e) {
      setPlan(null);
      setError(e instanceof ApiError ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  async function publish() {
    if (!plan) return;
    setBusy(true);
    setError("");
    try {
      const result = await api.publish(slug, certId, plan.sourceSha, status);
      setDone(result);
      setPlan(null);
    } catch (e) {
      // Nearly always the hash check: the Content Editor saved the file while
      // the plan was on screen. The plan is dropped rather than left looking
      // current, because it now describes a file that no longer exists.
      setPlan(null);
      setError(e instanceof ApiError ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="card publish">
      <p className="lede">
        Replaces a course's question pool with the bank's. The pass mark, the
        webhook and the intake settings belong to the Content Editor and are
        left exactly as they are.
      </p>

      <div className="field-row">
        <label className="field">
          <span className="field-label">Course</span>
          <select value={slug} onChange={(e) => setSlug(e.target.value)}>
            <option value="">Choose a course…</option>
            {/* A course with no exam.json stays selectable. Greying it out
                would hide the reason behind the very control that refuses,
                and the reason is a deliberate decision about ownership
                rather than a limitation — worth reading once. */}
            {courses.map((c) => (
              <option key={c.slug} value={c.slug}>
                {c.title}
                {c.hasExam ? ` — ${c.questionCount} in pool` : " — no exam.json"}
              </option>
            ))}
          </select>
        </label>

        <label className="field">
          <span className="field-label">Questions from</span>
          <select value={certId} onChange={(e) => setCertId(e.target.value)}>
            <option value="">Choose a certification…</option>
            {certifications.map((c) => (
              <option key={c.id} value={c.id}>
                {c.name} — {c.questionCount}
              </option>
            ))}
          </select>
        </label>

        <label className="field">
          <span className="field-label">Status</span>
          <select value={status} onChange={(e) => setStatus(e.target.value)}>
            {STATUSES.map((s) => (
              <option key={s.value} value={s.value}>
                {s.label}
              </option>
            ))}
          </select>
        </label>
      </div>

      {course && !course.hasExam && (
        <div className="banner warn">
          {course.title} has no exam.json. This publishes into an exam the
          Content Editor already set up — it does not create one, because the
          pass mark, the webhook and the intake behaviour are not the bank's to
          invent.
        </div>
      )}

      {error && <div className="banner">{error}</div>}

      <div className="toolbar">
        <button onClick={makePlan} disabled={!ready || busy}>
          {busy && !plan ? "Checking…" : "Check what would change"}
        </button>
        {!chosen && (
          <span className="faint">Choose a course and a certification.</span>
        )}
      </div>

      {done && <Wrote plan={done} />}
      {plan && <Plan plan={plan} busy={busy} onPublish={publish} />}
    </div>
  );
}

function Plan({
  plan,
  busy,
  onPublish,
}: {
  plan: PublishPlan;
  busy: boolean;
  onPublish: () => void;
}) {
  if (plan.isNoop) {
    return (
      <div className="plan card">
        <p>
          The course already has exactly these {plan.afterCount} questions.
          Nothing to publish.
        </p>
        <p className="faint">
          Publishing anyway would rewrite the file for no change, and the
          Content Editor may be sitting on top of it.
        </p>
      </div>
    );
  }

  return (
    <div className="plan card">
      <h3>
        What would change in <code className="mono">{plan.path}</code>
      </h3>

      <ul className="plan-summary">
        <li>
          Pool goes from <strong>{plan.beforeCount}</strong> to{" "}
          <strong>{plan.afterCount}</strong> questions.
        </li>
        {plan.added.length > 0 && (
          <li className="added">
            <Count n={plan.added.length} one="question added" many="questions added" />
            : <span className="mono">{plan.added.join(", ")}</span>
          </li>
        )}
        {plan.removed.length > 0 && (
          <li className="removed">
            <Count
              n={plan.removed.length}
              one="question removed"
              many="questions removed"
            />
            : <span className="mono">{plan.removed.join(", ")}</span>
            <div className="faint">
              A removed question's id disappears from the pool. Results already
              recorded against it stay in the sheet and will no longer match
              anything here.
            </div>
          </li>
        )}
        {plan.changed.length > 0 && (
          <li className="changed">
            <Count n={plan.changed.length} one="question edited" many="questions edited" />
            <ul>
              {plan.changed.map((c) => (
                <li key={c.id}>
                  <span className="mono">{c.id}</span>{" "}
                  <span className="faint">{c.fields.join(", ")}</span>
                </li>
              ))}
            </ul>
          </li>
        )}
        {plan.reordered && (
          <li className="changed">
            The pool order changes. With <code>shuffle</code> off that is the
            order a learner sees.
          </li>
        )}
        {plan.descriptionAfter && (
          // The one piece of authored prose a publish touches. Shown as the
          // actual sentence, before and after, because "the description will
          // be updated" is not something an author can agree or disagree with.
          <li className="changed">
            The description's pool size is rewritten, because the Content
            Manager's build check fails when the prose misstates it.
            <div className="prose-diff">
              <del>{plan.descriptionBefore}</del>
              <ins>{plan.descriptionAfter}</ins>
            </div>
          </li>
        )}
        {plan.unchanged > 0 && (
          <li className="faint">
            <Count n={plan.unchanged} one="question unchanged" many="questions unchanged" />
          </li>
        )}
      </ul>

      {plan.preservedKeys.length > 0 && (
        <p className="preserved faint">
          Left untouched: {plan.preservedKeys.map((k) => (
            <code className="mono" key={k}>
              {k}
            </code>
          ))}
        </p>
      )}

      <div className="toolbar">
        <button onClick={onPublish} disabled={busy}>
          {busy ? "Publishing…" : "Publish to the course"}
        </button>
        <span className="faint">
          Writes {plan.path}. The course still has to be published to the
          courses repo before an installed app sees it.
        </span>
      </div>
    </div>
  );
}

function Wrote({ plan }: { plan: PublishPlan }) {
  return (
    <div className="plan card">
      <h3>Published</h3>
      <p>
        <code className="mono">{plan.path}</code> now holds{" "}
        <strong>{plan.afterCount}</strong> questions.
      </p>
      <p className="faint">
        This wrote the authoring copy. An installed Content Manager syncs from
        the published courses repo, so nothing a learner runs has changed yet.
      </p>
    </div>
  );
}
