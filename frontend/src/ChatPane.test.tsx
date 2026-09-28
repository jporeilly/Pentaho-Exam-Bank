/**
 * Content → AI Chat, against a fake backend.
 *
 * Held here: an answer renders with its citations as buttons and its sources
 * grouped by where they came from; an app source opens Documentation at its
 * heading and a Pentaho one opens the browser; "not covered" is shown as that,
 * not as an answer; a failed docs.pentaho.com search is said out loud; the
 * conversation so far goes back with a follow-up; and the source switches can
 * never leave nothing to search.
 */
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ChatPane, historyOf } from "./ChatPane";
import type { ChatAnswer, Settings } from "./api";

function answer(over: Partial<ChatAnswer> = {}): ChatAnswer {
  return {
    answered: true,
    answer: "Use **Publish and push** [A1]. The server listens on 8080 [P1].",
    sources: [
      { id: "A1", kind: "app", title: "Publishing to a Course", heading: "The push", slug: "docs/guides/09-publishing", anchor: "the-push", url: "", snippet: "Publish and push commits…", cited: true },
      { id: "A2", kind: "app", title: "Glossary", heading: "Publish", slug: "docs/reference/01-glossary", anchor: "publish", url: "", snippet: "Write the bank's questions…", cited: false },
      { id: "P1", kind: "pentaho", title: "Ports", heading: "", slug: "", anchor: "", url: "https://docs.pentaho.com/install/ports", snippet: "8080", cited: true },
    ],
    grounding: {
      app: { searched: true, found: 2 },
      pentaho: { searched: true, found: 1, host: "docs.pentaho.com", ms: 640 },
    },
    provider: "ollama",
    model: "gemma4:12b",
    ...over,
  };
}

function mockApi(handlers: {
  chat?: ChatAnswer | { status: number; detail: string } | "hang";
  settings?: Partial<Settings>;
} = {}) {
  const chats: Array<{ messages: Array<{ role: string; content: string }>; appDocs: boolean; pentahoDocs: boolean }> = [];
  const opened: string[] = [];
  vi.stubGlobal("fetch", (url: string, init?: RequestInit) => {
    const path = String(url);
    const json = (body: unknown, status = 200) =>
      Promise.resolve(new Response(status === 204 ? null : JSON.stringify(body), {
        status, headers: { "Content-Type": "application/json" },
      }));
    if (path.includes("/api/chat")) {
      chats.push(JSON.parse(String(init?.body)));
      const r = handlers.chat ?? answer();
      if (r === "hang") {
        return new Promise((_resolve, reject) => {
          init?.signal?.addEventListener("abort", () => reject(new DOMException("aborted", "AbortError")));
        });
      }
      return "status" in r ? json({ detail: r.detail }, r.status) : json(r);
    }
    if (path.includes("/api/open-url")) {
      opened.push(JSON.parse(String(init?.body)).url);
      return json(null, 204);
    }
    if (path.includes("/api/settings")) {
      return json({
        settings: {
          docs_mcp_enabled: true,
          docs_mcp_url: "https://docs.pentaho.com/~gitbook/mcp",
          ...handlers.settings,
        },
      });
    }
    return json({});
  });
  return { chats, opened };
}

beforeEach(() => window.localStorage.clear());
afterEach(() => {
  vi.unstubAllGlobals();
  window.localStorage.clear();
});

async function askIt(text = "How do I publish an exam?") {
  const box = screen.getByRole("textbox", { name: "Your question" });
  await userEvent.type(box, text);
  await userEvent.click(screen.getByRole("button", { name: /^Ask$/ }));
}

describe("an answer", () => {
  it("renders markdown with its citations as buttons", async () => {
    mockApi();
    render(<ChatPane onOpenDoc={() => {}} />);
    await askIt();

    expect(await screen.findByText("Publish and push", { selector: "strong" })).toBeInTheDocument();
    const turn = document.querySelector(".turn.assistant") as HTMLElement;
    const inText = within(turn.querySelector(".md") as HTMLElement);
    expect(inText.getByRole("button", { name: "A1" })).toBeInTheDocument();
    expect(inText.getByRole("button", { name: "P1" })).toBeInTheDocument();
  });

  it("groups its sources by where they came from", async () => {
    mockApi();
    render(<ChatPane onOpenDoc={() => {}} />);
    await askIt();

    expect(await screen.findByText("From this app's documentation")).toBeInTheDocument();
    expect(screen.getByText("From docs.pentaho.com")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /A1 Publishing to a Course › The push/ })).toBeInTheDocument();
  });

  it("shows a source it was given and did not cite as such", async () => {
    mockApi();
    render(<ChatPane onOpenDoc={() => {}} />);
    await askIt();

    const a2 = await screen.findByRole("button", { name: /A2 Glossary › Publish/ });
    expect(a2).toHaveClass("uncited");
    expect(a2.getAttribute("title")).toMatch(/not cited/);
  });

  it("opens an app source in Documentation, at its heading", async () => {
    mockApi();
    const onOpenDoc = vi.fn();
    render(<ChatPane onOpenDoc={onOpenDoc} />);
    await askIt();

    await userEvent.click(await screen.findByRole("button", { name: /A1 Publishing to a Course/ }));
    expect(onOpenDoc).toHaveBeenCalledWith("docs/guides/09-publishing", "the-push");
  });

  it("opens a citation in the text the same way", async () => {
    mockApi();
    const onOpenDoc = vi.fn();
    render(<ChatPane onOpenDoc={onOpenDoc} />);
    await askIt();

    const turn = await screen.findByText("Publish and push", { selector: "strong" });
    await userEvent.click(within(turn.closest(".md") as HTMLElement).getByRole("button", { name: "A1" }));
    expect(onOpenDoc).toHaveBeenCalledWith("docs/guides/09-publishing", "the-push");
  });

  it("opens a Pentaho source in the browser, through the backend", async () => {
    const { opened } = mockApi();
    render(<ChatPane onOpenDoc={() => {}} />);
    await askIt();

    await userEvent.click(await screen.findByRole("button", { name: /P1 Ports/ }));
    expect(opened).toEqual(["https://docs.pentaho.com/install/ports"]);
  });

  it("names the model that answered", async () => {
    mockApi();
    render(<ChatPane onOpenDoc={() => {}} />);
    await askIt();

    expect(await screen.findByText("Answered by gemma4:12b via ollama")).toBeInTheDocument();
  });
});

