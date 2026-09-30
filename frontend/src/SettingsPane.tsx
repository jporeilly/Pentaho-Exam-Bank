/**
 * The app's configuration.
 *
 * Two things are deliberately absent. There is no field for an API key: keys
 * are read from the environment at call time and this app has never stored
 * one, so what is shown is whether a key is *present*, never its value. And
 * there is no field for the database path — moving it from a form would leave
 * the running app holding a handle to the old file.
 *
 * A setting an environment variable governs is shown but not editable, with
 * the variable named. Left editable it would save, appear to work, and revert
 * on the next start, which is worse than being told it is set elsewhere.
 */
import { useEffect, useMemo, useState } from "react";

import { api, ApiError, type DocsMcpStatus, type Settings, type SettingsResponse } from "./api";

/** One labelled control.
 *
 * The hint is a SIBLING of the `<label>`, not a child. Inside it, the label's
 * text content is "Model Set by OLLAMA_MODEL in the environment…" and that
 * whole string becomes the input's accessible name — which is what a screen
 * reader reads out, and it buries the actual label.
 */
function Field({
  label,
  hint,
  children,
}: {
  label: string;
  hint?: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <div className="field">
      <label>
        <span className="field-label">{label}</span>
        {children}
      </label>
      {hint && <span className="faint field-hint">{hint}</span>}
    </div>
  );
}

function Section({
  title,
  hint,
  children,
}: {
  title: string;
  hint?: string;
  children: React.ReactNode;
}) {
  return (
    <section className="settings-section">
      <h3>{title}</h3>
      {hint && <p className="faint section-hint">{hint}</p>}
      {children}
    </section>
  );
}

