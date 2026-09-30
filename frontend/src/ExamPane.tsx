/**
 * Build a printable exam paper, weighted across topics.
 *
 * The weighting is the whole point and also the whole difficulty. An author
 * sets a shape — forty questions, half Networking — and the bank may simply
 * not have the questions to fill it. When that happens the selection does not
 * fail: it takes the shortfall from whichever topics have spare questions, so
 * the paper comes back the right LENGTH and the wrong MIX.
 *
 * The printed cover does list the per-topic counts, so the mix is not hidden
 * — but it lists what the paper IS, never what was asked for, and only once
 * the paper exists. Telling the two apart means remembering the weights you
 * typed. So this is look-then-build, like publishing and importing: the plan
 * states the discrepancy outright, before anything is printed.
 */
import { useCallback, useEffect, useMemo, useState } from "react";

import {
  api,
  ApiError,
  type Certification,
  type ExamPlan,
  type ExamRequest,
  type ExamTopic,
} from "./api";
import { useVocabulary } from "./vocabulary";

// A deliberate subset, with the names an exam paper's author uses: which
// review states may go on a paper. Not the vocabulary.
const STATUSES = [
  { value: "approved", label: "Approved" },
  { value: "sme_review", label: "In review" },
  { value: "draft", label: "Drafts" },
];

/** Percentages that sum to 100, distributed as evenly as they divide.
 *
 * The remainder goes to the first topics one point at a time rather than all
 * to one: three topics become 34/33/33, not 34/33/33 with a 2-point outlier.
 */
function evenWeights(topics: string[]): Record<string, number> {
  const out: Record<string, number> = {};
  if (topics.length === 0) return out;
  const base = Math.floor(100 / topics.length);
  let remainder = 100 - base * topics.length;
  for (const topic of topics) {
    out[topic] = base + (remainder > 0 ? 1 : 0);
    if (remainder > 0) remainder -= 1;
  }
  return out;
}

