import { afterEach, describe, expect, it, vi } from "vitest";

import { api, ApiError } from "./api";

function mockFetch(handler: (url: string, init?: RequestInit) => Response | Promise<Response>) {
  const spy = vi.fn(handler);
  vi.stubGlobal("fetch", (url: string, init?: RequestInit) => spy(String(url), init));
  return spy;
}

function json(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

afterEach(() => vi.unstubAllGlobals());

describe("error handling", () => {
  it("surfaces the server's own message", async () => {
    // The API's messages carry the useful part — an unknown course names the
    // ones that exist — so they must not be replaced with something generic.
    mockFetch(() =>
      json({ detail: "No course 'developer-practitioner'. Available: pdi-2hr-lab" }, 404),
    );

    await expect(api.labs("developer-practitioner")).rejects.toThrowError(
      /Available: pdi-2hr-lab/,
    );
  });

  it("carries the status code", async () => {
    mockFetch(() => json({ detail: "still holds 3 questions" }, 428));
    await expect(api.questions()).rejects.toMatchObject({ status: 428 });
  });

  it("says the backend is down when the connection is refused", async () => {
    mockFetch(() => Promise.reject(new TypeError("Failed to fetch")));
    await expect(api.health()).rejects.toThrowError(/Is it running\?/);
  });

  it("falls back to the status line when the error body is not JSON", async () => {
    mockFetch(() => new Response("<html>502</html>", { status: 502, statusText: "Bad Gateway" }));
    await expect(api.health()).rejects.toThrowError(/502/);
  });

  it("is an ApiError, so callers can tell it apart", async () => {
    mockFetch(() => json({ detail: "nope" }, 400));
    await expect(api.health()).rejects.toBeInstanceOf(ApiError);
  });
});

describe("query building", () => {
  it("omits empty filters instead of sending blanks", async () => {
    // `?status=` is not the same request as no status at all, and the one the
    // UI means when a dropdown reads "Any status" is the second.
    const spy = mockFetch(() => json({ items: [], total: 0, limit: 25, offset: 0 }));
    await api.questions({ text: "", status: "", limit: 25, offset: 0 });

    const url = spy.mock.calls[0][0];
    expect(url).not.toContain("text=");
    expect(url).not.toContain("status=");
    expect(url).toContain("limit=25");
    expect(url).toContain("offset=0");
  });

  it("encodes a value that would otherwise break the query", async () => {
    const spy = mockFetch(() => json({ items: [], total: 0, limit: 25, offset: 0 }));
    await api.questions({ text: "a & b = c" });
    expect(spy.mock.calls[0][0]).toContain("text=a+%26+b+%3D+c");
  });

  it("encodes an id in the path", async () => {
    const spy = mockFetch(() => json({}));
    await api.question("m1/q1");
    expect(spy.mock.calls[0][0]).toContain("m1%2Fq1");
  });
});

describe("requests", () => {
  it("sends JSON on a status change", async () => {
    const spy = mockFetch(() => json({}));
    await api.setStatus("m1-q1", "sme_review", "JP", "looks right");

    const [url, init] = spy.mock.calls[0];
    expect(url).toContain("/api/questions/m1-q1/status");
    expect(init?.method).toBe("POST");
    expect(JSON.parse(String(init?.body))).toEqual({
      status: "sme_review",
      sme_name: "JP",
      comment: "looks right",
    });
  });

  it("builds an export URL rather than fetching it", () => {
    // Export is a file download; it has to be a URL the browser navigates to,
    // because fetching it would put the bytes in memory and never save them.
    const url = api.exportUrl("csv", { certification_id: "abc", status: "" });
    expect(url).toBe("/api/export/csv?certification_id=abc");
  });
});
