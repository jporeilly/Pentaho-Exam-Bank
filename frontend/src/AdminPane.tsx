/**
 * Backups, and bulk deletion.
 *
 * The two are in one pane on purpose: this is the only part of the app with
 * no undo short of a backup, and somebody about to delete four hundred
 * questions should be able to see the backup list while they decide.
 *
 * Deleting is count-first. The filters are the same ones the bank list uses,
 * so it is genuinely easy to press delete against a view believed to show
 * four questions and have it match four hundred — the count, the breakdown
 * and a few of the actual stems all come back before anything goes, and the
 * count is carried on the button rather than hidden behind "Are you sure?".
 */
import { useCallback, useEffect, useMemo, useState } from "react";

import {
  api,
  ApiError,
  type BackupFile,
  type Certification,
  type DatabaseStatus,
  type DeletionFilters,
  type DeletionPlan,
} from "./api";

// Until the server's own list arrives. This was the whole list, and it had
// drifted: it lacked `revised` and `retired`, so the bulk delete could not be
// narrowed to either.
const FALLBACK_STATUSES = ["draft", "sme_review", "revised", "approved", "rejected", "retired"];
const DIFFICULTIES = ["Easy", "Medium", "Hard"];

export function AdminPane({ onChanged }: { onChanged?: () => void } = {}) {
  const [status, setStatus] = useState<DatabaseStatus | null>(null);
  const [certifications, setCertifications] = useState<Certification[]>([]);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState("");

  const [statuses, setStatuses] = useState<string[]>(FALLBACK_STATUSES);
  const [filters, setFilters] = useState<DeletionFilters>({});
  const [plan, setPlan] = useState<DeletionPlan | null>(null);
  const [confirmedAll, setConfirmedAll] = useState(false);

  const reload = useCallback(async () => {
    const [db, certs] = await Promise.all([api.databaseStatus(), api.certifications()]);
    setStatus(db);
    setCertifications(certs);
  }, []);

  useEffect(() => {
    reload().catch((e: unknown) =>
      setError(e instanceof ApiError ? e.message : String(e)),
    );
  }, [reload]);

  // The statuses come from the bank's lifecycle, the one list the server
  // validates against. A failure keeps the fallback: the filter still works.
  useEffect(() => {
    api
      .lifecycle()
      .then((l) => {
        if (Array.isArray(l?.statuses) && l.statuses.length) setStatuses(l.statuses);
      })
      .catch(() => {});
  }, []);

  // A plan describes one specific selection. Changing the filters makes it a
  // description of something else, and its count would authorise that.
  useEffect(() => {
    setPlan(null);
    setConfirmedAll(false);
  }, [filters]);

  async function run<T>(work: () => Promise<T>, after?: (result: T) => void) {
    setBusy(true);
    setError("");
    try {
      const result = await work();
      await reload();
      after?.(result);
      onChanged?.();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  function set(field: keyof DeletionFilters, value: string) {
    setFilters((f) => {
      const next = { ...f };
      if (value) next[field] = value;
      else delete next[field];
      return next;
    });
    setNote("");
  }

  async function preview() {
    setBusy(true);
    setError("");
    setNote("");
    try {
      setPlan(await api.previewDeletion(filters));
    } catch (e) {
      setPlan(null);
      setError(e instanceof ApiError ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  async function doDelete() {
    if (!plan) return;
    await run(
      () => api.deleteQuestions(filters, plan.total, plan.everything),
      (result) => {
        setNote(
          `${result.deleted} ${result.deleted === 1 ? "question" : "questions"} deleted.`,
        );
        setPlan(null);
        setConfirmedAll(false);
      },
    );
  }

  const narrowed = useMemo(() => Object.keys(filters).length > 0, [filters]);
  // Deleting the whole bank needs a second, deliberate action. The server
  // refuses it outright without one; this is so the author is not surprised
  // by that refusal after pressing a button.
  const blockedByAll = Boolean(plan?.everything) && !confirmedAll;

  if (error && !status) return <div className="banner">{error}</div>;
  if (!status) return <div className="empty">Loading…</div>;

  return (
    <div className="card admin">
      <p className="lede">
        The only part of the app with no undo. Take a backup before deleting
        anything you would miss — restoring one is a single click, and the bank
        it replaces is backed up first.
      </p>

      {error && <div className="banner">{error}</div>}
      {note && <div className="banner ok-note">{note}</div>}

      <section className="settings-section">
        <h3>The database</h3>
        <dl className="paths">
          <dt>Path</dt>
          <dd className="mono faint">{status.database.path}</dd>
          <dt>Holds</dt>
          <dd>
            {status.database.questions ?? 0} questions,{" "}
            {status.database.certifications ?? 0} certifications
            {status.database.size_kb ? ` — ${status.database.size_kb} KB` : ""}
          </dd>
        </dl>
      </section>

      <Backups
        backups={status.backups}
        busy={busy}
        onCreate={(label) => run(() => api.createBackup(label), (r) => setNote(`Backed up as ${r.name}.`))}
        onRestore={(name) =>
          run(
            () => api.restoreBackup(name),
            (r) =>
              setNote(
                `Restored ${r.restored}. The bank it replaced was saved as ${r.safetyBackup}, ` +
                  "so this can be undone.",
              ),
          )
        }
        onDelete={(name) => run(() => api.deleteBackup(name), () => setNote(`Deleted ${name}.`))}
      />

      <section className="settings-section">
        <h3>Delete questions in bulk</h3>
        <p className="faint section-hint">
          The same filters as the bank list. Nothing is deleted until you have
          seen the count.
        </p>

        <div className="field-row">
          <label className="field">
            <span className="field-label">Status</span>
            <select value={filters.status ?? ""} onChange={(e) => set("status", e.target.value)}>
              <option value="">Any</option>
              {statuses.map((s) => (
                <option key={s} value={s}>
                  {s.replace("_", " ")}
                </option>
              ))}
            </select>
          </label>
          <label className="field">
            <span className="field-label">Certification</span>
            <select
              value={filters.certification_id ?? ""}
              onChange={(e) => set("certification_id", e.target.value)}
            >
              <option value="">Any</option>
              {certifications.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.name}
                </option>
              ))}
            </select>
          </label>
          <label className="field">
            <span className="field-label">Topic</span>
            <input
              value={filters.topic ?? ""}
              placeholder="Any"
              onChange={(e) => set("topic", e.target.value)}
            />
          </label>
          <label className="field">
            <span className="field-label">Difficulty</span>
            <select
              value={filters.difficulty ?? ""}
              onChange={(e) => set("difficulty", e.target.value)}
            >
              <option value="">Any</option>
              {DIFFICULTIES.map((d) => (
                <option key={d} value={d}>
                  {d}
                </option>
              ))}
            </select>
          </label>
        </div>

        <div className="toolbar">
          <button className="secondary" onClick={preview} disabled={busy}>
            {busy && !plan ? "Counting…" : "Count what would go"}
          </button>
          {!narrowed && (
            <span className="faint">
              No filter set — that means every question in the bank.
            </span>
          )}
        </div>

        {plan && (
          <DeletionReport
            plan={plan}
            busy={busy}
            blocked={blockedByAll}
            confirmedAll={confirmedAll}
            onConfirmAll={setConfirmedAll}
            onDelete={doDelete}
          />
        )}
      </section>
    </div>
  );
}

function Backups({
  backups,
  busy,
  onCreate,
  onRestore,
  onDelete,
}: {
  backups: BackupFile[];
  busy: boolean;
  onCreate: (label: string) => void;
  onRestore: (name: string) => void;
  onDelete: (name: string) => void;
}) {
  const [label, setLabel] = useState("");

  return (
    <section className="settings-section">
      <h3>Backups</h3>

      <div className="toolbar">
        <input
          value={label}
          aria-label="Backup label"
          placeholder="What is this backup for?"
          onChange={(e) => setLabel(e.target.value)}
        />
        <button
          onClick={() => {
            onCreate(label);
            setLabel("");
          }}
          disabled={busy}
        >
          Back up now
        </button>
      </div>

      {backups.length === 0 ? (
        <div className="empty">No backups yet.</div>
      ) : (
        <table>
          <thead>
            <tr>
              <th>Backup</th>
              <th style={{ width: 150 }}>Taken</th>
              <th style={{ width: 90, textAlign: "right" }}>Size</th>
              <th style={{ width: 170 }} />
            </tr>
          </thead>
          <tbody>
            {backups.map((b) => (
              <tr key={b.name} className="q-row">
                <td className="mono">{b.name}</td>
                <td className="faint">{b.created}</td>
                <td style={{ textAlign: "right" }} className="faint">
                  {b.sizeKb} KB
                </td>
                <td>
                  <button
                    className="secondary"
                    disabled={busy}
                    onClick={() => onRestore(b.name)}
                  >
                    Restore
                  </button>{" "}
                  <button
                    className="secondary danger"
                    disabled={busy}
                    onClick={() => onDelete(b.name)}
                  >
                    Delete
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  );
}

function DeletionReport({
  plan,
  busy,
  blocked,
  confirmedAll,
  onConfirmAll,
  onDelete,
}: {
  plan: DeletionPlan;
  busy: boolean;
  blocked: boolean;
  confirmedAll: boolean;
  onConfirmAll: (v: boolean) => void;
  onDelete: () => void;
}) {
  if (plan.total === 0) {
    return (
      <div className="plan card">
        <p>Nothing matches that selection.</p>
      </div>
    );
  }

  return (
    <div className="plan card">
      <h3>
        {plan.total} {plan.total === 1 ? "question" : "questions"} would be deleted
      </h3>

      <ul className="plan-summary">
        <li className="removed">
          By status:{" "}
          {Object.entries(plan.byStatus)
            .map(([s, n]) => `${n} ${s.replace("_", " ")}`)
            .join(", ")}
        </li>
        <li className="removed">
          By certification:{" "}
          {plan.byCertification.map((c) => `${c.count} from ${c.name}`).join(", ")}
        </li>
      </ul>

      {plan.sample.length > 0 && (
        <>
          <p className="faint">For example:</p>
          <ul className="sample">
            {plan.sample.map((stem) => (
              <li key={stem}>{stem}</li>
            ))}
          </ul>
        </>
      )}

      {plan.everything && (
        <label className="check danger-check">
          <input
            type="checkbox"
            checked={confirmedAll}
            onChange={(e) => onConfirmAll(e.target.checked)}
          />
          Yes — delete every one of the {plan.total} questions in the bank
        </label>
      )}

      <div className="toolbar">
        <button className="danger" onClick={onDelete} disabled={busy || blocked}>
          {busy ? "Deleting…" : `Delete ${plan.total}`}
        </button>
        <span className="faint">This cannot be undone without a backup.</span>
      </div>
    </div>
  );
}
