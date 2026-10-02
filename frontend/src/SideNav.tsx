/**
 * The left navigation rail.
 *
 * Nine destinations had outgrown a top bar: they wrapped at narrow widths,
 * and laid out in one row they implied nine equal siblings when they are
 * really three stages of one job — get material in, work on the questions,
 * run the app. A vertical rail can say that with headings; a row cannot.
 *
 * Grouped, not sorted. The order inside each group is the order the work
 * happens in, which is why Courses comes before Generate and Bank before
 * Publish.
 */
import { useEffect, useState } from "react";
import {
  BookOpen,
  ChartColumn,
  Database,
  FileText,
  LibraryBig,
  MessagesSquare,
  PanelLeftClose,
  PanelLeftOpen,
  Send,
  Settings,
  Sparkles,
  Upload,
  Wrench,
  type LucideIcon,
} from "lucide-react";

export type Tab =
  | "courses"
  | "generate"
  | "bank"
  | "report"
  | "import"
  | "chat"
  | "exam"
  | "publish"
  | "settings"
  | "admin"
  | "docs";

interface Item {
  id: Tab;
  label: string;
  icon: LucideIcon;
  /** Shown as a quiet number beside the label. Only where a count is the
   *  thing you actually want to know before clicking. */
  count?: number;
}

export interface NavGroup {
  heading: string;
  items: Item[];
}

/** `questions` is the bank's size, shown against Bank. Passed in rather
 *  than fetched here: App already asks for health and a second caller would
 *  be a second thing to keep in step. */
export function navGroups(questions?: number): NavGroup[] {
  return [
    {
      heading: "Content",
      items: [
        { id: "courses", label: "Courses", icon: BookOpen },
        { id: "generate", label: "Generate", icon: Sparkles },
        { id: "import", label: "Import", icon: Upload },
        // Last: not a stage of the work but help with all of it - how the
        // app does a thing, or what Pentaho does, while writing a question.
        { id: "chat", label: "AI Chat", icon: MessagesSquare },
      ],
    },
    {
      heading: "Questions",
      items: [
        { id: "bank", label: "Bank", icon: Database, count: questions },
        // After Bank: you read an exam's balance once its questions are in,
        // and before you draw a paper from it.
        { id: "report", label: "Report", icon: ChartColumn },
        { id: "exam", label: "Exam paper", icon: FileText },
        { id: "publish", label: "Publish", icon: Send },
      ],
    },
    {
      heading: "System",
      items: [
        { id: "settings", label: "Settings", icon: Settings },
        { id: "admin", label: "Admin", icon: Wrench },
        { id: "docs", label: "Documentation", icon: LibraryBig },
      ],
    },
  ];
}

const COLLAPSED_KEY = "peb-nav-collapsed";

function loadCollapsed(): boolean {
  // Wrapped: localStorage throws in a private window and comes back empty
  // after cleared site data. A nav that will not render is a worse outcome
  // than a nav that forgot it was collapsed.
  try {
    return window.localStorage.getItem(COLLAPSED_KEY) === "1";
  } catch {
    return false;
  }
}

export function SideNav({
  tab,
  onSelect,
  questions,
}: {
  tab: Tab;
  onSelect: (t: Tab) => void;
  questions?: number;
}) {
  const [collapsed, setCollapsed] = useState(loadCollapsed);

  useEffect(() => {
    try {
      window.localStorage.setItem(COLLAPSED_KEY, collapsed ? "1" : "0");
    } catch {
      /* not worth telling anyone about */
    }
  }, [collapsed]);

  return (
    <nav className={"rail" + (collapsed ? " is-collapsed" : "")} aria-label="Sections">
      {navGroups(questions).map((group) => (
        // group-content / group-questions / group-system: each stage of the
        // work has its colour (icons, heading, the current page's bar).
        <div className={`rail__group group-${group.heading.toLowerCase()}`} key={group.heading}>
          {/* Still rendered when collapsed, for screen readers: the grouping
              is the point of the rail and it should not vanish with the
              labels. */}
          <div className="rail__heading" aria-hidden={collapsed}>
            {group.heading}
          </div>
          {group.items.map((item) => {
            const Icon = item.icon;
            const current = tab === item.id;
            return (
              <button
                key={item.id}
                className="rail__item"
                onClick={() => onSelect(item.id)}
                aria-current={current ? "page" : undefined}
                // The label has to reach the user somehow when it is not
                // drawn, and a title is what a rail collapsed to icons has.
                title={collapsed ? item.label : undefined}
              >
                <Icon size={16} strokeWidth={2} aria-hidden />
                <span className="rail__label">{item.label}</span>
                {item.count !== undefined && (
                  // aria-hidden: inside the button, this joins the
                  // accessible name, so the Bank button announced itself as
                  // "Bank 114" and renamed itself every time the bank grew.
                  // The number is supplementary; the name is "Bank".
                  <span className="rail__count" aria-hidden>
                    {item.count}
                  </span>
                )}
              </button>
            );
          })}
        </div>
      ))}

      <button
        className="rail__toggle"
        onClick={() => setCollapsed((c) => !c)}
        aria-expanded={!collapsed}
        title={collapsed ? "Expand the navigation" : "Collapse the navigation"}
      >
        {collapsed ? (
          <PanelLeftOpen size={16} strokeWidth={2} aria-hidden />
        ) : (
          <PanelLeftClose size={16} strokeWidth={2} aria-hidden />
        )}
        <span className="rail__label">Collapse</span>
      </button>
    </nav>
  );
}
