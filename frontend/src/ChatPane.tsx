/**
 * Content → AI Chat: ask about the Exam Bank, or about Pentaho's products.
 *
 * Every answer is built from two searches — this app's documentation and
 * docs.pentaho.com — and lists what it was given, numbered the way it cites
 * it: A1 opens that page in Documentation at its heading, P1 opens the
 * Pentaho page in the browser. When neither search finds anything the
 * backend does not ask the model at all, and this says so rather than
 * showing a guess.
 *
 * The conversation is kept in this window's storage until "New
 * conversation", so leaving for the Bank and coming back does not lose it.
 * It is not in the bank and not in its backups.
 */
import { useEffect, useRef, useState } from "react";
import { CircleStop, ExternalLink, RotateCcw, Send } from "lucide-react";

import { api, ApiError, type ChatAnswer, type ChatSource, type ChatTurn } from "./api";
import { DocMarkdown, openExternal } from "./DocMarkdown";
import { linkCitations } from "./docLinks";

type Turn =
  | { role: "user"; content: string }
  | { role: "assistant"; content: string; answer: ChatAnswer }
  | { role: "error"; content: string };

interface Sources {
  appDocs: boolean;
  pentahoDocs: boolean;
}

const HISTORY_KEY = "peb-chat";
const SOURCES_KEY = "peb-chat-sources";
const KEEP = 60;

const STARTERS = [
  "How do I publish an exam so learners get it?",
  "What does draw headroom mean on the Report?",
  "Which ports does Pentaho Server use?",
  "How do I send an approved question back for review?",
];

function loadJson<T>(key: string, fallback: T, ok: (v: unknown) => boolean): T {
  try {
    const v = JSON.parse(window.localStorage.getItem(key) ?? "null");
    return ok(v) ? (v as T) : fallback;
  } catch {
    return fallback;
  }
}
function saveJson(key: string, value: unknown) {
  try {
    window.localStorage.setItem(key, JSON.stringify(value));
  } catch {
    /* a conversation that is not remembered is still a conversation */
  }
}

/** What goes back to the model as the conversation so far: the questions,
 *  and the answers that were actually answers. */
export function historyOf(turns: Turn[]): ChatTurn[] {
  return turns.flatMap((t): ChatTurn[] => {
    if (t.role === "user") return [{ role: "user", content: t.content }];
    if (t.role === "assistant" && t.answer.answered && !t.answer.stopped) {
      return [{ role: "assistant", content: t.content }];
    }
    return [];
  });
}

