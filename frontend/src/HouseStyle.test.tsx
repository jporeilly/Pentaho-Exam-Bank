import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { bullets, HouseStyle } from "./HouseStyle";

afterEach(() => vi.unstubAllGlobals());

function serve(body: unknown, status = 200) {
  vi.stubGlobal("fetch", () =>
    Promise.resolve(new Response(JSON.stringify(body), {
      status, headers: { "Content-Type": "application/json" },
    })),
  );
}

describe("the house style", () => {
  it("reads the prompts' bullets, joining each one's wrapped lines", () => {
    const rules = [
      "- **explanation** - why the correct answer is correct, and nothing else. Do NOT",
      "  discuss the wrong options.",
      "- One to three short paragraphs.",
    ].join("\n");
    expect(bullets(rules)).toEqual([
      "**explanation** - why the correct answer is correct, and nothing else. Do NOT discuss the wrong options.",
      "One to three short paragraphs.",
    ]);
  });

  it("shows the server's rules, collapsed until opened, with the bold rendered", async () => {
    serve({
      sections: [
        { title: "Explanation", rules: "- Put the key terms in **bold**.\n- No headings." },
        { title: "Scenario and question", rules: "- Name a real feature." },
      ],
    });
    render(<HouseStyle intro="What every question is written to." />);

    const summary = await screen.findByText(/The house style/);
    const panel = summary.closest("details")!;
    expect(panel.open).toBe(false);
    await userEvent.click(summary);

    expect(panel.open).toBe(true);
    expect(screen.getByRole("heading", { name: "Explanation" })).toBeInTheDocument();
    expect(screen.getByText("No headings.")).toBeInTheDocument();
    expect(screen.getByText("bold").tagName).toBe("STRONG");
    expect(screen.getByText("What every question is written to.")).toBeInTheDocument();
  });

  it("shows nothing when the server has no house style to give", async () => {
    serve({ detail: "Not Found" }, 404);
    const { container } = render(<HouseStyle />);
    await new Promise((r) => setTimeout(r, 20));
    expect(container).toBeEmptyDOMElement();
  });
});
