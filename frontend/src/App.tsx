import { useCallback, useEffect, useRef, useState } from "react";

import { api, ApiError, type Health } from "./api";
import { BankPane } from "./BankPane";
import { CoursesPane } from "./CoursesPane";
import { AdminPane } from "./AdminPane";
import { ChatPane } from "./ChatPane";
import { DocsPane, type DocTarget } from "./DocsPane";
import { ExamPane } from "./ExamPane";
import { GeneratePane } from "./GeneratePane";
import { ImportPane } from "./ImportPane";
import { PublishPane } from "./PublishPane";
import { ReportPane } from "./ReportPane";
import { SettingsPane } from "./SettingsPane";
import { SideNav, type Tab } from "./SideNav";

export function App() {
  const [tab, setTab] = useState<Tab>("courses");
  const [health, setHealth] = useState<Health | null>(null);
  const [healthError, setHealthError] = useState<string>("");
  // A page for Documentation to open, asked for by an AI Chat source.
  const [docTarget, setDocTarget] = useState<DocTarget | null>(null);
  const openDoc = useCallback((slug: string, anchor: string) => {
    setDocTarget((t) => ({ slug, anchor, seq: (t?.seq ?? 0) + 1 }));
    setTab("docs");
  }, []);

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
          </>
        )}
      </header>

      <div className="shell">
        <SideNav
          tab={tab}
          onSelect={setTab}
          questions={health?.database.questions}
        />

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
        {tab === "report" && <ReportPane openCourse={openCourse} />}
        {tab === "import" && <ImportPane onImported={loadHealth} />}
        {tab === "exam" && <ExamPane />}
        {tab === "publish" && <PublishPane openCourse={openCourse} />}
        {tab === "settings" && <SettingsPane onSaved={loadHealth} />}
        {tab === "admin" && <AdminPane onChanged={loadHealth} />}
        {tab === "chat" && <ChatPane onOpenDoc={openDoc} />}
        {tab === "docs" && (
          <DocsPane target={docTarget} onTargetDone={() => setDocTarget(null)} />
        )}
        </main>
      </div>

      <VersionBar health={health} />
    </div>
  );
}

/**
 * Which build, reading which content - the Content Editor's status-bar
 * pairing ("Course v… · Editor v… · Engine v…"), so a screenshot from either
 * app identifies itself.
 *
 * The UI's version is baked in at build time and the backend's comes over the
 * API. They normally agree and only one is shown; when they differ both are,
 * because that is a stale install - a UI bundle from one release served by a
 * backend from another - and it explains behaviour nothing else would.
 */
export function VersionBar({ health }: { health: Health | null }) {
  const ui = __APP_VERSION__;
  const backend = health?.version ?? "";
  const mismatch = backend !== "" && backend !== ui;
  const cm = health?.courses.contentManagerVersion ?? "";
  return (
    <footer className="statusbar">
      <span
        className="version"
        title={
          "This Exam Bank's build, and the Content Manager whose courses it reads.\n\n" +
          "The interface and the backend are versioned together. If they ever show " +
          "different numbers, the install is part one release and part another; " +
          "reinstall to bring them back into step.\n\n" +
          "The Content Manager version is read from the package.json beside the " +
          "configured courses folder."
        }
      >
        Exam Bank v{ui}
        {mismatch && <span className="mismatch"> · Backend v{backend}</span>}
        {cm && ` · Content Manager v${cm}`}
      </span>
    </footer>
  );
}
