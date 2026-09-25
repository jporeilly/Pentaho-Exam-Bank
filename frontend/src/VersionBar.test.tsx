import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { VersionBar } from "./App";
import type { Health } from "./api";

function health(version: string, contentManagerVersion?: string): Health {
  return {
    version,
    database: { path: "C:\\bank.db", exists: true, questions: 78, certifications: 11 },
    provider: { provider: "ollama", ok: true, model: "gemma3:27b", detail: "connected" },
    courses: {
      path: "C:\\Projects\\Pentaho-Content-Manager\\courses", configured: true,
      ...(contentManagerVersion === undefined ? {} : { contentManagerVersion }),
    },
    launch: { course: "", courseKnown: false, courseTitle: "", repoDisagreement: null },
  };
}

const bar = () => document.querySelector(".statusbar .version")!;

describe("the version status bar", () => {
  it("shows the build and the Content Manager it reads, once each", () => {
    render(<VersionBar health={health(__APP_VERSION__, "0.5.0")} />);
    expect(bar().textContent).toBe(`Exam Bank v${__APP_VERSION__} · Content Manager v0.5.0`);
  });

  it("shows the backend separately, flagged, when it disagrees with the UI", () => {
    // A UI bundle from one release served by a backend from another: the
    // stale-install case the separate number exists to expose.
    render(<VersionBar health={health("9.9.9", "0.5.0")} />);
    expect(screen.getByText("· Backend v9.9.9")).toHaveClass("mismatch");
    expect(bar().textContent).toBe(
      `Exam Bank v${__APP_VERSION__} · Backend v9.9.9 · Content Manager v0.5.0`,
    );
  });

  it("still names the build when the backend is down", () => {
    render(<VersionBar health={null} />);
    expect(bar().textContent).toBe(`Exam Bank v${__APP_VERSION__}`);
  });

  it("leaves the Content Manager out when it cannot be read, or an older backend omits it", () => {
    const { unmount } = render(<VersionBar health={health(__APP_VERSION__, "")} />);
    expect(bar().textContent).toBe(`Exam Bank v${__APP_VERSION__}`);
    unmount();
    render(<VersionBar health={health(__APP_VERSION__)} />);
    expect(bar().textContent).toBe(`Exam Bank v${__APP_VERSION__}`);
  });

  it("carries the UI's real version from package.json, not a placeholder", async () => {
    const pkg = await import("../package.json");
    expect(__APP_VERSION__).toBe(pkg.version);
  });
});
