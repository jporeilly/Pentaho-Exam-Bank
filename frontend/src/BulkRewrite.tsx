/**
 * The AI rewrite over every question the Bank is showing (1.14.0).
 *
 * The single rewrite's rule holds here too: the model proposes and the author
 * accepts. The rewrite runs as a job, one model call per question, and the
 * review list grows as each one finishes; nothing reaches the bank until a
 * question is accepted, one at a time or all the ready ones at once. Accepting
 * is the editor's own save on the server, recorded in each question's history
 * as the bulk rewrite's.
 *
 * "Accept all" takes only the clean ones - a proposal with notes (an
 * explanation that still judges every option, say) waits for a look.
 */
import { useCallback, useEffect, useMemo, useState } from "react";

import { api, ApiError, type RewriteEntry, type RewriteJob, type RewriteScope } from "./api";
import { HouseStyle } from "./HouseStyle";
import { ProposedQuestion } from "./ProposalView";

type Props = {
  scope: RewriteScope;
  /** How many questions the scope matches, for the confirmation. */
  total: number;
  onClose: () => void;
  /** Called after any question was saved, so the Bank can reload. */
  onSaved: () => void;
  /** How often to ask the job how it is doing. */
  pollMs?: number;
};

/**
 * Which parts the rewrite touched, in the author's words. A polish should
 * mostly read "Explanation"; a scenario or question in the list is where to
 * look first, because a rewrite there can change what is being asked.
 */
export function changedParts(e: RewriteEntry): string[] {
  const p = e.proposed;
  if (!p) return [];
  const o = e.original;
  const same = (a: unknown, b: unknown) => JSON.stringify(a) === JSON.stringify(b);
  const parts: string[] = [];
  if (o.scenario !== p.scenario) parts.push("Scenario");
  if (o.stem !== p.stem) parts.push("Question");
  if (o.key !== p.key || !same(o.keys, p.keys) || !same(o.distractors, p.distractors)) parts.push("Answers");
  if (o.explanation !== p.explanation) parts.push("Explanation");
  return parts;
}

/** Why an entry cannot be accepted, or "" when it can. An unchanged one can:
 *  accepting it saves nothing but still passes it through the gate (1.18.0). */
function blocked(e: RewriteEntry): string {
  if (e.accepted) return "Accepted";
  if (e.error || !e.proposed) return "Failed";
  if (e.problems.length) return "Cannot be graded";
  return "";
}

/** What the gate did with an accepted question. */
type Outcome = { approved: boolean; reasons: string[] };

