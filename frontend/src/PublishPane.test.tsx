import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { PublishPane } from "./PublishPane";
import type { PublishPlan } from "./api";

const COURSES = [
  { slug: "demo-course", title: "Demo Course", hasExam: true, questionCount: 2 },
  { slug: "no-exam", title: "Course Without An Exam", hasExam: false, questionCount: 0 },
];

const CERTS = [
  {
    id: "cert-1", name: "Demo Practitioner", description: "",
    sourceType: "pcm", sourceRef: "demo-course", questionCount: 12,
  },
  {
    id: "cert-2", name: "Unrelated", description: "",
    sourceType: "pptx", sourceRef: "", questionCount: 4,
  },
];

function plan(over: Partial<PublishPlan> = {}): PublishPlan {
  return {
    courseId: "demo-course",
    path: "C:/Projects/Pentaho-Content-Manager/courses/demo-course/exam.json",
    sourceSha: "abc123",
    isNoop: false,
    beforeCount: 2,
    afterCount: 3,
    added: [],
    removed: [],
    changed: [],
    unchanged: 2,
    reordered: false,
    preservedKeys: ["title", "passMark", "webhookSecret", "intake"],
    descriptionBefore: "",
    descriptionAfter: "",
    ...over,
  };
}

/** Records every request, so a test can assert what was NOT sent. */
function mockApi(handlers: {
  plan?: PublishPlan | { status: number; detail: string };
  publish?: PublishPlan | { status: number; detail: string };
}) {
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

    if (path.endsWith("/plan")) {
      const r = handlers.plan ?? plan();
      return "status" in r ? json({ detail: r.detail }, r.status) : json(r);
    }
    if (path.includes("/exam/questions")) {
      const r = handlers.publish ?? { ...plan(), written: true };
      return "status" in r ? json({ detail: r.detail }, r.status) : json(r);
    }
    if (path.includes("/certifications")) return json(CERTS);
    return json(COURSES);
  });
  return calls;
}

async function choose(label: string, option: string) {
  await userEvent.selectOptions(await screen.findByLabelText(label), option);
}

async function check() {
  await userEvent.click(
    await screen.findByRole("button", { name: "Check what would change" }),
  );
}

afterEach(() => vi.unstubAllGlobals());

describe("choosing what to publish", () => {
  it("preselects the certification the course was adopted from", async () => {
    // The server refuses a mismatched pair, and meeting that refusal for a
    // choice nobody made is a bad first experience of a destructive action.
    mockApi({});
    render(<PublishPane />);

    await choose("Course", "demo-course");

    expect(await screen.findByLabelText("Questions from")).toHaveValue("cert-1");
  });

  it("replaces a certification left behind by a course change", async () => {
    // Found by driving the real app: changing the course kept the previous
    // certification, and the next click met the server's mismatch refusal
    // for a pairing the author never chose.
    mockApi({});
    render(<PublishPane />);

    await choose("Course", "demo-course");
    expect(await screen.findByLabelText("Questions from")).toHaveValue("cert-1");

    await choose("Course", "no-exam");

    expect(await screen.findByLabelText("Questions from")).toHaveValue("");
  });

  it("leaves a certification that belongs to no course alone", async () => {
    // sourceRef "" means it was never adopted from a course, so publishing it
    // into one is a deliberate choice rather than a stale selection.
    mockApi({});
    render(<PublishPane />);

    await choose("Questions from", "cert-2");
    await choose("Course", "demo-course");

    expect(await screen.findByLabelText("Questions from")).toHaveValue("cert-2");
  });

  it("says why a course with no exam.json cannot be published into", async () => {
    mockApi({});
    render(<PublishPane />);

    await choose("Course", "no-exam");

    expect(await screen.findByText(/does not create one/)).toBeInTheDocument();
  });

  it("will not check anything until both are chosen", async () => {
    mockApi({});
    render(<PublishPane />);

    expect(
      await screen.findByRole("button", { name: "Check what would change" }),
    ).toBeDisabled();
  });
});

