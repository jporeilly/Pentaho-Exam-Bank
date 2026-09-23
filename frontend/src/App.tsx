import { useCallback, useEffect, useRef, useState } from "react";

import { api, ApiError, type Health } from "./api";
import { BankPane } from "./BankPane";
import { CoursesPane } from "./CoursesPane";
import { AdminPane } from "./AdminPane";
import { ExamPane } from "./ExamPane";
import { GeneratePane } from "./GeneratePane";
import { ImportPane } from "./ImportPane";
import { PublishPane } from "./PublishPane";
import { SettingsPane } from "./SettingsPane";

type Tab =
  | "courses"
  | "generate"
  | "bank"
  | "import"
  | "exam"
  | "publish"
  | "settings"
  | "admin";

const TABS: Array<{ id: Tab; label: string }> = [
  { id: "courses", label: "Courses" },
  { id: "generate", label: "Generate" },
  { id: "bank", label: "Bank" },
  { id: "import", label: "Import" },
  { id: "exam", label: "Exam paper" },
  { id: "publish", label: "Publish" },
  { id: "settings", label: "Settings" },
  { id: "admin", label: "Admin" },
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

  // Opened for a course — the Content Editor's Questions button — so show
  // that course's questions rather than making the author find them again.
  // Applied once: health is refetched after a save, and snapping back to the
  // launch course every time would fight whatever the author moved to.
  const opened = useRef(false);
  useEffect(() => {
    if (opened.current || !health?.launch.courseKnown) return;
    opened.current = true;
    setTab("bank");
  }, [health]);

  const launch = health?.launch;
  const openCourse = launch?.courseKnown ? launch.course : "";

  return (
    <div className="app">
      <header className="bar">
        <span className="brand">
          <span className="tile" aria-hidden="true">
            P
          </span>
          Exam Bank
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

        {launch?.repoDisagreement && (
          // Two checkouts on one machine. Editing one course's questions
          // while believing they came from another is only noticed much
          // later, so say which one is actually being read.
          <div className="banner warn">
            <strong>Two Content Manager checkouts disagree.</strong> This app
            was opened from <code>{launch.repoDisagreement.handedOver}</code>{" "}
            but is configured to read{" "}
            <code>{launch.repoDisagreement.configured}</code>. Showing
            questions from the configured one.
          </div>
        )}

        {launch && launch.course && !launch.courseKnown && (
          <div className="banner warn">
            Opened for the course <code>{launch.course}</code>, which is not in{" "}
            {health?.courses.path || "the courses directory"}. It may have been
            renamed — check the Courses tab for the current list.
          </div>
        )}

        {tab === "courses" && <CoursesPane />}
        {tab === "generate" && (
          <GeneratePane initialCourse={openCourse} onCommitted={loadHealth} />
        )}
        {tab === "bank" && <BankPane openCourse={openCourse} onChanged={loadHealth} />}
        {tab === "import" && <ImportPane onImported={loadHealth} />}
        {tab === "exam" && <ExamPane />}
        {tab === "publish" && <PublishPane openCourse={openCourse} />}
        {tab === "settings" && <SettingsPane onSaved={loadHealth} />}
        {tab === "admin" && <AdminPane onChanged={loadHealth} />}
      </main>
    </div>
  );
}
