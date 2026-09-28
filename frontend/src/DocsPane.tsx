/**
 * System → Documentation: the app's guide, page by page.
 *
 * Laid out the way OpenSight's documentation is, because it works: a sidebar
 * of sections that doubles as search, the page with a breadcrumb and a reading
 * time, an "On this page" list that follows the scroll, and previous/next
 * links through the whole set. The pages are the files under `docs/` plus the
 * root documents; the backend lists them, so adding a page is adding a file.
 *
 * AI Chat opens a page here at a heading — that is what its A1, A2 sources
 * do — through `target`, which carries a sequence number so opening the same
 * source twice still scrolls to it.
 */
import { useEffect, useMemo, useRef, useState } from "react";
import { ArrowLeft, ArrowRight, ChevronDown, ChevronRight, Search, X } from "lucide-react";

import {
  api,
  ApiError,
  type DocIndex,
  type DocItem,
  type DocPage,
  type DocSearchResult,
} from "./api";
import { DocMarkdown, scrollToAnchor } from "./DocMarkdown";
import { minutesToRead } from "./docLinks";

/** A request, from elsewhere in the app, to show a page at a heading. */
export interface DocTarget {
  slug: string;
  anchor: string;
  seq: number;
}

const PAGE_KEY = "peb-docs-page";
const COLLAPSED_KEY = "peb-docs-collapsed";
/** Where the guide starts when nothing else was asked for: the hub. */
const HOME = "HOW_TO_GUIDE";

// Wrapped: storage throws in a private window and comes back empty after
// cleared site data. Forgetting the last page is fine; failing to render is not.
function load(key: string): string {
  try {
    return window.localStorage.getItem(key) ?? "";
  } catch {
    return "";
  }
}
function save(key: string, value: string) {
  try {
    window.localStorage.setItem(key, value);
  } catch {
    /* not worth telling anyone about */
  }
}

function message(e: unknown): string {
  return e instanceof ApiError ? e.message : String(e);
}