describe("the plan", () => {
  it("writes nothing when it is only checked", async () => {
    const calls = mockApi({});
    render(<PublishPane />);

    await choose("Course", "demo-course");
    await check();
    await screen.findByText(/What would change/);

    expect(calls.filter((c) => c.path.endsWith("/plan"))).toHaveLength(1);
    expect(calls.some((c) => c.path.match(/exam\/questions$/))).toBe(false);
  });

  it("names the questions that would be added and removed", async () => {
    mockApi({ plan: plan({ added: ["q-new"], removed: ["q-old"], unchanged: 2 }) });
    render(<PublishPane />);

    await choose("Course", "demo-course");
    await check();

    expect(await screen.findByText("q-new")).toBeInTheDocument();
    expect(screen.getByText("q-old")).toBeInTheDocument();
  });

  it("says what a removal costs, because the sheet keeps the old results", async () => {
    mockApi({ plan: plan({ removed: ["q-old"] }) });
    render(<PublishPane />);

    await choose("Course", "demo-course");
    await check();

    expect(
      await screen.findByText(/Results already recorded against it/),
    ).toBeInTheDocument();
  });

  it("lists which fields changed on an edited question", async () => {
    mockApi({
      plan: plan({ changed: [{ id: "m1-q0", fields: ["prompt", "options"] }] }),
    });
    render(<PublishPane />);

    await choose("Course", "demo-course");
    await check();

    const item = (await screen.findByText("m1-q0")).closest("li")!;
    expect(within(item).getByText("prompt, options")).toBeInTheDocument();
  });

  it("shows the keys the merge left alone", async () => {
    // The whole point of the merge. An author needs to see that `intake` and
    // the webhook survived, which is a different claim from "it worked".
    mockApi({});
    render(<PublishPane />);

    await choose("Course", "demo-course");
    await check();

    const preserved = await screen.findByText(/Left untouched/);
    expect(within(preserved).getByText("intake")).toBeInTheDocument();
    expect(within(preserved).getByText("webhookSecret")).toBeInTheDocument();
  });

  it("offers nothing to press when the course already matches", async () => {
    mockApi({ plan: plan({ isNoop: true, afterCount: 2, beforeCount: 2 }) });
    render(<PublishPane />);

    await choose("Course", "demo-course");
    await check();

    expect(await screen.findByText(/Nothing to publish/)).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Publish to the course" }),
    ).not.toBeInTheDocument();
  });

  it("shows the description sentence before and after, not just that it changed", async () => {
    // The one piece of authored prose a publish touches. "The description
    // will be updated" is not something an author can agree or disagree with.
    mockApi({
      plan: plan({
        descriptionBefore: "Drawn from a pool of 36. Pass mark is 80%.",
        descriptionAfter: "Drawn from a pool of 46. Pass mark is 80%.",
      }),
    });
    render(<PublishPane />);

    await choose("Course", "demo-course");
    await check();

    expect(
      await screen.findByText("Drawn from a pool of 36. Pass mark is 80%."),
    ).toBeInTheDocument();
    expect(
      screen.getByText("Drawn from a pool of 46. Pass mark is 80%."),
    ).toBeInTheDocument();
    expect(screen.getByText(/build check fails/)).toBeInTheDocument();
  });

  it("says nothing about the description when it already agrees", async () => {
    mockApi({});
    render(<PublishPane />);

    await choose("Course", "demo-course");
    await check();
    await screen.findByText(/What would change/);

    expect(screen.queryByText(/build check fails/)).not.toBeInTheDocument();
  });

  it("flags a reorder, which is not visible in any per-question diff", async () => {
    mockApi({ plan: plan({ reordered: true, unchanged: 3 }) });
    render(<PublishPane />);

    await choose("Course", "demo-course");
    await check();

    expect(await screen.findByText(/order a learner sees/)).toBeInTheDocument();
  });
});

describe("publishing", () => {
  it("sends back the hash the plan was made against", async () => {
    const calls = mockApi({ plan: plan({ sourceSha: "sha-from-the-plan" }) });
    render(<PublishPane />);

    await choose("Course", "demo-course");
    await check();
    await userEvent.click(
      await screen.findByRole("button", { name: "Publish to the course" }),
    );

    const write = calls.find((c) => c.path.match(/exam\/questions$/))!;
    expect(write.body).toMatchObject({
      certification_id: "cert-1",
      expect_sha: "sha-from-the-plan",
    });
  });

  it("says the authoring copy changed, not what a learner runs", async () => {
    mockApi({});
    render(<PublishPane />);

    await choose("Course", "demo-course");
    await check();
    await userEvent.click(
      await screen.findByRole("button", { name: "Publish to the course" }),
    );

    expect(await screen.findByText("Published")).toBeInTheDocument();
    expect(screen.getByText(/nothing a learner runs has changed until it is pushed/)).toBeInTheDocument();
  });

  it("drops the plan when the file changed underneath it", async () => {
    // The Content Editor writes this same file in whole. A plan left on
    // screen after that refusal describes a file that no longer exists.
    mockApi({
      publish: {
        status: 409,
        detail: "The course's exam.json changed after this plan was made.",
      },
    });
    render(<PublishPane />);

    await choose("Course", "demo-course");
    await check();
    await userEvent.click(
      await screen.findByRole("button", { name: "Publish to the course" }),
    );

    expect(await screen.findByText(/changed after this plan was made/)).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Publish to the course" }),
    ).not.toBeInTheDocument();
  });

  it("shows the server's refusal rather than inventing one", async () => {
    mockApi({
      plan: {
        status: 409,
        detail: "demo-course/exam.json carries configuration that moved out of exam.json: intake.contact.",
      },
    });
    render(<PublishPane />);

    await choose("Course", "demo-course");
    await check();

    expect(await screen.findByText(/intake\.contact/)).toBeInTheDocument();
  });

  it("invalidates a plan when the selection changes under it", async () => {
    // The hash authorises a write of a specific question set. Leaving the
    // plan on screen after the status changed would let it authorise a
    // different one.
    mockApi({});
    render(<PublishPane />);

    await choose("Course", "demo-course");
    await check();
    await screen.findByText(/What would change/);

    await choose("Status", "draft");

    expect(screen.queryByText(/What would change/)).not.toBeInTheDocument();
  });
});

