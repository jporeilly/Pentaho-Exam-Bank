/**
 * The app's own documentation: ask it, search it, read it.
 *
 * The asking is the part that needed care. A model asked "how do I publish
 * back to a course?" answers *something* whether or not it was given anything
 * to read — it knows what apps like this generally do — and a confident
 * invention about a tool somebody is about to use is worse than no answer.
 *
 * So retrieval decides, on the server: if nothing in the documentation
 * matches, the model is never called and this says so. When it is called, the
 * sections it read come back with the answer and are shown underneath it. An
 * answer about your own app is only worth anything if you can check what it
 * was built from.
 */
import { useEffect, useState } from "react";

import {
  api,
  ApiError,
  type DocAnswer,
  type DocDocument,
  type DocSearchResult,
} from "./api";

type Mode = "ask" | "search" | "read";

const MODES: Array<{ id: Mode; label: string }> = [
  { id: "ask", label: "Ask" },
  { id: "search", label: "Search" },
  { id: "read", label: "Read" },
];

export function DocsPane() {
  const [mode, setMode] = useState<Mode>("ask");

  return (
    <div className="card docs">
      <p className="lede">
        Answers come from this app's own guide and README — never from outside
        them. If the documentation does not cover a question, you are told
        that rather than given a guess.
      </p>

      <div className="toolbar segmented">
        {MODES.map((m) => (
          <button
            key={m.id}
            className={mode === m.id ? "" : "secondary"}
            aria-pressed={mode === m.id}
            onClick={() => setMode(m.id)}
          >
            {m.label}
          </button>
        ))}
      </div>

      {mode === "ask" && <Ask />}
      {mode === "search" && <Search />}
      {mode === "read" && <Read />}
    </div>
  );
}

function Ask() {
  const [question, setQuestion] = useState("");
  const [answer, setAnswer] = useState<DocAnswer | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function ask() {
    const text = question.trim();
    if (!text) return;
    setBusy(true);
    setError("");
    setAnswer(null);
    try {
      setAnswer(await api.askDocs(text));
    } catch (e) {
      setError(e instanceof ApiError ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <div className="toolbar">
        <input
          value={question}
          aria-label="Your question"
          placeholder="How do I import a CSV of questions?"
          onChange={(e) => setQuestion(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") ask();
          }}
        />
        {/* "Ask the guide", not "Ask": the mode above is already called Ask,
            and naming what is being asked is the point of the pane. */}
        <button onClick={ask} disabled={busy || !question.trim()}>
          {busy ? "Reading the docs…" : "Ask the guide"}
        </button>
      </div>

      {error && <div className="banner">{error}</div>}

      {answer && (
        <div className="plan card">
          {answer.answered ? (
            <>
              <p className="answer">{answer.answer}</p>
              <h3>Built from</h3>
              <ul className="sources">
                {answer.sources.map((s) => (
                  <li key={`${s.document}-${s.heading}`}>
                    <strong>{s.heading}</strong>{" "}
                    <span className="faint">— {s.document}</span>
                    <div className="faint">{s.snippet}</div>
                  </li>
                ))}
              </ul>
              {answer.model && (
                <p className="faint">
                  Answered by {answer.model} via {answer.provider}, reading only
                  the sections above.
                </p>
              )}
            </>
          ) : (
            // The model was never called. Saying so is the point: an answer
            // invented from outside the documentation is the failure this
            // whole pane is arranged to avoid.
            <>
              <h3>Not covered</h3>
              <p>{answer.answer}</p>
            </>
          )}
        </div>
      )}
    </>
  );
}

function Search() {
  const [query, setQuery] = useState("");
  const [found, setFound] = useState<DocSearchResult | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    const text = query.trim();
    if (!text) {
      setFound(null);
      return;
    }
    // Debounced: this searches on every keystroke, and a request per
    // character is both wasteful and out of order by the time it lands.
    const timer = setTimeout(() => {
      api
        .searchDocs(text)
        .then((r) => {
          setFound(r);
          setError("");
        })
        .catch((e: unknown) => setError(e instanceof ApiError ? e.message : String(e)));
    }, 200);
    return () => clearTimeout(timer);
  }, [query]);

  return (
    <>
      <div className="toolbar">
        <input
          value={query}
          aria-label="Search the documentation"
          placeholder="backup, import, certification…"
          onChange={(e) => setQuery(e.target.value)}
        />
      </div>

      {error && <div className="banner">{error}</div>}

      {found && found.results.length === 0 && (
        <div className="empty">
          Nothing about “{found.query}” in {found.sectionsSearched} sections of
          documentation.
        </div>
      )}

      {found && found.results.length > 0 && (
        <ul className="sources">
          {found.results.map((s) => (
            <li key={`${s.document}-${s.heading}`}>
              <strong>{s.heading}</strong>{" "}
              <span className="faint">— {s.document}</span>
              <div className="faint">{s.snippet}</div>
            </li>
          ))}
        </ul>
      )}
    </>
  );
}

function Read() {
  const [documents, setDocuments] = useState<DocDocument[] | null>(null);
  const [open, setOpen] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    api
      .documents()
      .then((d) => {
        setDocuments(d);
        setOpen(d[0]?.document ?? "");
      })
      .catch((e: unknown) => setError(e instanceof ApiError ? e.message : String(e)));
  }, []);

  if (error) return <div className="banner">{error}</div>;
  if (!documents) return <div className="empty">Loading…</div>;
  if (documents.length === 0)
    return <div className="empty">No documentation was found beside the app.</div>;

  const current = documents.find((d) => d.document === open) ?? documents[0];

  return (
    <>
      <div className="toolbar segmented">
        {documents.map((d) => (
          <button
            key={d.document}
            className={d.document === current.document ? "" : "secondary"}
            aria-pressed={d.document === current.document}
            onClick={() => setOpen(d.document)}
          >
            {d.document}
          </button>
        ))}
      </div>

      <div className="doc-body">
        {current.sections.map((s) => (
          <section key={s.heading}>
            <h3>{s.heading}</h3>
            {/* Rendered as plain text, deliberately. These are markdown files
                and this is a reading pane, not a renderer — and text that is
                shown rather than interpreted cannot carry anything. */}
            <pre>{s.text}</pre>
          </section>
        ))}
      </div>
    </>
  );
}