export function ChatPane({
  onOpenDoc,
}: {
  onOpenDoc: (slug: string, anchor: string) => void;
}) {
  const [turns, setTurns] = useState<Turn[]>(() =>
    loadJson<Turn[]>(HISTORY_KEY, [], (v) => Array.isArray(v)),
  );
  const [sources, setSources] = useState<Sources>(() =>
    loadJson<Sources>(SOURCES_KEY, { appDocs: true, pentahoDocs: true }, (v) =>
      typeof v === "object" && v !== null && "appDocs" in v,
    ),
  );
  const [mcp, setMcp] = useState<{ enabled: boolean; host: string }>({
    enabled: true,
    host: "docs.pentaho.com",
  });
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  // The answer being written: its sources as soon as the search is done, then
  // the text as the model writes it. Moved into `turns` when it is finished.
  const [live, setLive] = useState<ChatAnswer | null>(null);
  const controller = useRef<AbortController | null>(null);
  const logRef = useRef<HTMLDivElement>(null);

  // Whether the docs connection is on is a Settings matter; read it, do not
  // probe it — a probe is a network call, and Settings is where it is shown.
  useEffect(() => {
    api
      .settings()
      .then(({ settings }) => {
        let host = "docs.pentaho.com";
        try {
          host = new URL(settings.docs_mcp_url).hostname || host;
        } catch {
          /* keep the default name */
        }
        setMcp({ enabled: settings.docs_mcp_enabled, host });
      })
      .catch(() => {
        /* the chat still works; the switch just keeps its default */
      });
  }, []);

  useEffect(() => saveJson(HISTORY_KEY, turns.slice(-KEEP)), [turns]);
  useEffect(() => saveJson(SOURCES_KEY, sources), [sources]);
  useEffect(() => {
    const el = logRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [turns, busy, live]);

  const pentahoOn = sources.pentahoDocs && mcp.enabled;
  const noSource = !sources.appDocs && !pentahoOn;

  async function ask(text: string) {
    const question = text.trim();
    if (!question || busy || noSource) return;
    const history = historyOf(turns);
    setTurns((t) => [...t, { role: "user", content: question }]);
    setInput("");
    setBusy(true);
    const ac = new AbortController();
    controller.current = ac;
    let current = null as ChatAnswer | null;
    let finished = false;
    // What was written before a stop or a failure stays on screen, marked.
    const keep = (why: string) => {
      const partial = current;
      if (partial && partial.answer.trim()) {
        setTurns((t) => [...t, { role: "assistant", content: partial.answer,
                                 answer: { ...partial, stopped: true } }]);
      }
      if (why) setTurns((t) => [...t, { role: "error", content: why }]);
    };
    try {
      await api.chatStream(
        [...history, { role: "user", content: question }],
        { appDocs: sources.appDocs, pentahoDocs: pentahoOn },
        (event) => {
          if (event.type === "sources") {
            current = { answered: true, answer: "", sources: event.sources, grounding: event.grounding };
            setLive(current);
          } else if (event.type === "token" && current) {
            current = { ...current, answer: current.answer + event.text };
            setLive(current);
          } else if (event.type === "done") {
            finished = true;
            const { type: _type, ...answer } = event;
            setTurns((t) => [...t, { role: "assistant", content: answer.answer, answer }]);
            setLive(null);
          } else if (event.type === "error") {
            finished = true;
            setLive(null);
            keep(event.message);
          }
        },
        ac.signal,
      );
      if (!finished) {
        setLive(null);
        keep("The answer broke off before it finished.");
      }
    } catch (e) {
      setLive(null);
      if (ac.signal.aborted) {
        keep(current && current.answer.trim() ? "" : "Stopped. Nothing was answered.");
      } else {
        keep(e instanceof ApiError ? e.message : String(e));
      }
    } finally {
      setBusy(false);
      controller.current = null;
    }
  }

  function openSource(s: ChatSource) {
    if (s.kind === "app") onOpenDoc(s.slug, s.anchor);
    else if (s.url) openExternal(s.url);
  }

  return (
    <div className="chat">
      <div className="chat-head">
        <p className="lede">
          Ask about the Exam Bank or about Pentaho's products. Answers come only
          from this app's documentation and {mcp.host}, and list the pages they
          were built from.
        </p>
        <div className="chat-tools">
          <span className="faint">Search</span>
          <label className="check">
            <input
              type="checkbox"
              checked={sources.appDocs}
              disabled={busy || (sources.appDocs && !pentahoOn)}
              onChange={(e) => setSources((s) => ({ ...s, appDocs: e.target.checked }))}
            />
            This app's docs
          </label>
          <label
            className="check"
            title={mcp.enabled ? "" : "The Pentaho docs connection is off in Settings."}
          >
            <input
              type="checkbox"
              checked={pentahoOn}
              disabled={busy || !mcp.enabled || (pentahoOn && !sources.appDocs)}
              onChange={(e) => setSources((s) => ({ ...s, pentahoDocs: e.target.checked }))}
            />
            {mcp.host}
          </label>
          {!mcp.enabled && <span className="faint">off in Settings</span>}
          <span className="spacer" />
          <button
            type="button"
            className="secondary"
            disabled={busy || turns.length === 0}
            onClick={() => setTurns([])}
          >
            <RotateCcw size={14} aria-hidden="true" /> New conversation
          </button>
        </div>
      </div>

      <div className="chat-log" ref={logRef} aria-live="polite">
        {turns.length === 0 && (
          <div className="chat-empty">
            <p className="faint">Try one of these, or ask your own.</p>
            <div className="chat-starters">
              {STARTERS.map((s) => (
                <button type="button" key={s} className="secondary ai" onClick={() => ask(s)} disabled={noSource}>
                  {s}
                </button>
              ))}
            </div>
          </div>
        )}

        {turns.map((t, i) => {
          if (t.role === "user") {
            return (
              <div key={i} className="turn user">
                {t.content}
              </div>
            );
          }
          if (t.role === "error") {
            return (
              <div key={i} className="turn error" role="alert">
                {t.content}
              </div>
            );
          }
          return <Answer key={i} answer={t.answer} onOpen={openSource} />;
        })}

        {live && <Answer answer={live} onOpen={openSource} writing />}
        {busy && !live?.answer && (
          <div className="turn busy faint">
            {live ? "Asking the model…" : "Searching the documentation, then asking the model…"}
          </div>
        )}
      </div>

      <form
        className="chat-input"
        onSubmit={(e) => {
          e.preventDefault();
          ask(input);
        }}
      >
        <textarea
          rows={2}
          value={input}
          aria-label="Your question"
          placeholder="Ask a question. Enter sends; Shift+Enter starts a new line."
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              ask(input);
            }
          }}
        />
        {busy ? (
          <button type="button" className="secondary danger" onClick={() => controller.current?.abort()}>
            <CircleStop size={14} aria-hidden="true" /> Stop
          </button>
        ) : (
          <button type="submit" className="ai" disabled={!input.trim() || noSource}>
            <Send size={14} aria-hidden="true" /> Ask
          </button>
        )}
      </form>
    </div>
  );
}

