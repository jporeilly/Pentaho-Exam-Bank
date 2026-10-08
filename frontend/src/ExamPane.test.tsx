import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ExamPane } from "./ExamPane";
import type { ExamPlan, ExamTopic, TopicOutcome } from "./api";

const CERTS = [
  {
    id: "cert-1", name: "DI Practitioner", description: "",
    sourceType: "pcm", sourceRef: "developer-di-practitioner", questionCount: 48,
  },
  {
    id: "cert-2", name: "BA Practitioner", description: "",
    sourceType: "pcm", sourceRef: "analyst-ba-practitioner", questionCount: 44,
  },
];

const TOPICS: ExamTopic[] = [
  { topic: "Networking", questionCount: 10 },
  { topic: "Security", questionCount: 8 },
  { topic: "Cloud", questionCount: 3 },
];

function outcome(over: Partial<TopicOutcome> = {}): TopicOutcome {
  return {
    topic: "Networking", weight: 34, wanted: 3, available: 10,
    selected: 3, short: 0, lent: 0, ...over,
  };
}

function plan(over: Partial<ExamPlan> = {}): ExamPlan {
  return {
    requested: 9, selected: 9, shortfall: 0, redistributed: 0, honoured: true,
    topics: [outcome()],
    ...over,
  };
}

function mockApi(handlers: {
  topics?: ExamTopic[];
  plan?: ExamPlan | { status: number; detail: string };
} = {}) {
  const calls: Array<{ path: string; body: unknown }> = [];
  vi.stubGlobal("fetch", (url: string, init?: RequestInit) => {
    const path = String(url);
    calls.push({ path, body: init?.body ? JSON.parse(String(init.body)) : null });

    const json = (body: unknown, status = 200) =>
      Promise.resolve(
        new Response(JSON.stringify(body), {
          status,
          headers: { "Content-Type": "application/json" },
        }),
      );

    if (path.includes("/exam/topics")) return json(handlers.topics ?? TOPICS);
    if (path.includes("/exam/plan")) {
      const r = handlers.plan ?? plan();
      return "status" in r ? json({ detail: r.detail }, r.status) : json(r);
    }
    return json(CERTS);
  });
  return calls;
}

async function pickCertification() {
  await userEvent.click(await screen.findByRole("checkbox", { name: /DI Practitioner/ }));
}

afterEach(() => vi.unstubAllGlobals());

