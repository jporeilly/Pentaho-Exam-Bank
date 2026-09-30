import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { FALLBACK, resetVocabulary, statusLabel, useVocabulary } from "./vocabulary";

function Show() {
  const v = useVocabulary();
  return (
    <ul>
      {v.statuses.map((s) => (
        <li key={s}>{statusLabel(v, s)}</li>
      ))}
    </ul>
  );
}

function serve(body: unknown, status = 200) {
  const calls: string[] = [];
  vi.stubGlobal("fetch", (url: string) => {
    calls.push(String(url));
    return Promise.resolve(
      new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } }),
    );
  });
  return calls;
}

afterEach(() => {
  vi.unstubAllGlobals();
  resetVocabulary();
});

describe("useVocabulary", () => {
  it("shows the server's lists once they arrive", async () => {
    const calls = serve({ ...FALLBACK, statuses: [...FALLBACK.statuses, "archived"],
                          statusLabels: { archived: "Archived" } });
    render(<Show />);

    expect(await screen.findByText("Archived")).toBeInTheDocument();
    expect(screen.getByText("SME Review")).toBeInTheDocument();
    expect(calls.some((c) => c.endsWith("/api/vocabulary"))).toBe(true);
  });

  it("keeps the fallback when the server cannot answer, and asks again next time", async () => {
    const calls = serve({ detail: "boom" }, 500);
    const first = render(<Show />);
    await waitFor(() => expect(calls).toHaveLength(1));
    expect(screen.getByText("Retired")).toBeInTheDocument();
    first.unmount();

    render(<Show />);
    await waitFor(() => expect(calls).toHaveLength(2));
  });
});
