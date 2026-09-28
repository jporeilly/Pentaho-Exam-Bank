import { describe, expect, it } from "vitest";

import { linkCitations, minutesToRead, resolveDocLink } from "./docLinks";

const PAGES = new Set([
  "README.md",
  "INSTALL.md",
  "HOW_TO_GUIDE.md",
  "docs/guides/05-the-bank.md",
  "docs/guides/06-review.md",
  "docs/writing/01-how-a-question-is-written.md",
]);

describe("resolveDocLink", () => {
  const here = "docs/guides/05-the-bank.md";

  it("resolves a sibling page", () => {
    expect(resolveDocLink("06-review.md", here, PAGES)).toEqual({
      kind: "doc", slug: "docs/guides/06-review", anchor: "",
    });
  });

  it("resolves ../ into another folder, with its anchor", () => {
    expect(resolveDocLink("../writing/01-how-a-question-is-written.md#the-scenario", here, PAGES)).toEqual({
      kind: "doc", slug: "docs/writing/01-how-a-question-is-written", anchor: "the-scenario",
    });
  });

  it("resolves a root document from deep inside docs/", () => {
    expect(resolveDocLink("../../INSTALL.md#what-it-connects-to", here, PAGES)).toEqual({
      kind: "doc", slug: "INSTALL", anchor: "what-it-connects-to",
    });
  });

  it("resolves a docs page from a root document", () => {
    expect(resolveDocLink("docs/guides/06-review.md", "HOW_TO_GUIDE.md", PAGES)).toEqual({
      kind: "doc", slug: "docs/guides/06-review", anchor: "",
    });
  });

  it("keeps an anchor on this page as an anchor", () => {
    expect(resolveDocLink("#saving-a-question", here, PAGES)).toEqual({
      kind: "anchor", anchor: "saving-a-question",
    });
  });

  it("sends anything with a scheme outside", () => {
    expect(resolveDocLink("https://ollama.com", here, PAGES)).toEqual({ kind: "external", url: "https://ollama.com" });
    expect(resolveDocLink("mailto:a@b.c", here, PAGES)).toEqual({ kind: "external", url: "mailto:a@b.c" });
  });

  it("treats a repo file that is not a page as nothing to open", () => {
    expect(resolveDocLink("../../LICENSE", here, PAGES)).toEqual({ kind: "none" });
    expect(resolveDocLink("docs/", "HOW_TO_GUIDE.md", PAGES)).toEqual({ kind: "none" });
    expect(resolveDocLink("nope.md", here, PAGES)).toEqual({ kind: "none" });
  });
});

describe("linkCitations", () => {
  it("turns each marker into a link the renderer makes a button", () => {
    expect(linkCitations("Publish it [A1]. It listens on 8080 [P2].")).toBe(
      "Publish it [A1](#cite-A1). It listens on 8080 [P2](#cite-P2).",
    );
  });

  it("splits a group of markers", () => {
    expect(linkCitations("Both [A1, P3].")).toBe("Both [A1](#cite-A1) [P3](#cite-P3).");
  });

  it("leaves code, real links and other brackets alone", () => {
    const text = "Use `[A1]` and [the guide](x.md) and [1] and [note].";
    expect(linkCitations(text)).toBe(text);
  });
});

it("never says zero minutes", () => {
  expect(minutesToRead(20)).toBe(1);
  expect(minutesToRead(1000)).toBe(5);
});
