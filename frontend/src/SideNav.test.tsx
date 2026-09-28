/**
 * The navigation rail.
 *
 * Written after a peer session pointed out that the release carrying the
 * rail added no frontend test at all, and that its CHANGELOG entry makes
 * four falsifiable claims. It was rendered and walked by hand, which proves
 * it worked once and nothing about tomorrow.
 *
 * The claim worth a test above the others is that the group HEADINGS stay in
 * the DOM when the rail is collapsed. That is an accessibility claim written
 * into a public changelog, it is a one-line regression for a sighted
 * developer to make, and nothing on screen would look wrong afterwards.
 *
 * NOT tested here, and said plainly rather than implied: the 860px
 * auto-collapse is a CSS media query (`styles.css:192`) with no JavaScript
 * behind it, so jsdom cannot exercise it. It was checked by resizing a real
 * browser to 768px and reading the computed width back.
 */
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { SideNav, type Tab } from "./SideNav";

const HEADINGS = ["Content", "Questions", "System"];
const ITEMS = [
  "Courses", "Generate", "Import", "AI Chat",
  "Bank", "Report", "Exam paper", "Publish",
  "Settings", "Admin", "Documentation",
];

beforeEach(() => window.localStorage.clear());
afterEach(() => {
  window.localStorage.clear();
  vi.restoreAllMocks();
});

function mount(tab: Tab = "courses", questions?: number) {
  const onSelect = vi.fn();
  render(<SideNav tab={tab} onSelect={onSelect} questions={questions} />);
  return onSelect;
}

const rail = () => document.querySelector(".rail")!;
const headingText = () =>
  [...document.querySelectorAll(".rail__heading")].map((el) => el.textContent);

describe("the rail", () => {
  it("shows every destination, grouped", () => {
    mount();
    for (const label of ITEMS) {
      expect(screen.getByRole("button", { name: label })).toBeTruthy();
    }
    expect(headingText()).toEqual(HEADINGS);
  });

  it("marks the current destination and only that one", () => {
    mount("bank");
    const current = document.querySelectorAll('.rail__item[aria-current="page"]');
    expect(current.length).toBe(1);
    expect(current[0].textContent).toContain("Bank");
  });

  it("reports a selection", async () => {
    const onSelect = mount();
    await userEvent.click(screen.getByRole("button", { name: "Publish" }));
    expect(onSelect).toHaveBeenCalledWith("publish");
  });
});

describe("the count beside Bank", () => {
  it("is shown", () => {
    mount("courses", 413);
    expect(document.querySelector(".rail__count")?.textContent).toBe("413");
  });

  it("is NOT part of the button's accessible name", () => {
    // It sits inside the button, so without aria-hidden it joins the name:
    // the button announced itself as "Bank 413" and renamed itself every
    // time the bank grew. launch.test.tsx caught this once; this pins it.
    mount("courses", 413);
    expect(screen.getByRole("button", { name: "Bank" })).toBeTruthy();
    expect(screen.queryByRole("button", { name: /Bank 413/ })).toBeNull();
  });

  it("is absent when there is no count to show", () => {
    mount();
    expect(document.querySelector(".rail__count")).toBeNull();
  });
});

describe("collapsing", () => {
  it("collapses and expands", async () => {
    mount();
    expect(rail().className).not.toContain("is-collapsed");

    await userEvent.click(screen.getByTitle("Collapse the navigation"));
    expect(rail().className).toContain("is-collapsed");

    await userEvent.click(screen.getByTitle("Expand the navigation"));
    expect(rail().className).not.toContain("is-collapsed");
  });

  it("remembers that it was collapsed", async () => {
    mount();
    await userEvent.click(screen.getByTitle("Collapse the navigation"));
    expect(window.localStorage.getItem("peb-nav-collapsed")).toBe("1");
  });

  it("starts collapsed when it was left collapsed", () => {
    window.localStorage.setItem("peb-nav-collapsed", "1");
    mount();
    expect(rail().className).toContain("is-collapsed");
  });

  it("KEEPS THE GROUP HEADINGS IN THE DOM when collapsed", async () => {
    // The claim in the changelog, and the one that would rot silently: the
    // grouping is the point of the rail, and dropping the headings when the
    // labels go would take it away from a screen reader while looking
    // perfectly fine on screen.
    mount();
    await userEvent.click(screen.getByTitle("Collapse the navigation"));

    expect(rail().className).toContain("is-collapsed");
    expect(headingText()).toEqual(HEADINGS);
  });

  it("gives every item a title when collapsed, so the label is still reachable", async () => {
    mount();
    await userEvent.click(screen.getByTitle("Collapse the navigation"));
    for (const label of ITEMS) {
      expect(screen.getByTitle(label)).toBeTruthy();
    }
  });
});

describe("when localStorage is unavailable", () => {
  // It throws in a private window and after cleared site data. A nav that
  // will not render is a far worse outcome than one that forgot a preference.
  it("still renders when reading throws", () => {
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new Error("denied");
    });
    mount();
    expect(headingText()).toEqual(HEADINGS);
    expect(rail().className).not.toContain("is-collapsed");
  });

  it("still collapses when writing throws", async () => {
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new Error("denied");
    });
    mount();
    await userEvent.click(screen.getByTitle("Collapse the navigation"));
    expect(rail().className).toContain("is-collapsed");
  });
});

describe("AI Chat and Documentation", () => {
  it("puts AI Chat under Content and Documentation under System", async () => {
    const { navGroups } = await import("./SideNav");
    const groups = Object.fromEntries(navGroups().map((g) => [g.heading, g.items.map((i) => i.label)]));

    expect(groups.Content).toContain("AI Chat");
    expect(groups.System).toContain("Documentation");
    expect(Object.values(groups).flat()).not.toContain("AI & Docs");
  });

  it("opens each with its own tab", async () => {
    const onSelect = mount();
    await userEvent.click(screen.getByRole("button", { name: /AI Chat/ }));
    await userEvent.click(screen.getByRole("button", { name: /Documentation/ }));

    expect(onSelect.mock.calls.map((c) => c[0])).toEqual(["chat", "docs"]);
  });
});
