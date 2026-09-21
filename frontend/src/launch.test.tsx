import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { App } from "./App";
import type { Health, LaunchContext } from "./api";

function health(launch: Partial<LaunchContext> = {}): Health {
  return {
    version: "0.1.0",
    database: { path: "C:\\bank.db", exists: true, questions: 68, certifications: 2 },
    provider: { provider: "ollama", ok: true, model: "gemma3:27b", detail: "connected" },
    courses: { path: "C:\\Projects\\Pentaho-Content-Manager\\courses", configured: true },
    launch: {
      course: "", courseKnown: false, courseTitle: "", repoDisagreement: null, ...launch,
    },
  };
}

const CERTS = [
  { id: "c-pdi", name: "PDI in 2 Hours", description: "", sourceType: "pcm",
    sourceRef: "pdi-2hr-lab", questionCount: 20 },
  { id: "c-di", name: "DI Practitioner", description: "", sourceType: "pcm",
    sourceRef: "developer-di-practitioner", questionCount: 48 },
];

function mockApi(h: Health) {
  const calls: string[] = [];
  vi.stubGlobal("fetch", (url: string) => {
    const path = String(url);
    calls.push(path);
    const body = path.includes("/api/health")
      ? h
      : path.includes("/api/certifications")
        ? CERTS
        : path.includes("/api/questions")
          ? { items: [], total: 0, limit: 25, offset: 0 }
          : [];
    return Promise.resolve(
      new Response(JSON.stringify(body), { headers: { "Content-Type": "application/json" } }),
    );
  });
  return calls;
}

afterEach(() => vi.unstubAllGlobals());

describe("opened for a course", () => {
  it("opens on the Bank, filtered to that course's questions", async () => {
    // The point of the handover: the author clicked Questions on a course and
    // should be looking at that course's pool, not picking it again.
    const calls = mockApi(health({
      course: "pdi-2hr-lab", courseKnown: true, courseTitle: "PDI in 2 Hours",
    }));
    render(<App />);

    await waitFor(() =>
      expect(screen.getByRole("button", { name: "Bank" })).toHaveAttribute(
        "aria-current", "page",
      ),
    );
    await waitFor(() =>
      expect(calls.some((c) => c.includes("certification_id=c-pdi"))).toBe(true),
    );
  });

  it("stays on Courses when nothing was handed over", async () => {
    mockApi(health());
    render(<App />);
    await waitFor(() =>
      expect(screen.getByRole("button", { name: "Courses" })).toHaveAttribute(
        "aria-current", "page",
      ),
    );
  });

  it("says so when the course no longer resolves", async () => {
    // A slug that stopped resolving after a rename is how the bank's original
    // certifications died, silently. It must not look like an empty bank.
    mockApi(health({ course: "developer-practitioner", courseKnown: false }));
    render(<App />);

    expect(await screen.findByText(/which is not in/)).toBeInTheDocument();
    expect(screen.getByText("developer-practitioner")).toBeInTheDocument();
  });

  it("says so when the course has never been adopted", async () => {
    mockApi(health({
      course: "developer-ml-specialty", courseKnown: true, courseTitle: "ML",
    }));
    render(<App />);

    expect(await screen.findByText(/has not been adopted into the bank yet/))
      .toBeInTheDocument();
    // And it names the command that brings them in, rather than leaving an
    // unexplained empty table.
    expect(screen.getByText(/migrate_pcm_exams\.py developer-ml-specialty/))
      .toBeInTheDocument();
  });
});

describe("two checkouts", () => {
  it("names both paths and which one is being read", async () => {
    // Editing one checkout's questions while believing they came from another
    // is only noticed much later.
    mockApi(health({
      course: "pdi-2hr-lab", courseKnown: true,
      repoDisagreement: {
        handedOver: "D:\\other-pcm\\courses",
        configured: "C:\\Projects\\Pentaho-Content-Manager\\courses",
        using: "C:\\Projects\\Pentaho-Content-Manager\\courses",
      },
    }));
    render(<App />);

    expect(await screen.findByText(/Two Content Manager checkouts disagree/))
      .toBeInTheDocument();
    expect(screen.getByText("D:\\other-pcm\\courses")).toBeInTheDocument();
    expect(screen.getAllByText("C:\\Projects\\Pentaho-Content-Manager\\courses").length)
      .toBeGreaterThan(0);
  });

  it("says nothing when the paths agree", async () => {
    mockApi(health({ course: "pdi-2hr-lab", courseKnown: true }));
    render(<App />);
    await screen.findByText(/68 questions/);
    expect(screen.queryByText(/checkouts disagree/)).not.toBeInTheDocument();
  });
});
