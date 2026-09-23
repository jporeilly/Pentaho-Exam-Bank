import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { AdminPane } from "./AdminPane";
import type { DatabaseStatus, DeletionPlan } from "./api";

const CERTS = [
  {
    id: "cert-1", name: "DI Practitioner", description: "",
    sourceType: "pcm", sourceRef: "developer-di-practitioner", questionCount: 48,
  },
];

function dbStatus(over: Partial<DatabaseStatus> = {}): DatabaseStatus {
  return {
    database: {
      exists: true,
      path: "C:/Projects/Pentaho-Exam-Bank/assets/db/exam_bank.db",
      questions: 114,
      certifications: 3,
      size_kb: 512,
    },
    backups: [
      { name: "exam_bank_20260923_120000_before-the-cull", sizeKb: 500, created: "2026-09-23 12:00" },
    ],
    ...over,
  };
}

function plan(over: Partial<DeletionPlan> = {}): DeletionPlan {
  return {
    total: 6,
    everything: false,
    byStatus: { draft: 6 },
    byCertification: [{ id: "cert-1", name: "DI Practitioner", count: 6 }],
    sample: ["Draft question 0?", "Draft question 1?"],
    ...over,
  };
}

function mockApi(handlers: {
  status?: DatabaseStatus;
  preview?: DeletionPlan | { status: number; detail: string };
  delete?: { deleted: number } | { status: number; detail: string };
  restore?: Record<string, unknown>;
} = {}) {
  const calls: Array<{ path: string; method: string; body: unknown }> = [];
  vi.stubGlobal("fetch", (url: string, init?: RequestInit) => {
    const path = String(url);
    const method = init?.method ?? "GET";
    calls.push({ path, method, body: init?.body ? JSON.parse(String(init.body)) : null });

    const json = (body: unknown, status = 200) =>
      Promise.resolve(
        new Response(JSON.stringify(body), {
          status,
          headers: { "Content-Type": "application/json" },
        }),
      );

    if (path.includes("/delete/preview")) {
      const r = handlers.preview ?? plan();
      return "status" in r ? json({ detail: r.detail }, r.status) : json(r);
    }
    if (path.includes("/questions/delete")) {
      const r = handlers.delete ?? { deleted: 6 };
      return "status" in r ? json({ detail: r.detail }, r.status) : json(r);
    }
    if (path.includes("/restore")) {
      return json(
        handlers.restore ?? {
          restored: "a-backup",
          safetyBackup: "exam_bank_20260923_130000_pre_restore",
          ...dbStatus(),
        },
      );
    }
    if (path.includes("/admin/backups")) return json({ name: "new-backup", backups: [] });
    if (path.includes("/admin/database")) return json(handlers.status ?? dbStatus());
    return json(CERTS);
  });
  return calls;
}

async function count() {
  await userEvent.click(
    await screen.findByRole("button", { name: "Count what would go" }),
  );
}

afterEach(() => vi.unstubAllGlobals());

describe("what is shown", () => {
  it("says up front that this is the part with no undo", async () => {
    mockApi();
    render(<AdminPane />);

    expect(await screen.findByText(/no undo/)).toBeInTheDocument();
  });

  it("shows what the live database holds", async () => {
    mockApi();
    render(<AdminPane />);

    expect(await screen.findByText(/114 questions, 3 certifications/)).toBeInTheDocument();
  });

  it("lists the backups", async () => {
    mockApi();
    render(<AdminPane />);

    expect(
      await screen.findByText("exam_bank_20260923_120000_before-the-cull"),
    ).toBeInTheDocument();
  });

  it("warns before counting that no filter means the whole bank", async () => {
    mockApi();
    render(<AdminPane />);

    expect(await screen.findByText(/every question in the bank/)).toBeInTheDocument();
  });
});

