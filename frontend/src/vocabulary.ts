/**
 * The bank's fixed lists - statuses, difficulties, Bloom levels - as the
 * server validates them (GET /api/vocabulary).
 *
 * Until 1.9.0 five screens typed their own copies, and one had drifted: the
 * Admin bulk delete offered four of the six statuses, so it could not be
 * narrowed to revised or retired questions. Now every screen asks here.
 *
 * FALLBACK is the first paint and what a screen shows if the server cannot be
 * reached; the server's answer replaces it as soon as it arrives, and is kept
 * for the rest of the session.
 */
import { useEffect, useState } from "react";

import { api, type Vocabulary } from "./api";

export const FALLBACK: Vocabulary = {
  statuses: ["draft", "sme_review", "revised", "approved", "rejected", "retired"],
  statusLabels: {
    draft: "Draft", sme_review: "SME Review", revised: "Revised",
    approved: "Approved", rejected: "Rejected", retired: "Retired",
  },
  difficulties: ["Easy", "Medium", "Hard"],
  bloomLevels: ["Remember", "Understand", "Apply", "Analyze", "Evaluate", "Create"],
};

let cached: Vocabulary | null = null;
let pending: Promise<Vocabulary> | null = null;

function usable(v: unknown): v is Vocabulary {
  const x = v as Vocabulary | null;
  return !!x && [x.statuses, x.difficulties, x.bloomLevels].every(
    (list) => Array.isArray(list) && list.length > 0,
  );
}

function load(): Promise<Vocabulary> {
  pending ??= api
    .vocabulary()
    .then((v) => {
      if (usable(v)) {
        cached = { ...v, statusLabels: { ...FALLBACK.statusLabels, ...(v.statusLabels ?? {}) } };
        return cached;
      }
      pending = null;                         // ask again next time
      return FALLBACK;
    })
    .catch(() => {
      pending = null;
      return FALLBACK;
    });
  return pending;
}

/** The lists, for rendering: the fallback at once, the server's when it answers. */
export function useVocabulary(): Vocabulary {
  const [vocabulary, setVocabulary] = useState<Vocabulary>(cached ?? FALLBACK);
  useEffect(() => {
    if (cached) return;
    let live = true;
    load().then((v) => {
      if (live) setVocabulary(v);
    });
    return () => {
      live = false;
    };
  }, []);
  return vocabulary;
}

/** What a status is called on screen. */
export function statusLabel(vocabulary: Vocabulary, status: string): string {
  return vocabulary.statusLabels?.[status] ?? status.replace("_", " ");
}

/** For tests: forget what the server said. */
export function resetVocabulary(): void {
  cached = null;
  pending = null;
}