export function BulkRewrite({ scope, total, onClose, onSaved, pollMs = 1500 }: Props) {
  const [jobId, setJobId] = useState("");
  const [job, setJob] = useState<RewriteJob | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  /** Questions the author passed over, and server refusals, by id. */
  const [skipped, setSkipped] = useState<Record<string, string>>({});
  const [outcomes, setOutcomes] = useState<Record<string, Outcome>>({});
  const [showOriginal, setShowOriginal] = useState<Record<string, boolean>>({});

  const refresh = useCallback(async (id: string) => {
    const latest = await api.rewriteJob(id);
    setJob(latest);
    return latest;
  }, []);

  // Ask how the job is doing until it stops running.
  useEffect(() => {
    if (!jobId) return;
    let live = true;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const tick = async () => {
      try {
        const latest = await refresh(jobId);
        if (live && latest.status === "running") timer = setTimeout(tick, pollMs);
      } catch (e) {
        if (live) setError(e instanceof ApiError ? e.message : String(e));
      }
    };
    void tick();
    return () => {
      live = false;
      if (timer) clearTimeout(timer);
    };
  }, [jobId, pollMs, refresh]);

  async function start() {
    setBusy(true);
    setError("");
    try {
      const started = await api.aiRewriteAll(scope);
      setJobId(started.jobId);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  async function stop() {
    try {
      await api.cancelJob(jobId);
      await refresh(jobId);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : String(e));
    }
  }

  async function accept(ids: string[]) {
    if (!ids.length) return;
    setBusy(true);
    setError("");
    try {
      const result = await api.acceptRewrites(jobId, ids);
      if (result.skipped.length) {
        setSkipped((s) => ({
          ...s,
          ...Object.fromEntries(result.skipped.map((x) => [x.id, x.reason])),
        }));
      }
      setOutcomes((o) => ({
        ...o,
        ...Object.fromEntries((result.approved ?? []).map((id) => [id, { approved: true, reasons: [] }])),
        ...Object.fromEntries((result.review ?? []).map((r) => [r.id, { approved: false, reasons: r.reasons }])),
      }));
      await refresh(jobId);
      if (result.saved.length || (result.approved ?? []).length || (result.review ?? []).length) onSaved();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  const entries = useMemo(() => job?.result ?? [], [job]);
  const open = entries.filter((e) => !blocked(e) && !(e.id in skipped));
  const ready = open.filter((e) => e.notes.length === 0);
  const accepted = entries.filter((e) => e.accepted).length;
  const approvedCount = Object.values(outcomes).filter((o) => o.approved).length;
  const heldCount = Object.values(outcomes).filter((o) => !o.approved).length;
  const running = job?.status === "running";

  if (!jobId) {
    return (
      <div className="card bulk-rewrite">
        <strong>AI rewrite {total === 1 ? "the 1 question" : `all ${total} questions`} shown?</strong>
        <p className="muted">
          Each question is proofread for spelling, grammar and flow, and its explanation
          rewritten to say why the correct answer is right, in paragraphs with the key terms
          in bold. It takes one model call per question, so this runs for a while; you can
          review and accept them as they arrive. <strong>Nothing is saved until you accept.</strong>
        </p>
        <p className="muted">
          Every question you accept then goes through every check. One that passes them all
          is approved; one with any finding is held for review, with the reasons on it.
        </p>
        <HouseStyle intro="What the rewrite brings each question to. New questions are generated to the same rules." />
        {error && <div className="banner">{error}</div>}
        <div className="toolbar bulk-rewrite__actions">
          <button className="ai" onClick={start} disabled={busy || total === 0}>
            {busy ? "Starting…" : `Rewrite ${total} ${total === 1 ? "question" : "questions"}`}
          </button>
          <button className="secondary" onClick={onClose} disabled={busy}>
            Cancel
          </button>
        </div>
      </div>
    );
  }

  const done = job?.progress.current ?? 0;
  const of = job?.progress.total || job?.requested || total;
  return (
    <div className="card bulk-rewrite">
      <div className="toolbar bulk-rewrite__head">
        <strong>AI rewrite</strong>
        <span className="muted" aria-live="polite">
          {running
            ? `Rewriting ${done + 1 > of ? of : done + 1} of ${of}…`
            : job?.status === "cancelled"
              ? `Stopped after ${entries.length} of ${of}.`
              : job?.status === "error"
                ? `Stopped: ${job.error}`
                : `Rewrote ${entries.length} of ${of}.`}
          {accepted > 0 && ` ${accepted} accepted.`}
          {approvedCount + heldCount > 0 &&
            ` ${approvedCount} approved, ${heldCount} held for review.`}
        </span>
        <span className="spacer" />
        <button
          className="add"
          onClick={() => accept(ready.map((e) => e.id))}
          disabled={busy || ready.length === 0}
          title="Accepts every rewrite with no notes and no problems; each is then approved if it passes every check. Look at the ones with notes first."
        >
          Accept all ready ({ready.length})
        </button>
        {running ? (
          <button className="secondary danger" onClick={stop}>
            Stop
          </button>
        ) : (
          <button className="secondary" onClick={onClose}>
            Close
          </button>
        )}
      </div>
      <progress
        className="bulk-rewrite__progress"
        max={of || 1}
        value={running ? done : of}
        aria-label="Rewrite progress"
      />
      {error && <div className="banner">{error}</div>}
      {open.length > ready.length && (
        <p className="muted">
          {open.length - ready.length} with notes {open.length - ready.length === 1 ? "is" : "are"}{" "}
          left for you to look at before accepting.
        </p>
      )}

      <ol className="rewrite-list">
        {entries.map((e) => {
          const outcome = outcomes[e.id];
          const state = outcome
            ? outcome.approved ? "Approved" : "Held for review"
            : blocked(e) || (e.id in skipped ? "Skipped" : "");
          const reason = skipped[e.id] || (outcome && !outcome.approved ? outcome.reasons.join(" ") : "");
          return (
            <li key={e.id} className={`rewrite-entry${state ? " is-settled" : ""}`}>
              <div className="rewrite-entry__head">
                <code className="mono">{e.id}</code>
                {state && <span className={`rewrite-chip rewrite-chip-${state.split(" ")[0].toLowerCase()}`}>{state}</span>}
                {!state && e.notes.length > 0 && <span className="rewrite-chip rewrite-chip-notes">Has notes</span>}
                {e.proposed && e.unchanged && <span className="muted rewrite-entry__changed">Unchanged</span>}
                {e.proposed && !e.unchanged && (
                  <span className="muted rewrite-entry__changed">
                    Changed: {changedParts(e).join(" · ")}
                  </span>
                )}
                <span className="spacer" />
                {e.proposed && (
                  <button
                    className="secondary"
                    onClick={() => setShowOriginal((s) => ({ ...s, [e.id]: !s[e.id] }))}
                  >
                    {showOriginal[e.id] ? "Hide original" : "Show original"}
                  </button>
                )}
                {!state && (
                  <>
                    <button className="add" onClick={() => accept([e.id])} disabled={busy}>
                      Accept
                    </button>
                    <button
                      className="secondary"
                      onClick={() => setSkipped((s) => ({ ...s, [e.id]: "" }))}
                      disabled={busy}
                    >
                      Skip
                    </button>
                  </>
                )}
              </div>
              {reason && <div className="advice">{reason}</div>}
              {e.proposed ? (
                <ProposedQuestion proposed={e.proposed} notes={e.notes} problems={e.problems} />
              ) : (
                <p className="problem">{e.error || "There is no proposal for this question."}</p>
              )}
              {showOriginal[e.id] && (
                <div className="rewrite-entry__original">
                  <div className="explanation-card__label">Original</div>
                  <ProposedQuestion proposed={e.original} />
                </div>
              )}
            </li>
          );
        })}
      </ol>
    </div>
  );
}
