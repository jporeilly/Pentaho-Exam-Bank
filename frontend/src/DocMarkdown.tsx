/**
 * Markdown as the Documentation screen and AI Chat show it.
 *
 * One renderer for both, so a table, a code block or a link looks the same in
 * a page and in an answer. What differs is passed in:
 *
 * - `headings` gives each rendered heading its id. The backend decides the
 *   ids (GitHub's rule, repeats numbered) and this matches them by SOURCE
 *   LINE, so there is one slug rule in the app, not two that disagree about
 *   the first heading with an ampersand in it.
 * - `onDoc` receives links to other pages; `onCite` receives an answer's
 *   `[A1]` markers, which `linkCitations` has made into `#cite-A1` links.
 *
 * External links go to the system browser through the backend: the window is
 * a webview without Tauri's APIs, where `target="_blank"` goes nowhere.
 */
import ReactMarkdown, { type Components } from "react-markdown";
import remarkGfm from "remark-gfm";

import { api, type DocHeading } from "./api";
import { resolveDocLink } from "./docLinks";

/** Open a web page in the system browser; in a plain browser tab (the dev
 *  server), a new tab does the same job if the backend refuses. */
export function openExternal(url: string): void {
  api.openUrl(url).catch(() => {
    window.open(url, "_blank", "noopener,noreferrer");
  });
}

/** Scroll the heading with this id into view, if it is on the page. */
export function scrollToAnchor(id: string): boolean {
  const el = id ? document.getElementById(id) : null;
  if (!el) return false;
  el.scrollIntoView({ block: "start" });
  return true;
}

interface Props {
  content: string;
  headings?: DocHeading[];
  /** The page's repo-relative path, to resolve its relative links against. */
  currentPath?: string;
  pagePaths?: ReadonlySet<string>;
  onDoc?: (slug: string, anchor: string) => void;
  onCite?: (id: string) => void;
  className?: string;
}

const NO_PAGES: ReadonlySet<string> = new Set();

export function DocMarkdown({
  content,
  headings = [],
  currentPath = "",
  pagePaths = NO_PAGES,
  onDoc,
  onCite,
  className = "",
}: Props) {
  const byLine = new Map(headings.map((h) => [h.line, h.id]));

  function heading(Tag: "h1" | "h2" | "h3" | "h4") {
    return function Heading({ node, children }: { node?: { position?: { start: { line: number } } }; children?: React.ReactNode }) {
      const id = byLine.get(node?.position?.start.line ?? -1);
      return <Tag id={id}>{children}</Tag>;
    };
  }

  const components: Components = {
    h1: heading("h1"),
    h2: heading("h2"),
    h3: heading("h3"),
    h4: heading("h4"),
    table: ({ children }) => (
      <div className="md-table">
        <table>{children}</table>
      </div>
    ),
    a: ({ href = "", children }) => {
      const cite = /^#cite-([AP]\d+)$/.exec(href);
      if (cite) {
        const id = cite[1];
        return (
          <button
            type="button"
            className="cite"
            title={`Open source ${id}`}
            onClick={() => onCite?.(id)}
          >
            {id}
          </button>
        );
      }
      const link = resolveDocLink(href, currentPath, pagePaths);
      switch (link.kind) {
        case "external":
          return (
            <a
              href={link.url}
              target="_blank"
              rel="noopener noreferrer"
              onClick={(e) => {
                e.preventDefault();
                if (link.url.startsWith("mailto:")) window.location.href = link.url;
                else openExternal(link.url);
              }}
            >
              {children}
            </a>
          );
        case "anchor":
          return (
            <a
              href={`#${link.anchor}`}
              onClick={(e) => {
                e.preventDefault();
                scrollToAnchor(link.anchor);
              }}
            >
              {children}
            </a>
          );
        case "doc":
          return (
            <a
              href={`#${link.slug}`}
              onClick={(e) => {
                e.preventDefault();
                onDoc?.(link.slug, link.anchor);
              }}
            >
              {children}
            </a>
          );
        default:
          return <span className="md-deadlink">{children}</span>;
      }
    },
  };

  return (
    <div className={`md ${className}`.trim()}>
      <ReactMarkdown remarkPlugins={[remarkGfm]} components={components}>
        {content}
      </ReactMarkdown>
    </div>
  );
}