function Answer({
  answer,
  onOpen,
  writing = false,
}: {
  answer: ChatAnswer;
  onOpen: (s: ChatSource) => void;
  /** Still being written: the text grows, and there is nothing to sign off. */
  writing?: boolean;
}) {
  const byId = new Map(answer.sources.map((s) => [s.id, s]));
  const app = answer.sources.filter((s) => s.kind === "app");
  const pentaho = answer.sources.filter((s) => s.kind === "pentaho");
  const failed = answer.grounding.pentaho.error;
  const host = answer.grounding.pentaho.host;

  return (
    <div className="turn assistant">
      {answer.answered ? (
        <DocMarkdown
          content={linkCitations(answer.answer)}
          onCite={(id) => {
            const s = byId.get(id);
            if (s) onOpen(s);
          }}
        />
      ) : (
        <p className="not-covered">
          <strong>Not covered.</strong> {answer.answer}
        </p>
      )}

      {answer.stopped && (
        <p className="advice">Stopped before it finished. It is not sent back with a follow-up.</p>
      )}

      {answer.answered && failed && (
        <p className="advice">
          {host} could not be searched: {failed} This answer is from this app's
          documentation only.
        </p>
      )}

      {app.length > 0 && <SourceList title="From this app's documentation" items={app} onOpen={onOpen} />}
      {pentaho.length > 0 && <SourceList title={`From ${host}`} items={pentaho} onOpen={onOpen} />}

      {answer.answered && answer.model && !writing && !answer.stopped && (
        <div className="turn-meta faint">
          Answered by {answer.model} via {answer.provider}
        </div>
      )}
    </div>
  );
}

function SourceList({
  title,
  items,
  onOpen,
}: {
  title: string;
  items: ChatSource[];
  onOpen: (s: ChatSource) => void;
}) {
  return (
    <div className="sources-group">
      <div className="sources-title faint">{title}</div>
      <ul className="chat-sources">
        {items.map((s) => (
          <li key={s.id}>
            <button
              type="button"
              className={"source" + (s.cited ? "" : " uncited")}
              title={(s.cited ? "" : "Given to the model; not cited in the answer.\n\n") + s.snippet}
              onClick={() => onOpen(s)}
            >
              <span className="cite">{s.id}</span>
              <span>{s.heading ? `${s.title} › ${s.heading}` : s.title}</span>
              {s.kind === "pentaho" && <ExternalLink size={12} aria-hidden="true" />}
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}
