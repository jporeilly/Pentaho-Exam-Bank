/**
 * Adopt the Content Manager's courses into the bank, and keep them current.
 *
 * Look-then-act, the same shape as publishing: the button fetches a plan and
 * shows it, and nothing is written until the author has seen what would
 * change and pressed the second button. The plan's token goes back with the
 * apply, so a sync cannot run against courses that moved while the summary
 * sat on screen.
 *
 * `changed` is reported but NOT adopted unless the author opts in. These
 * questions were brought into the bank precisely because they had nowhere
 * else to be edited; a refresh that silently reverted that work would make
 * the tool unsafe to use.
 */
import { useState } from "react";

import { api, ApiError, type SyncPlan, type SyncResult } from "./api";

export function SyncPanel({ onSynced }: { onSynced: () => void }) {
  const [plan, setPlan] = useState<SyncPlan | null>(null);
  const [result, setResult] = useState<SyncResult | null>(null);
  const [overwrite, setOverwrite] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const look = async () => {
    setBusy(true);
    setError("");
    setResult(null);
    try {
      setPlan(await api.planCourseSync());
    } catch (e: unknown) {
      setError(e instanceof ApiError ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  const act = async () => {
    if (!plan) return;
    setBusy(true);
    setError("");
    try {
      const r = await api.syncCourses(plan.token, overwrite);
      setResult(r);
      setPlan(null);
      onSynced();
    } catch (e: unknown) {
      // A 409 means the courses moved under the plan. Re-look rather than
      // making the author work out what to do about it.
      const message = e instanceof ApiError ? e.message : String(e);
      setError(message);
      if (e instanceof ApiError && e.status === 409) await look();
    } finally {
      setBusy(false);
    }
  };

  const nothingToDo =
    plan !== null && plan.totalNew === 0 && (!overwrite || plan.totalChanged === 0);

  return (
    <div className="card" style={{ marginBottom: 16 }}>
      <div style={{ display: "flex", alignItems: "center", gap: 12, flexWrap: "wrap" }}>
        <button onClick={look} disabled={busy}>
          {busy && !plan ? "Looking…" : "Check courses for questions"}
        </button>
        {plan && (
          <span className="muted">
            {plan.totalNew} new, {plan.totalChanged} changed, {plan.totalUnchanged} already
            in the bank
            {plan.totalConflicts > 0 && `, ${plan.totalConflicts} refused`}
          </span>
        )}
        {result && (
          <span className="muted">
            Adopted {result.added} question{result.added === 1 ? "" : "s"}
            {result.updated > 0 && `, updated ${result.updated}`}
            {result.skippedChanged > 0 &&
              `, left ${result.skippedChanged} local edit${
                result.skippedChanged === 1 ? "" : "s"
              } alone`}
            .
          </span>
        )}
      </div>

      {error && (
        <div className="banner" style={{ marginTop: 12 }}>
          {error}
        </div>
      )}

      {plan && (
        <>
          <table style={{ marginTop: 12 }}>
            <thead>
              <tr>
                <th>Course</th>
                <th style={{ width: 70, textAlign: "right" }}>New</th>
                <th style={{ width: 90, textAlign: "right" }}>Changed</th>
                <th style={{ width: 90, textAlign: "right" }}>In bank</th>
                <th style={{ width: 90, textAlign: "right" }}>Refused</th>
                <th>Notes</th>
              </tr>
            </thead>
            <tbody>
              {plan.courses.map((c) => {
                const conflicts = c.conflicts ?? [];
                const unusable = c.unusable ?? [];
                return (
                <tr key={c.slug}>
                  <td>
                    {c.title}
                    <div className="muted" style={{ fontSize: "0.85em" }}>
                      {c.slug}
                    </div>
                  </td>
                  <td style={{ textAlign: "right" }}>{c.new || ""}</td>
                  <td style={{ textAlign: "right" }}>{c.changed || ""}</td>
                  <td style={{ textAlign: "right" }}>{c.unchanged || ""}</td>
                  <td style={{ textAlign: "right" }}>
                    {conflicts.length || ""}
                  </td>
                  <td className="muted" style={{ fontSize: "0.85em" }}>
                    {c.error && <span className="warn">{c.error}</span>}
                    {!c.error && conflicts.length > 0 && (
                      <div className="warn">
                        {conflicts.length} id
                        {conflicts.length === 1 ? "" : "s"} {conflicts[0].reason}
                        {" — refused, because the bank keys questions by id and "}
                        adopting both would overwrite one with the other.
                      </div>
                    )}
                    {!c.error && unusable.length > 0 && (
                      <span className="warn">
                        {unusable.length} question
                        {unusable.length === 1 ? "" : "s"} the bank cannot grade —{" "}
                        {unusable[0].reason}
                      </span>
                    )}
                  </td>
                </tr>
                );
              })}
            </tbody>
          </table>

          {plan.totalChanged > 0 && (
            <label
              style={{ display: "flex", alignItems: "center", gap: 8, marginTop: 12 }}
            >
              <input
                type="checkbox"
                checked={overwrite}
                onChange={(e) => setOverwrite(e.target.checked)}
              />
              <span>
                Replace the {plan.totalChanged} question
                {plan.totalChanged === 1 ? "" : "s"} edited here with the course's
                version. Review state is kept; the wording is not.
              </span>
            </label>
          )}

          <div style={{ marginTop: 12 }}>
            <button onClick={act} disabled={busy || nothingToDo}>
              {busy ? "Adopting…" : "Adopt into the bank"}
            </button>
            {nothingToDo && (
              <span className="muted" style={{ marginLeft: 12 }}>
                Nothing to adopt — the bank already has every usable question.
              </span>
            )}
          </div>
        </>
      )}
    </div>
  );
}