describe("setting up the weighting", () => {
  it("asks for nothing until a certification is chosen", async () => {
    const calls = mockApi();
    render(<ExamPane />);

    expect(await screen.findByText(/Choose a certification/)).toBeInTheDocument();
    expect(calls.some((c) => c.path.includes("/exam/topics"))).toBe(false);
  });

  it("lists every certification as a checkbox, with its question count", async () => {
    // The multi-select it replaced showed four rows and hid the rest behind a
    // scroll; every certification is now on screen at once.
    mockApi();
    render(<ExamPane />);

    const group = await screen.findByRole("group", { name: "Draw from" });
    const boxes = await within(group).findAllByRole("checkbox");
    expect(boxes).toHaveLength(2);
    expect(within(group).getByText("48")).toBeInTheDocument();
    expect(within(group).getByText("44")).toBeInTheDocument();
    expect(screen.getByText("2 certifications")).toBeInTheDocument();
  });

  it("selects all and clears in one click, and counts what is chosen", async () => {
    mockApi();
    render(<ExamPane />);

    await userEvent.click(await screen.findByRole("button", { name: "Select all" }));
    expect(screen.getByRole("checkbox", { name: /DI Practitioner/ })).toBeChecked();
    expect(screen.getByRole("checkbox", { name: /BA Practitioner/ })).toBeChecked();
    expect(screen.getByText("2 of 2 chosen · 92 questions")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Select all" })).toBeDisabled();

    await userEvent.click(screen.getByRole("button", { name: "Clear" }));
    expect(screen.getByRole("checkbox", { name: /DI Practitioner/ })).not.toBeChecked();
    expect(screen.getByRole("button", { name: "Clear" })).toBeDisabled();
  });

  it("says why the buttons are disabled", async () => {
    mockApi();
    render(<ExamPane />);

    expect(await screen.findByText("Choose at least one certification.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Build the paper" })).toBeDisabled();

    await pickCertification();
    expect(await screen.findByText("21 questions at the statuses chosen")).toBeInTheDocument();
    expect(screen.queryByText("Choose at least one certification.")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Build the paper" })).toBeEnabled();
  });

  it("draws difficulty and review status as labelled groups of checkboxes", async () => {
    mockApi();
    render(<ExamPane />);

    const status = await screen.findByRole("group", { name: "Review status" });
    expect(within(status).getByRole("checkbox", { name: "Approved" })).toBeChecked();
    expect(within(status).getByRole("checkbox", { name: "Drafts" })).not.toBeChecked();
    expect(screen.getByRole("group", { name: "Difficulty" })).toBeInTheDocument();
  });

  it("splits the topics evenly to a total of 100", async () => {
    // Three topics divide as 34/33/33, not 34/33/33 with an outlier, and not
    // 33/33/33 which the server would refuse.
    mockApi();
    render(<ExamPane />);

    await pickCertification();

    expect(await screen.findByLabelText("Networking share")).toHaveValue(34);
    expect(screen.getByLabelText("Security share")).toHaveValue(33);
    expect(screen.getByLabelText("Cloud share")).toHaveValue(33);
    expect(screen.getByText("100% of 100%")).toBeInTheDocument();
  });

  it("says how many questions a share actually means", async () => {
    // A percentage is not something an author can check against the bank; a
    // count is.
    mockApi();
    render(<ExamPane />);

    await pickCertification();
    const row = (await screen.findByText("Cloud")).closest("tr")!;

    // 33% of the default 20 questions.
    expect(within(row).getByText("7 questions")).toBeInTheDocument();
  });

  it("flags a topic that cannot fill its share before anything is checked", async () => {
    mockApi();
    render(<ExamPane />);

    await pickCertification();
    const row = (await screen.findByText("Cloud")).closest("tr")!;

    expect(within(row).getByText("not enough")).toBeInTheDocument();
  });

  it("will not build while the weights do not total 100", async () => {
    mockApi();
    render(<ExamPane />);

    await pickCertification();
    const share = await screen.findByLabelText("Cloud share");
    await userEvent.clear(share);
    await userEvent.type(share, "10");

    expect(screen.getByRole("button", { name: "Check the mix" })).toBeDisabled();
    expect(screen.getByText(/must total 100/)).toBeInTheDocument();
  });

  it("says nothing can be weighted when no topic has questions", async () => {
    mockApi({ topics: [] });
    render(<ExamPane />);

    await pickCertification();

    expect(await screen.findByText(/nothing to weight/)).toBeInTheDocument();
  });
});

describe("checking the mix", () => {
  it("confirms a mix the bank can meet", async () => {
    mockApi();
    render(<ExamPane />);

    await pickCertification();
    await userEvent.click(await screen.findByRole("button", { name: "Check the mix" }));

    expect(await screen.findByText("The mix works")).toBeInTheDocument();
  });

  it("names the topic that falls short and who covers it", async () => {
    // The paper comes back the right length and the wrong mix. The printed
    // cover lists what the paper IS but never what was asked for, so this is
    // the only place the discrepancy itself is stated.
    mockApi({
      plan: plan({
        honoured: false, requested: 20, selected: 20, redistributed: 7,
        topics: [
          outcome({ topic: "Cloud", wanted: 10, available: 3, selected: 3, short: 7 }),
          outcome({ topic: "Networking", wanted: 5, available: 10, selected: 12, lent: 7 }),
        ],
      }),
    });
    render(<ExamPane />);

    await pickCertification();
    await userEvent.click(await screen.findByRole("button", { name: "Check the mix" }));

    // Scoped to the plan: every topic also appears in the weights table
    // above, so an unscoped query matches two rows.
    const report = (await screen.findByText(/would not match the mix/))
      .closest(".plan") as HTMLElement;
    const cloud = within(report).getByText("Cloud").closest("tr")!;
    expect(within(cloud).getByText(/7 short/)).toBeInTheDocument();
    const networking = within(report).getByText("Networking").closest("tr")!;
    expect(within(networking).getByText(/contributing 7 beyond its share/)).toBeInTheDocument();
  });

  it("says when the bank cannot fill the paper at all", async () => {
    mockApi({
      plan: plan({ honoured: false, requested: 40, selected: 23, shortfall: 17 }),
    });
    render(<ExamPane />);

    await pickCertification();
    await userEvent.click(await screen.findByRole("button", { name: "Check the mix" }));

    expect(await screen.findByText(/17 short/)).toBeInTheDocument();
  });

  it("shows the server's refusal rather than inventing one", async () => {
    mockApi({
      plan: {
        status: 409,
        detail: "No questions match that selection, so there is no paper to build.",
      },
    });
    render(<ExamPane />);

    await pickCertification();
    await userEvent.click(await screen.findByRole("button", { name: "Check the mix" }));

    expect(await screen.findByText(/no paper to build/)).toBeInTheDocument();
  });

  it("drops the plan when the request changes under it", async () => {
    // The plan describes one specific request; leaving it on screen after the
    // question count changed makes it a description of something else.
    mockApi();
    render(<ExamPane />);

    await pickCertification();
    await userEvent.click(await screen.findByRole("button", { name: "Check the mix" }));
    await screen.findByText("The mix works");

    const questions = screen.getByLabelText("Questions");
    await userEvent.clear(questions);
    await userEvent.type(questions, "40");

    expect(screen.queryByText("The mix works")).not.toBeInTheDocument();
  });

  it("sends the weighting the author set", async () => {
    const calls = mockApi();
    render(<ExamPane />);

    await pickCertification();
    await userEvent.click(await screen.findByRole("button", { name: "Check the mix" }));

    const planned = calls.find((c) => c.path.includes("/exam/plan"))!;
    expect(planned.body).toMatchObject({
      certification_ids: ["cert-1"],
      topic_weights: { Networking: 34, Security: 33, Cloud: 33 },
    });
  });

  it("sends a seed only when one was given", async () => {
    const calls = mockApi();
    render(<ExamPane />);

    await pickCertification();
    await userEvent.click(await screen.findByRole("button", { name: "Check the mix" }));

    expect((calls.find((c) => c.path.includes("/exam/plan"))!.body as { seed: unknown }).seed)
      .toBeNull();
  });
});