/** A section's text as a snippet: the markdown marks removed. */
function plain(markdown: string): string {
  return markdown
    .replace(/\[([^\]]*)\]\([^)]*\)/g, "$1")
    .replace(/[*_`>#|]/g, "")
    .replace(/\s+/g, " ")
    .trim();
}

function Highlight({ text, query }: { text: string; query: string }) {
  const terms = query
    .toLowerCase()
    .split(/[^a-z0-9]+/)
    .filter((t) => t.length > 2)
    .map((t) => t.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"));
  if (!terms.length) return <>{text}</>;
  const parts = text.split(new RegExp(`(${terms.join("|")})`, "gi"));
  return (
    <>
      {parts.map((p, i) => (i % 2 === 1 ? <mark key={i}>{p}</mark> : p))}
    </>
  );
}

export function DocsPane({
  target,
  onTargetDone,
}: {
  target?: DocTarget | null;
  onTargetDone?: () => void;
}) {
  const [index, setIndex] = useState<DocIndex | null>(null);
  const [error, setError] = useState("");
  const [slug, setSlug] = useState(() => load(PAGE_KEY));
  const [page, setPage] = useState<DocPage | null>(null);
  const [pageError, setPageError] = useState("");
  const [query, setQuery] = useState("");
  const [hits, setHits] = useState<DocSearchResult | null>(null);
  const [collapsed, setCollapsed] = useState<string[]>(() => {
    try {
      return JSON.parse(load(COLLAPSED_KEY) || "[]");
    } catch {
      return [];
    }
  });
  const [active, setActive] = useState("");
  const pending = useRef("");
  const articleRef = useRef<HTMLElement>(null);

  useEffect(() => {
    api.docsIndex().then(setIndex).catch((e) => setError(message(e)));
  }, []);

  const items: DocItem[] = useMemo(() => index?.sections.flatMap((s) => s.items) ?? [], [index]);
  const pagePaths = useMemo(() => new Set(items.map((i) => i.path)), [items]);

  // Start on the remembered page if it still exists, else on the guide's hub.
  useEffect(() => {
    if (!index || items.some((i) => i.slug === slug)) return;
    setSlug(items.find((i) => i.slug === HOME)?.slug ?? items[0]?.slug ?? "");
  }, [index, items, slug]);

  useEffect(() => {
    if (!slug) return;
    save(PAGE_KEY, slug);
    let live = true;
    setPageError("");
    api
      .docsPage(slug)
      .then((p) => live && setPage(p))
      .catch((e) => live && setPageError(message(e)));
    return () => {
      live = false;
    };
  }, [slug]);

  const scroller = () => (articleRef.current?.closest("main") as HTMLElement | null) ?? null;

  // Once a page has rendered: to the heading that was asked for, or the top.
  useEffect(() => {
    if (!page) return;
    const anchor = pending.current;
    pending.current = "";
    requestAnimationFrame(() => {
      if (!scrollToAnchor(anchor)) scroller()?.scrollTo({ top: 0 });
    });
  }, [page]);

  function open(to: string, anchor = "") {
    if (to === page?.slug) {
      if (!scrollToAnchor(anchor)) scroller()?.scrollTo({ top: 0 });
      return;
    }
    pending.current = anchor;
    setSlug(to);
  }

  // A page asked for from elsewhere (an AI Chat source). Handed back as done,
  // so the request is used once: left standing, it would reopen that page
  // every time this screen is shown, over whatever the author read since.
  useEffect(() => {
    if (!target) return;
    open(target.slug, target.anchor);
    onTargetDone?.();
    // `open` reads the page at the time; only a new request should run this.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [target?.seq]);

  // Search as you type, debounced; two characters before it starts.
  useEffect(() => {
    const q = query.trim();
    if (q.length < 2) {
      setHits(null);
      return;
    }
    const timer = window.setTimeout(() => {
      api.searchDocs(q).then(setHits).catch((e) => setError(message(e)));
    }, 200);
    return () => window.clearTimeout(timer);
  }, [query]);

  // A long page (the changelog) lists only its top level, or the list would
  // be longer than the page it is meant to navigate.
  const toc = useMemo(() => {
    const all = page?.headings ?? [];
    return all.length > 30 ? all.filter((h) => h.level <= 2) : all;
  }, [page]);

  // "On this page" follows the scroll: the last heading above the top edge.
  useEffect(() => {
    const el = scroller();
    if (!el || toc.length < 2) return;
    const onScroll = () => {
      const edge = el.getBoundingClientRect().top + 90;
      let current = toc[0]?.id ?? "";
      for (const h of toc) {
        const node = document.getElementById(h.id);
        if (node && node.getBoundingClientRect().top <= edge) current = h.id;
      }
      setActive(current);
    };
    onScroll();
    el.addEventListener("scroll", onScroll, { passive: true });
    return () => el.removeEventListener("scroll", onScroll);
  }, [toc]);

  function toggle(name: string) {
    setCollapsed((c) => {
      const next = c.includes(name) ? c.filter((n) => n !== name) : [...c, name];
      save(COLLAPSED_KEY, JSON.stringify(next));
      return next;
    });
  }

  if (error && !index) return <div className="banner">{error}</div>;
  if (!index) return <div className="empty">Loading the documentation…</div>;
  if (!index.count) {
    return (
      <div className="empty">
        No documentation was found. It is installed beside the app; reinstalling
        puts it back.
      </div>
    );
  }

  const at = items.findIndex((i) => i.slug === page?.slug);
  const prev = at > 0 ? items[at - 1] : null;
  const next = at >= 0 && at < items.length - 1 ? items[at + 1] : null;
  const searching = query.trim().length >= 2;

  return (
    <div className="docs">
      <aside className="docs-nav" aria-label="Documentation">
        <label className="docs-search">
          <Search size={14} aria-hidden="true" />
          <input
            type="search"
            placeholder="Search the documentation"
            aria-label="Search the documentation"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
          {query && (
            <button type="button" className="icon" aria-label="Clear the search" onClick={() => setQuery("")}>
              <X size={14} />
            </button>
          )}
        </label>

        {searching ? (
          <div className="docs-hits" aria-live="polite">
            {hits && (
              <div className="docs-hits-title faint">
                {hits.results.length
                  ? `${hits.results.length} ${hits.results.length === 1 ? "section" : "sections"} match`
                  : `Nothing about “${query.trim()}” in ${hits.sectionsSearched} sections.`}
              </div>
            )}
            {hits?.results.map((h) => (
              <button
                type="button"
                key={`${h.slug}#${h.anchor}`}
                className="docs-hit"
                onClick={() => open(h.slug, h.anchor)}
              >
                <span className="docs-hit-title">
                  {h.heading === h.page ? h.page : `${h.page} › ${h.heading}`}
                </span>
                <span className="docs-hit-meta faint">{h.section}</span>
                <span className="docs-hit-snippet">
                  <Highlight text={plain(h.snippet)} query={query} />
                </span>
              </button>
            ))}
          </div>
        ) : (
          index.sections.map((s) => {
            const holds = s.items.some((i) => i.slug === slug);
            const open_ = holds || !collapsed.includes(s.name);
            return (
              <div className="docs-section" key={s.name}>
                <button
                  type="button"
                  className="docs-section-btn"
                  aria-expanded={open_}
                  onClick={() => toggle(s.name)}
                >
                  {open_ ? <ChevronDown size={13} /> : <ChevronRight size={13} />}
                  <span>{s.name}</span>
                  <span className="docs-count">{s.items.length}</span>
                </button>
                {open_ && (
                  <ul>
                    {s.items.map((i) => (
                      <li key={i.slug}>
                        <button
                          type="button"
                          className={"docs-item" + (i.slug === slug ? " active" : "")}
                          aria-current={i.slug === slug ? "page" : undefined}
                          title={i.summary}
                          onClick={() => open(i.slug)}
                        >
                          {i.title}
                        </button>
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            );
          })
        )}
      </aside>

      <article className="docs-main" ref={articleRef}>
        {pageError && <div className="banner">{pageError}</div>}
        {!page && !pageError && <div className="empty">Loading…</div>}
        {page && (
          <>
            <nav className="docs-crumbs faint" aria-label="Breadcrumb">
              <span>Documentation</span>
              <ChevronRight size={12} aria-hidden="true" />
              <span>{page.section}</span>
              <ChevronRight size={12} aria-hidden="true" />
              <span className="docs-crumb-here">{page.title}</span>
            </nav>
            <h1 className="docs-title">{page.title}</h1>
            <div className="docs-meta faint">
              {page.words.toLocaleString()} words · about {minutesToRead(page.words)} min read ·{" "}
              <code className="mono">{page.path}</code>
            </div>

            <div className={"docs-body" + (toc.length < 2 ? " no-toc" : "")}>
              <DocMarkdown
                className="docs-content"
                content={page.content}
                headings={page.headings}
                currentPath={page.path}
                pagePaths={pagePaths}
                onDoc={open}
              />
              {toc.length >= 2 && (
                <aside className="docs-toc" aria-label="On this page">
                  <div className="docs-toc-title">On this page</div>
                  <ul>
                    {toc.map((h) => (
                      <li key={h.id} className={`l${h.level}` + (active === h.id ? " active" : "")}>
                        <a
                          href={`#${h.id}`}
                          onClick={(e) => {
                            e.preventDefault();
                            scrollToAnchor(h.id);
                            setActive(h.id);
                          }}
                        >
                          {h.text}
                        </a>
                      </li>
                    ))}
                  </ul>
                </aside>
              )}
            </div>

            <nav className="docs-pager" aria-label="Previous and next page">
              {prev ? (
                <button type="button" className="docs-pager-link" onClick={() => open(prev.slug)}>
                  <span className="faint">Previous</span>
                  <span className="docs-pager-title">
                    <ArrowLeft size={14} aria-hidden="true" /> {prev.title}
                  </span>
                </button>
              ) : (
                <span />
              )}
              {next && (
                <button type="button" className="docs-pager-link next" onClick={() => open(next.slug)}>
                  <span className="faint">Next</span>
                  <span className="docs-pager-title">
                    {next.title} <ArrowRight size={14} aria-hidden="true" />
                  </span>
                </button>
              )}
            </nav>
          </>
        )}
      </article>
    </div>
  );
}