describe("pushing to the courses repo", () => {
  const PUSHABLE = {
    available: true, versionFrom: "0.1.11", versionTo: "0.1.12",
    coursesRepo: "https://github.com/jporeilly/Pentaho-Courses.git",
  };

  it("offers the push, ticked, with the version it will publish", async () => {
    mockApi({ plan: plan({ push: PUSHABLE }) });
    render(<PublishPane />);
    await choose("Course", "demo-course");
    await check();
    expect(await screen.findByRole("checkbox", { name: "Also push to the courses repo" })).toBeChecked();
    expect(screen.getByText("0.1.11")).toBeInTheDocument();
    expect(screen.getByText("0.1.12")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Publish and push" })).toBeInTheDocument();
  });

  it("asks the server to push when it is ticked", async () => {
    const calls = mockApi({ plan: plan({ push: PUSHABLE }) });
    render(<PublishPane />);
    await choose("Course", "demo-course");
    await check();
    await userEvent.click(await screen.findByRole("button", { name: "Publish and push" }));
    const write = calls.find((c) => c.path.match(/exam\/questions$/))!;
    expect(write.body).toMatchObject({ push: true, expect_sha: "abc123" });
  });

  it("publishes without pushing when it is unticked", async () => {
    const calls = mockApi({ plan: plan({ push: PUSHABLE }) });
    render(<PublishPane />);
    await choose("Course", "demo-course");
    await check();
    await userEvent.click(await screen.findByRole("checkbox", { name: "Also push to the courses repo" }));
    await userEvent.click(screen.getByRole("button", { name: "Publish to the course" }));
    const write = calls.find((c) => c.path.match(/exam\/questions$/))!;
    expect(write.body).toMatchObject({ push: false });
  });

  it("says why a push is not possible, and cannot be ticked", async () => {
    const calls = mockApi({
      plan: plan({ push: { available: false, reason: "The Content Manager repository is 2 commit(s) behind its remote." } }),
    });
    render(<PublishPane />);
    await choose("Course", "demo-course");
    await check();
    const box = await screen.findByRole("checkbox", { name: "Also push to the courses repo" });
    expect(box).toBeDisabled();
    expect(box).not.toBeChecked();
    expect(screen.getByText(/2 commit\(s\) behind its remote/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Publish to the course" }));
    const write = calls.find((c) => c.path.match(/exam\/questions$/))!;
    expect(write.body).toMatchObject({ push: false });
  });

  it("reports both commits and the version once it has pushed", async () => {
    mockApi({
      plan: plan({ push: PUSHABLE }),
      publish: {
        ...plan(), written: true,
        push: {
          versionFrom: "0.1.11", versionTo: "0.1.12", coursesRepo: PUSHABLE.coursesRepo,
          authoring: { commit: "aaaaaaa1111", pushed: true },
          courses: { commit: "bbbbbbb2222", pushed: true },
        },
      } as unknown as PublishPlan,
    });
    render(<PublishPane />);
    await choose("Course", "demo-course");
    await check();
    await userEvent.click(await screen.findByRole("button", { name: "Publish and push" }));
    expect(await screen.findByText("Published and pushed")).toBeInTheDocument();
    expect(screen.getByText("bbbbbbb")).toBeInTheDocument();
    expect(screen.getByText("aaaaaaa")).toBeInTheDocument();
  });

  it("says plainly when the file is written but the push stopped", async () => {
    mockApi({
      plan: plan({ push: PUSHABLE }),
      publish: {
        ...plan(), written: true,
        push: { error: "git push failed: rejected", failedAt: "courses",
                authoring: { commit: "aaaaaaa1111", pushed: true } },
      } as unknown as PublishPlan,
    });
    render(<PublishPane />);
    await choose("Course", "demo-course");
    await check();
    await userEvent.click(await screen.findByRole("button", { name: "Publish and push" }));
    expect(await screen.findByText(/the push stopped at the courses stage/)).toBeInTheDocument();
    expect(screen.getByText(/only the courses repo is behind/)).toBeInTheDocument();
  });
});
