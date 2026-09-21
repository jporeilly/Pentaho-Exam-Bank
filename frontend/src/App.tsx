import { useCallback, useEffect, useState } from "react";

import { api, ApiError, type Health } from "./api";
import { BankPane } from "./BankPane";
import { CoursesPane } from "./CoursesPane";
import { GeneratePane } from "./GeneratePane";

type Tab = "courses" | "generate" | "bank";

const TABS: Array<{ id: Tab; label: string }> = [
  { id: "courses", label: "Courses" },
  { id: "generate", label: "Generate" },
  { id: "bank", label: "Bank" },
];

export function App() {
  const [tab, setTab] = useState<Tab>("courses");
  const [health, setHealth] = useState<Health | null>(null);
  const [healthError, setHealthError] = useState<string>("");

  const loadHealth = useCallback(() => {
    api
      .health()
      .then((h) => {
        setHealth(h);
        setHealthError("");
      })
      .catch((e: unknown) => {
        setHealth(null);
        setHealthError(e instanceof ApiError ? e.message : String(e));
      });
  }, []);

  useEffect(loadHealth, [loadHealth]);

  return (
    <div className="app">
      <header className="bar">
        <span className="brand">
          <span className="tile" aria-hidden="true">
            P
          </span>
          Question Bank
        </span>

        <nav className="tabs">
          {TABS.map((t) => (
            <button
              key={t.id}
              onClick={() => setTab(t.id)}
              aria-current={tab === t.id ? "page" : undefined}
            >
              {t.label}
            </button>
          ))}
        </nav>

        <span className="spacer" />

        {health && (
          <>
            <span className="status" title={health.database.path}>
              {health.database.questions} questions
              <span className="faint">/</span>
              {health.database.certifications} certifications
            </span>
            <span
              className="status"
              title={`${health.provider.provider}: ${health.provider.detail}`}
            >
              <span className={`dot ${health.provider.ok ? "ok" : "bad"}`} />
              {health.provider.ok ? health.provider.model : "no model"}
            </span>
            <span className="status faint">v{health.version}</span>
          </>
        )}
      </header>

      <main>
        {healthError && (
          // The backend being down is the one failure that makes every pane
          // useless, so it is said once here rather than repeated in each.
          <div className="banner">
            {healthError}{" "}
            <button className="secondary" onClick={loadHealth}>
              Retry
            </button>
          </div>
        )}

        {!healthError && health && !health.courses.configured && (
          <div className="banner warn">
            No Content Manager courses directory is configured, so there is
            nothing to generate from or adopt.
          </div>
        )}

        {tab === "courses" && <CoursesPane />}
        {tab === "generate" && <GeneratePane onCommitted={loadHealth} />}
        {tab === "bank" && <BankPane onChanged={loadHealth} />}
      </main>
    </div>
  );
}