export function ExamPane() {
  const [certifications, setCertifications] = useState<Certification[]>([]);
  const [certIds, setCertIds] = useState<string[]>([]);
  const [topics, setTopics] = useState<ExamTopic[]>([]);
  const [weights, setWeights] = useState<Record<string, number>>({});

  const [total, setTotal] = useState(20);
  const vocabulary = useVocabulary();
  const [difficulties, setDifficulties] = useState<string[]>(vocabulary.difficulties);
  const [statuses, setStatuses] = useState<string[]>(["approved"]);
  const [seed, setSeed] = useState("");
  const [title, setTitle] = useState("Practice Exam");
  const [institution, setInstitution] = useState("");
  const [answerKey, setAnswerKey] = useState(true);

  const [plan, setPlan] = useState<ExamPlan | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [built, setBuilt] = useState("");

  useEffect(() => {
    api
      .certifications()
      .then(setCertifications)
      .catch((e: unknown) => setError(e instanceof ApiError ? e.message : String(e)));
  }, []);

  const statusKey = statuses.join(",");

  // Topics depend on which certifications and statuses are in play, so the
  // weighting is always built against what the bank can actually supply.
  useEffect(() => {
    if (certIds.length === 0) {
      setTopics([]);
      setWeights({});
      return;
    }
    let live = true;
    api
      .examTopics(certIds, statusKey)
      .then((found) => {
        if (!live) return;
        setTopics(found);
        // Re-even the split whenever the available topics change: keeping old
        // weights would leave a total that no longer adds to 100, and the
        // server would refuse a request the author never knowingly made.
        setWeights(evenWeights(found.map((t) => t.topic)));
      })
      .catch((e: unknown) => setError(e instanceof ApiError ? e.message : String(e)));
    return () => {
      live = false;
    };
  }, [certIds, statusKey]);

  // The plan describes one specific request. Any change to that request makes
  // it a description of something else.
  useEffect(() => {
    setPlan(null);
    setBuilt("");
  }, [certIds, statusKey, weights, total, difficulties, seed]);

  const weightTotal = useMemo(
    () => Object.values(weights).reduce((a, b) => a + b, 0),
    [weights],
  );
  const balanced = Math.abs(weightTotal - 100) <= 1;

  const request = useCallback(
    (): ExamRequest => ({
      certification_ids: certIds,
      total_questions: total,
      topic_weights: weights,
      difficulties,
      statuses,
      seed: seed.trim() === "" ? null : Number(seed),
    }),
    [certIds, total, weights, difficulties, statuses, seed],
  );

  function toggle(list: string[], value: string, set: (v: string[]) => void) {
    set(list.includes(value) ? list.filter((v) => v !== value) : [...list, value]);
  }

  async function check() {
    setBusy(true);
    setError("");
    try {
      setPlan(await api.planExam(request()));
    } catch (e) {
      setPlan(null);
      setError(e instanceof ApiError ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  async function build() {
    setBusy(true);
    setError("");
    try {
      const blob = await api.examPdf({
        ...request(),
        title,
        institution,
        include_answer_key: answerKey,
        filename: `${title.trim().toLowerCase().replace(/[^a-z0-9]+/g, "-") || "exam"}.pdf`,
      });
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = `${title.trim() || "exam"}.pdf`;
      link.click();
      URL.revokeObjectURL(url);
      setBuilt(`${title.trim() || "exam"}.pdf`);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  const ready = certIds.length > 0 && topics.length > 0 && balanced;

  return (
    <div className="card exam">
      <p className="lede">
        Draws a paper from the bank in the proportions you set. Checking first
        is worth it: where a topic has too few questions the rest are taken
        from elsewhere, so the paper comes out the right length and the wrong
        mix.
      </p>

      {error && <div className="banner">{error}</div>}

      <div className="field-row">
        <label className="field">
          <span className="field-label">Draw from</span>
          <select
            multiple
            size={Math.min(4, Math.max(2, certifications.length))}
            value={certIds}
            onChange={(e) =>
              setCertIds([...e.target.selectedOptions].map((o) => o.value))
            }
          >
            {certifications.map((c) => (
              <option key={c.id} value={c.id}>
                {c.name} — {c.questionCount}
              </option>
            ))}
          </select>
          <span className="faint field-hint">Ctrl-click for more than one.</span>
        </label>

        <label className="field">
          <span className="field-label">Questions</span>
          <input
            type="number"
            min={1}
            max={500}
            value={total}
            onChange={(e) => setTotal(Math.max(1, Number(e.target.value) || 1))}
          />
        </label>

        <label className="field">
          <span className="field-label">Seed</span>
          <input
            value={seed}
            placeholder="Blank for a new paper each time"
            onChange={(e) => setSeed(e.target.value)}
          />
          <span className="faint field-hint">
            The same seed reprints the same paper.
          </span>
        </label>
      </div>

      <div className="field-row">
        <fieldset className="field checks">
          <legend className="field-label">Difficulty</legend>
          {vocabulary.difficulties.map((d) => (
            <label key={d} className="check">
              <input
                type="checkbox"
                checked={difficulties.includes(d)}
                onChange={() => toggle(difficulties, d, setDifficulties)}
              />
              {d}
            </label>
          ))}
        </fieldset>

        <fieldset className="field checks">
          <legend className="field-label">Draw questions that are</legend>
          {STATUSES.map((s) => (
            <label key={s.value} className="check">
              <input
                type="checkbox"
                checked={statuses.includes(s.value)}
                onChange={() => toggle(statuses, s.value, setStatuses)}
              />
              {s.label}
            </label>
          ))}
        </fieldset>
      </div>

      {certIds.length === 0 ? (
        <div className="empty">Choose a certification to draw from.</div>
      ) : topics.length === 0 ? (
        <div className="banner warn">
          Nothing in those certifications has a topic at the statuses chosen, so
          there is nothing to weight. Questions adopted from a course are drafts
          until they are reviewed.
        </div>
      ) : (
        <Weights
          topics={topics}
          weights={weights}
          total={total}
          weightTotal={weightTotal}
          balanced={balanced}
          onChange={setWeights}
        />
      )}

      <div className="field-row">
        <label className="field">
          <span className="field-label">Exam title</span>
          <input value={title} onChange={(e) => setTitle(e.target.value)} />
        </label>
        <label className="field">
          <span className="field-label">Institution</span>
          <input
            value={institution}
            placeholder="Optional, printed on the cover"
            onChange={(e) => setInstitution(e.target.value)}
          />
        </label>
        <label className="field">
          <span className="field-label">Answer key</span>
          <label className="check">
            <input
              type="checkbox"
              checked={answerKey}
              onChange={(e) => setAnswerKey(e.target.checked)}
            />
            Include at the end
          </label>
        </label>
      </div>

      <div className="toolbar">
        <button onClick={check} disabled={!ready || busy}>
          {busy && !plan ? "Checking…" : "Check the mix"}
        </button>
        <button className="secondary" onClick={build} disabled={!ready || busy}>
          {busy ? "Building…" : "Build the paper"}
        </button>
        {!balanced && topics.length > 0 && (
          <span className="faint">Weights must total 100%.</span>
        )}
      </div>

      {built && (
        <div className="plan card">
          <h3>Built</h3>
          <p>
            <code className="mono">{built}</code> has been downloaded.
          </p>
        </div>
      )}

      {plan && <Plan plan={plan} />}
    </div>
  );
}

function Weights({
  topics,
  weights,
  total,
  weightTotal,
  balanced,
  onChange,
}: {
  topics: ExamTopic[];
  weights: Record<string, number>;
  total: number;
  weightTotal: number;
  balanced: boolean;
  onChange: (w: Record<string, number>) => void;
}) {
  return (
    <div className="weights">
      <div className="toolbar">
        <strong>Topic mix</strong>
        <span className={`faint ${balanced ? "" : "unbalanced"}`}>
          {weightTotal}% of 100%
        </span>
        <span className="spacer" />
        <button
          className="secondary"
          onClick={() => onChange(evenWeights(topics.map((t) => t.topic)))}
        >
          Split evenly
        </button>
      </div>

      <table>
        <thead>
          <tr>
            <th>Topic</th>
            <th style={{ width: 110 }}>Share</th>
            <th style={{ width: 130, textAlign: "right" }}>That's about</th>
            <th style={{ width: 110, textAlign: "right" }}>In the bank</th>
          </tr>
        </thead>
        <tbody>
          {topics.map((t) => {
            const weight = weights[t.topic] ?? 0;
            // Said here as well as in the plan, because it is the number that
            // makes a weight mean something while it is being typed.
            const wanted = Math.round((total * weight) / 100);
            const thin = wanted > t.questionCount;
            return (
              <tr key={t.topic} className="q-row">
                <td>{t.topic}</td>
                <td>
                  <input
                    type="number"
                    min={0}
                    max={100}
                    value={weight}
                    aria-label={`${t.topic} share`}
                    onChange={(e) =>
                      onChange({
                        ...weights,
                        [t.topic]: Math.max(0, Math.min(100, Number(e.target.value) || 0)),
                      })
                    }
                  />
                </td>
                <td style={{ textAlign: "right" }}>
                  {wanted} {wanted === 1 ? "question" : "questions"}
                </td>
                <td style={{ textAlign: "right" }} className={thin ? "thin" : "faint"}>
                  {t.questionCount}
                  {thin && <div className="faint">not enough</div>}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function Plan({ plan }: { plan: ExamPlan }) {
  if (plan.honoured) {
    return (
      <div className="plan card">
        <h3>The mix works</h3>
        <p>
          All <strong>{plan.selected}</strong> questions come from the topics you
          weighted, in the proportions you set.
        </p>
      </div>
    );
  }

  return (
    <div className="plan card">
      <h3>The paper would not match the mix you set</h3>

      <ul className="plan-summary">
        {plan.shortfall > 0 && (
          <li className="removed">
            The bank has <strong>{plan.selected}</strong> of the{" "}
            <strong>{plan.requested}</strong> questions asked for, so the paper
            would be {plan.shortfall} short.
          </li>
        )}
        {plan.redistributed > 0 && (
          <li className="changed">
            <strong>{plan.redistributed}</strong>{" "}
            {plan.redistributed === 1 ? "question comes" : "questions come"} from a
            topic other than the one entitled to{" "}
            {plan.redistributed === 1 ? "it" : "them"}.
          </li>
        )}
      </ul>

      <table>
        <thead>
          <tr>
            <th>Topic</th>
            <th style={{ width: 90, textAlign: "right" }}>Wanted</th>
            <th style={{ width: 90, textAlign: "right" }}>Available</th>
            <th style={{ width: 90, textAlign: "right" }}>On the paper</th>
          </tr>
        </thead>
        <tbody>
          {plan.topics.map((t) => (
            <tr key={t.topic} className={`q-row ${t.short ? "broken" : ""}`}>
              <td>
                {t.topic}
                {t.short > 0 && (
                  <div className="problem">
                    {t.short} short — the rest of its share comes from elsewhere
                  </div>
                )}
                {t.lent > 0 && (
                  <div className="duplicate">
                    contributing {t.lent} beyond its share
                  </div>
                )}
              </td>
              <td style={{ textAlign: "right" }}>{t.wanted}</td>
              <td style={{ textAlign: "right" }} className="faint">
                {t.available}
              </td>
              <td style={{ textAlign: "right" }}>
                <strong>{t.selected}</strong>
              </td>
            </tr>
          ))}
        </tbody>
      </table>

      <p className="faint">
        Build it anyway if that is acceptable — or add questions to the thin
        topics, lower their share, or ask for a shorter paper.
      </p>
    </div>
  );
}
