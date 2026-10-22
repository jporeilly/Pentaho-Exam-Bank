/**
 * The house style: the template every question is written to (1.14.0).
 *
 * Read from the server, which returns the very rules the prompts carry
 * (core/generation_prompts.py), so what the author reads here is what the
 * model is told - generating, rewriting one question or rewriting an exam.
 * Collapsed by default; it is reference, not a step.
 */
import { useEffect, useState } from "react";

import { api, type HouseStyleSection } from "./api";
import { Formatted } from "./inlineFormat";

/** The rules text is a list of "- " bullets, each wrapped over indented lines. */
export function bullets(rules: string): string[] {
  const out: string[] = [];
  for (const line of rules.split("\n")) {
    if (line.startsWith("- ")) out.push(line.slice(2).trim());
    else if (out.length && line.trim()) out[out.length - 1] += " " + line.trim();
  }
  return out;
}

export function HouseStyle({ intro }: { intro?: string }) {
  const [sections, setSections] = useState<HouseStyleSection[]>([]);

  useEffect(() => {
    api
      .houseStyle()
      .then((style) => setSections(Array.isArray(style?.sections) ? style.sections : []))
      .catch(() => setSections([]));
  }, []);

  if (!sections.length) return null;
  return (
    <details className="house-style">
      <summary>The house style - how every question is written</summary>
      {intro && <p className="muted">{intro}</p>}
      {sections.map((s) => (
        <section key={s.title} className="house-style__section">
          <h4>{s.title}</h4>
          <ul>
            {bullets(s.rules).map((b) => (
              <li key={b}>
                <Formatted text={b} />
              </li>
            ))}
          </ul>
        </section>
      ))}
    </details>
  );
}