describe("counting before deleting", () => {
  it("deletes nothing while counting", async () => {
    const calls = mockApi();
    render(<AdminPane />);

    await count();
    await screen.findByText(/6 questions would be deleted/);

    expect(calls.some((c) => c.path.match(/questions\/delete$/))).toBe(false);
  });

  it("breaks the set down rather than giving a bare number", async () => {
    // A number alone is not something an author can check against what they
    // meant to select.
    mockApi();
    render(<AdminPane />);

    await count();

    const report = (await screen.findByText(/6 questions would be deleted/))
      .closest(".plan") as HTMLElement;
    expect(within(report).getByText(/6 draft/)).toBeInTheDocument();
    expect(within(report).getByText(/6 from DI Practitioner/)).toBeInTheDocument();
  });

  it("shows a few of the actual questions", async () => {
    mockApi();
    render(<AdminPane />);

    await count();

    expect(await screen.findByText("Draft question 0?")).toBeInTheDocument();
  });

  it("carries the count on the button", async () => {
    // Rather than behind "Are you sure?", which says nothing about how much.
    mockApi();
    render(<AdminPane />);

    await count();

    expect(await screen.findByRole("button", { name: "Delete 6" })).toBeInTheDocument();
  });

  it("says plainly when nothing matches", async () => {
    mockApi({ preview: plan({ total: 0, byStatus: {}, byCertification: [], sample: [] }) });
    render(<AdminPane />);

    await count();

    expect(await screen.findByText(/Nothing matches/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /^Delete \d/ })).not.toBeInTheDocument();
  });

  it("drops the count when the filters change under it", async () => {
    mockApi();
    render(<AdminPane />);

    await count();
    await screen.findByText(/6 questions would be deleted/);

    await userEvent.selectOptions(screen.getByLabelText("Status"), "draft");

    expect(screen.queryByText(/6 questions would be deleted/)).not.toBeInTheDocument();
  });
});

describe("deleting the whole bank", () => {
  it("needs a second, deliberate confirmation", async () => {
    mockApi({ preview: plan({ total: 114, everything: true }) });
    render(<AdminPane />);

    await count();

    expect(await screen.findByRole("button", { name: "Delete 114" })).toBeDisabled();
    const confirm = screen.getByLabelText(/delete every one of the 114/i);
    await userEvent.click(confirm);
    expect(screen.getByRole("button", { name: "Delete 114" })).toBeEnabled();
  });

  it("does not ask for that confirmation on a narrowed set", async () => {
    mockApi();
    render(<AdminPane />);

    await count();

    expect(await screen.findByRole("button", { name: "Delete 6" })).toBeEnabled();
    expect(screen.queryByLabelText(/delete every one/i)).not.toBeInTheDocument();
  });
});

describe("deleting", () => {
  it("sends the count it was shown", async () => {
    // A mismatch means the bank changed in between, and the server refuses
    // rather than deleting a different set.
    const calls = mockApi();
    render(<AdminPane />);

    await count();
    await userEvent.click(await screen.findByRole("button", { name: "Delete 6" }));

    const sent = calls.find((c) => c.path.match(/questions\/delete$/))!;
    expect(sent.body).toMatchObject({ expect_count: 6, everything: false });
  });

  it("says how many went, and clears the count", async () => {
    mockApi();
    render(<AdminPane />);

    await count();
    await userEvent.click(await screen.findByRole("button", { name: "Delete 6" }));

    expect(await screen.findByText(/6 questions deleted/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Delete 6" })).not.toBeInTheDocument();
  });

  it("shows the server's refusal rather than inventing one", async () => {
    mockApi({
      delete: {
        status: 409,
        detail: "This was going to delete 6 questions but now matches 9.",
      },
    });
    render(<AdminPane />);

    await count();
    await userEvent.click(await screen.findByRole("button", { name: "Delete 6" }));

    expect(await screen.findByText(/now matches 9/)).toBeInTheDocument();
  });
});

describe("restoring", () => {
  it("names the backup of what it replaced, so the restore can be undone", async () => {
    mockApi();
    render(<AdminPane />);

    await userEvent.click(await screen.findByRole("button", { name: "Restore" }));

    expect(await screen.findByText(/pre_restore/)).toBeInTheDocument();
    expect(screen.getByText(/can be undone/)).toBeInTheDocument();
  });
});