export function SettingsPane({ onSaved }: { onSaved?: () => void } = {}) {
  const [loaded, setLoaded] = useState<SettingsResponse | null>(null);
  const [draft, setDraft] = useState<Settings | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [saved, setSaved] = useState(false);

  const [mcp, setMcp] = useState<DocsMcpStatus | null>(null);
  const [checking, setChecking] = useState(false);

  function checkMcp(url = "") {
    setChecking(true);
    api
      .docsMcpStatus(url)
      .then(setMcp)
      .catch((e: unknown) =>
        setMcp({
          enabled: false, url, ok: false, server: "", version: "", tools: [], ms: null,
          searchTool: false, error: e instanceof ApiError ? e.message : String(e),
        }),
      )
      .finally(() => setChecking(false));
  }

  useEffect(() => {
    api
      .settings()
      .then((body) => {
        setLoaded(body);
        setDraft(body.settings);
        // Checked on opening only while it is on: someone who turned it off
        // may not want the docs site contacted. "Test connection" still asks.
        if (body.settings.docs_mcp_enabled) checkMcp();
      })
      .catch((e: unknown) => setError(e instanceof ApiError ? e.message : String(e)));
  }, []);

  const dirty = useMemo(
    () => Boolean(loaded && draft && JSON.stringify(draft) !== JSON.stringify(loaded.settings)),
    [draft, loaded],
  );

  if (error && !loaded) return <div className="banner">{error}</div>;
  if (!loaded || !draft) return <div className="empty">Loading settings…</div>;

  const governed = (field: keyof Settings) => loaded.envOverridden.includes(field);

  function set<K extends keyof Settings>(field: K, value: Settings[K]) {
    setDraft((d) => (d ? { ...d, [field]: value } : d));
    setSaved(false);
  }

  async function save() {
    if (!draft) return;
    setBusy(true);
    setError("");
    try {
      // Only what changed. Sending the whole set would re-submit
      // env-governed fields the author never touched, and a courses
      // directory that has since been deleted would fail a save that was
      // about something else entirely.
      const changed: Partial<Settings> = {};
      for (const key of Object.keys(draft) as Array<keyof Settings>) {
        if (draft[key] !== loaded!.settings[key]) {
          (changed[key] as Settings[typeof key]) = draft[key];
        }
      }
      const body = await api.saveSettings(changed);
      setLoaded(body);
      setDraft(body.settings);
      setSaved(true);
      if (
        body.settings.docs_mcp_enabled &&
        ("docs_mcp_url" in changed || "docs_mcp_enabled" in changed)
      ) {
        checkMcp();
      }
      onSaved?.();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  /** The hint for a field the environment governs, or nothing.
   *
   * Returned as a hint rather than rendered inside the label: anything inside
   * a `<label>` becomes part of the control's accessible name, so this text
   * would be read out in place of "Model". */
  function governedHint(field: keyof Settings): React.ReactNode {
    if (!governed(field)) return null;
    return (
      <>
        Set by <code className="mono">{loaded!.envNames[field]}</code> in the
        environment. Changing it here would not survive a restart.
      </>
    );
  }

  return (
    <div className="card settings">
      <p className="lede">
        Applies to this installation. API keys are not among these — they are
        read from the environment when a model is called and never stored by
        this app.
      </p>

      {error && <div className="banner">{error}</div>}

      <Section
        title="Who you are"
        hint="Stamped on every review action, so the audit trail says who approved what."
      >
        <label className="field">
          <span className="field-label">Your name</span>
          <input value={draft.sme_name} onChange={(e) => set("sme_name", e.target.value)} />
        </label>
      </Section>

      <Section title="The model">
        <div className="field-row">
          <label className="field">
            <span className="field-label">Provider</span>
            <select
              value={draft.ai_provider}
              onChange={(e) => set("ai_provider", e.target.value)}
            >
              {loaded.choices.providers.map((p) => (
                <option key={p} value={p}>
                  {p}
                </option>
              ))}
            </select>
          </label>

          {draft.ai_provider === "ollama" ? (
            <>
              <Field label="Ollama URL" hint={governedHint("ollama_url")}>
                <input
                  value={draft.ollama_url}
                  disabled={governed("ollama_url")}
                  onChange={(e) => set("ollama_url", e.target.value)}
                />
              </Field>
              <Field label="Model" hint={governedHint("ollama_model")}>
                <input
                  value={draft.ollama_model}
                  disabled={governed("ollama_model")}
                  onChange={(e) => set("ollama_model", e.target.value)}
                />
              </Field>
            </>
          ) : (
            <>
              <label className="field">
                <span className="field-label">Model</span>
                <input
                  value={
                    draft.ai_provider === "anthropic"
                      ? draft.anthropic_model
                      : draft.openai_model
                  }
                  onChange={(e) =>
                    set(
                      draft.ai_provider === "anthropic"
                        ? "anthropic_model"
                        : "openai_model",
                      e.target.value,
                    )
                  }
                />
              </label>
              <div className="field">
                <span className="field-label">API key</span>
                <KeyStatus
                  present={loaded.providerKeys[draft.ai_provider] ?? false}
                  variable={
                    draft.ai_provider === "anthropic"
                      ? "ANTHROPIC_API_KEY"
                      : "OPENAI_API_KEY"
                  }
                />
              </div>
            </>
          )}
        </div>

        {draft.ai_provider === "ollama" && (
          <div className="field-row">
            <Field
              label="Context window"
              hint={
                <>
                  A section longer than this is truncated silently, so the
                  Courses tab flags one against this number. 0 means the model's
                  own default, which this app cannot know — nothing is flagged.
                  {governedHint("ollama_num_ctx")}
                </>
              }
            >
              <input
                type="number"
                min={0}
                value={draft.ollama_num_ctx}
                disabled={governed("ollama_num_ctx")}
                onChange={(e) => set("ollama_num_ctx", Number(e.target.value) || 0)}
              />
            </Field>
          </div>
        )}
      </Section>

      <Section
        title="Pentaho documentation"
        hint="AI Chat searches docs.pentaho.com alongside this app's own documentation, through the MCP server GitBook publishes for the docs site."
      >
        <label className="check">
          <input
            type="checkbox"
            checked={draft.docs_mcp_enabled}
            onChange={(e) => set("docs_mcp_enabled", e.target.checked)}
          />
          Search docs.pentaho.com from AI Chat
        </label>
        <Field
          label="MCP server"
          hint={
            <>
              A GitBook docs site serves one at <code className="mono">/~gitbook/mcp</code>.
              Only a question's text is sent to it.
            </>
          }
        >
          <input
            value={draft.docs_mcp_url}
            onChange={(e) => set("docs_mcp_url", e.target.value)}
          />
        </Field>
        <McpStatus
          status={mcp}
          checking={checking}
          enabled={loaded.settings.docs_mcp_enabled}
          onTest={() => checkMcp(draft.docs_mcp_url)}
        />
      </Section>

      <Section title="Where things are">
        <Field
          label="Content Manager courses"
          hint={
            <>
              The <code className="mono">courses/</code> directory of a Content
              Manager checkout. Generating, adopting and publishing all read it.
            </>
          }
        >
          <input
            value={draft.pcm_courses_dir}
            onChange={(e) => set("pcm_courses_dir", e.target.value)}
          />
        </Field>

        <dl className="paths">
          <dt>Database</dt>
          <dd className="mono faint">{loaded.paths.database}</dd>
          <dt>Config file</dt>
          <dd className="mono faint">{loaded.paths.config}</dd>
        </dl>
      </Section>

      <Section
        title="Export and backups"
        hint="Both run on their own once switched on; neither needs the app restarted."
      >
        <div className="field-row">
          <Field
            label="Default export format"
            hint="What the Bank's Export offers first, and what auto-export writes."
          >
            <select
              value={draft.default_export_format}
              onChange={(e) => set("default_export_format", e.target.value)}
            >
              {(loaded.choices.exportFormats ?? []).map((f) => (
                <option key={f.format} value={f.format}>
                  {f.label}
                </option>
              ))}
            </select>
          </Field>
          <Field label="Export folder" hint="Where auto-export writes. Created the first time it is needed.">
            <input
              value={draft.output_folder}
              onChange={(e) => set("output_folder", e.target.value)}
            />
          </Field>
        </div>
        <label className="check">
          <input
            type="checkbox"
            checked={draft.auto_export_on_save}
            onChange={(e) => set("auto_export_on_save", e.target.checked)}
          />
          Export the whole bank to that folder after each change
        </label>
        <p className="faint field-hint">
          A couple of seconds after the last change it writes{" "}
          <code className="mono">{loaded.autoExport?.target}</code>, replacing the
          previous copy.{" "}
          {loaded.autoExport?.error
            ? `The last attempt failed: ${loaded.autoExport.error}`
            : loaded.autoExport?.at
              ? `Last written ${loaded.autoExport.at.replace("T", " ")}: ${loaded.autoExport.count} questions.`
              : ""}
        </p>

        <label className="check">
          <input
            type="checkbox"
            checked={draft.auto_backup_enabled}
            onChange={(e) => set("auto_backup_enabled", e.target.checked)}
          />
          Back up the bank automatically
        </label>
        <div className="field-row">
          <Field label="Every (hours)">
            <input
              type="number"
              min={1}
              max={168}
              value={draft.auto_backup_interval_hours}
              onChange={(e) => set("auto_backup_interval_hours", Number(e.target.value))}
            />
          </Field>
          <Field label="Keep the newest">
            <input
              type="number"
              min={1}
              max={100}
              value={draft.auto_backup_max_count}
              onChange={(e) => set("auto_backup_max_count", Number(e.target.value))}
            />
          </Field>
        </div>
        <p className="faint field-hint">
          Only automatic backups are pruned; a backup you take in Admin, and the
          safety copy a restore takes, are kept.{" "}
          {loaded.autoBackup?.error
            ? `The last automatic backup failed: ${loaded.autoBackup.error}`
            : loaded.autoBackup?.at
              ? `Last automatic backup ${loaded.autoBackup.at.replace("T", " ")}.`
              : ""}
        </p>
      </Section>

      <Section
        title="Quality"
        hint="Similarity scores between 0 and 1. Higher means stricter — fewer things get flagged."
      >
        <div className="field-row">
          <Field
            label="Duplicate threshold"
            hint="How alike two stems must be before import calls it a duplicate."
          >
            <input
              type="number"
              min={0}
              max={1}
              step={0.05}
              value={draft.duplicate_threshold}
              onChange={(e) => set("duplicate_threshold", Number(e.target.value))}
            />
          </Field>
        </div>
      </Section>

      <Section title="Defaults">
        <div className="field-row">
          <label className="field">
            <span className="field-label">Questions per page</span>
            <select
              value={draft.questions_per_page}
              onChange={(e) => set("questions_per_page", Number(e.target.value))}
            >
              {loaded.choices.pageSizes.map((n) => (
                <option key={n} value={n}>
                  {n}
                </option>
              ))}
            </select>
          </label>
          <label className="field">
            <span className="field-label">Difficulty</span>
            <select
              value={draft.default_difficulty}
              onChange={(e) => set("default_difficulty", e.target.value)}
            >
              {loaded.choices.difficulties.map((d) => (
                <option key={d} value={d}>
                  {d}
                </option>
              ))}
            </select>
          </label>
          <label className="field">
            <span className="field-label">Bloom level</span>
            <select
              value={draft.default_bloom_level}
              onChange={(e) => set("default_bloom_level", e.target.value)}
            >
              {loaded.choices.bloomLevels.map((b) => (
                <option key={b} value={b}>
                  {b}
                </option>
              ))}
            </select>
          </label>
        </div>
      </Section>

      <div className="toolbar">
        <button onClick={save} disabled={!dirty || busy}>
          {busy ? "Saving…" : "Save"}
        </button>
        {saved && !dirty && <span className="muted">Saved</span>}
        {dirty && <span className="faint">Unsaved changes.</span>}
      </div>
    </div>
  );
}

/** The docs server's state: connected (who, how fast, which tools) or why not. */
function McpStatus({
  status,
  checking,
  enabled,
  onTest,
}: {
  status: DocsMcpStatus | null;
  checking: boolean;
  enabled: boolean;
  onTest: () => void;
}) {
  let line: React.ReactNode;
  if (checking) {
    line = <span className="faint">Checking…</span>;
  } else if (!status) {
    line = enabled ? (
      <span className="faint">Not checked yet.</span>
    ) : (
      <span className="faint">Off: AI Chat does not contact the docs site.</span>
    );
  } else if (status.ok) {
    line = (
      <>
        <span className="dot ok" />
        <span>
          <strong>Connected</strong> — {status.server || "MCP server"}
          {status.version && ` ${status.version}`}, answered in {status.ms} ms
        </span>
      </>
    );
  } else {
    line = (
      <>
        <span className="dot bad" />
        <span>
          <strong>Not connected</strong> — {status.error}
        </span>
      </>
    );
  }

  return (
    <div className="mcp-status" aria-live="polite">
      <div className="mcp-line">
        {line}
        <span className="spacer" />
        <button type="button" className="secondary" onClick={onTest} disabled={checking}>
          Test connection
        </button>
      </div>
      {status?.ok && !checking && (
        <div className="mcp-detail faint">
          <span className="mono">{status.url}</span>
          <span>
            Tools: {status.tools.join(", ") || "none"}.{" "}
            {status.searchTool ? (
              "Search tool available."
            ) : (
              <span className="advice">
                No searchDocumentation tool, so AI Chat cannot search this server.
              </span>
            )}
          </span>
        </div>
      )}
    </div>
  );
}

function KeyStatus({ present, variable }: { present: boolean; variable: string }) {
  return (
    <span className="key-status">
      <span className={`dot ${present ? "ok" : "bad"}`} />
      {present ? (
        <>
          <code className="mono">{variable}</code> is set
        </>
      ) : (
        <>
          <code className="mono">{variable}</code> is not set, so this provider
          cannot be used
        </>
      )}
    </span>
  );
}