describe("when there is no answer", () => {
  it("says not covered rather than showing a guess", async () => {
    mockApi({
      chat: answer({ answered: false, answer: "Neither this app's documentation nor docs.pentaho.com has anything on that.", sources: [] }),
    });
    render(<ChatPane onOpenDoc={() => {}} />);
    await askIt("kubernetes helm chart");

    expect(await screen.findByText("Not covered.")).toBeInTheDocument();
    expect(screen.queryByText(/Answered by/)).not.toBeInTheDocument();
  });

  it("says when docs.pentaho.com could not be searched", async () => {
    mockApi({
      chat: answer({
        sources: answer().sources.filter((s) => s.kind === "app"),
        grounding: { app: { searched: true, found: 2 }, pentaho: { searched: true, found: 0, host: "docs.pentaho.com", error: "No answer within 15 seconds." } },
      }),
    });
    render(<ChatPane onOpenDoc={() => {}} />);
    await askIt();

    expect(await screen.findByText(/docs\.pentaho\.com could not be searched: No answer within 15 seconds\./)).toBeInTheDocument();
    expect(screen.getByText(/from this app's documentation only/)).toBeInTheDocument();
  });

  it("shows the backend's reason when the model fails", async () => {
    mockApi({ chat: { status: 503, detail: "No Ollama model is configured." } });
    render(<ChatPane onOpenDoc={() => {}} />);
    await askIt();

    expect(await screen.findByRole("alert")).toHaveTextContent("No Ollama model is configured.");
  });

  it("stops a question on request", async () => {
    mockApi({ chat: "hang" });
    render(<ChatPane onOpenDoc={() => {}} />);
    await askIt();

    await userEvent.click(await screen.findByRole("button", { name: /Stop/ }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Stopped.");
  });
});

describe("the conversation", () => {
  it("sends the conversation so far with a follow-up", async () => {
    const { chats } = mockApi();
    render(<ChatPane onOpenDoc={() => {}} />);
    await askIt("How do I publish an exam?");
    await screen.findByText(/Answered by/);
    await askIt("and the push?");

    await screen.findAllByText(/Answered by/);
    expect(chats[1].messages.map((m) => m.role)).toEqual(["user", "assistant", "user"]);
    expect(chats[1].messages[2].content).toBe("and the push?");
  });

  it("does not send a not-covered reply back as an answer", () => {
    const history = historyOf([
      { role: "user", content: "q1" },
      { role: "assistant", content: "Not covered", answer: answer({ answered: false }) },
      { role: "error", content: "boom" },
      { role: "user", content: "q2" },
    ]);
    expect(history).toEqual([
      { role: "user", content: "q1" },
      { role: "user", content: "q2" },
    ]);
  });

  it("is kept across a remount until New conversation", async () => {
    mockApi();
    const { unmount } = render(<ChatPane onOpenDoc={() => {}} />);
    await askIt("How do I publish an exam?");
    await screen.findByText(/Answered by/);
    unmount();

    render(<ChatPane onOpenDoc={() => {}} />);
    expect(screen.getByText("How do I publish an exam?")).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: /New conversation/ }));
    expect(screen.queryByText("How do I publish an exam?")).not.toBeInTheDocument();
  });

  it("starts from a suggested question", async () => {
    const { chats } = mockApi();
    render(<ChatPane onOpenDoc={() => {}} />);

    await userEvent.click(screen.getByRole("button", { name: "Which ports does Pentaho Server use?" }));
    await screen.findByText(/Answered by/);
    expect(chats[0].messages[0].content).toBe("Which ports does Pentaho Server use?");
  });
});

describe("the source switches", () => {
  it("sends which sources to search", async () => {
    const { chats } = mockApi();
    render(<ChatPane onOpenDoc={() => {}} />);
    await userEvent.click(screen.getByRole("checkbox", { name: "docs.pentaho.com" }));
    await askIt();

    await screen.findByText(/Answered by/);
    expect(chats[0]).toMatchObject({ appDocs: true, pentahoDocs: false });
  });

  it("never lets the last source be switched off", async () => {
    mockApi();
    render(<ChatPane onOpenDoc={() => {}} />);
    await userEvent.click(screen.getByRole("checkbox", { name: "docs.pentaho.com" }));

    expect(screen.getByRole("checkbox", { name: "This app's docs" })).toBeDisabled();
  });

  it("cannot turn on docs.pentaho.com while Settings has it off", async () => {
    const { chats } = mockApi({ settings: { docs_mcp_enabled: false } });
    render(<ChatPane onOpenDoc={() => {}} />);

    expect(await screen.findByText("off in Settings")).toBeInTheDocument();
    const box = screen.getByRole("checkbox", { name: "docs.pentaho.com" });
    expect(box).toBeDisabled();
    expect(box).not.toBeChecked();

    await askIt();
    await screen.findByText(/Answered by/);
    expect(chats[0].pentahoDocs).toBe(false);
  });
});
