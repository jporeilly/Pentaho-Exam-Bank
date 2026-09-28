# Bloom review — Pentaho Content Manager exam corpus

A per-question classification of all eleven PCM exams against Bloom's
revised taxonomy, with a verdict and a one-line reason for each. Made in
September 2026, as the input to the rework that followed.

**This is a snapshot, not a source of truth.** A question's current level
lives in `courses/<slug>/exam.json` in Pentaho-Content-Manager, in its
`bloom` field, and that is the only place to read it from. These files
record what each question looked like when it was reviewed and what the
review concluded — which is worth keeping precisely because the exam
files record the outcome and not the reasoning.

## How stale

Measured against Pentaho-Content-Manager at `5bddd0c`:

| | |
| --- | --- |
| questions covered | 395 (the corpus is now 413) |
| `level` no longer matching the course file | 85 |
| tagged `rewrite` / `rename` | 134 |
| of those, acted on since | 69 |
| **still open** | **65** |

Two courses have gained questions since the review, so it does not cover
them: `architect-install-certified` (12 reviewed, 20 now) and
`pdi-2hr-lab` (20 reviewed, 30 now).

The drift is the rework happening, not rot. Where a `level` here
disagrees with the course file, the course file is right and the
difference is the question having been rewritten.

## Schema

```json
{
  "course": "developer-sd-specialty",
  "note": "free text about the exam as a whole",
  "questions": [
    { "id": "sd-concept-q1",
      "level": "Understand",
      "verdict": "keep",
      "why": "Unbounded-vs-finite is the defining distinction, asked directly." }
  ]
}
```

- `level` — Remember | Understand | Apply | Analyze | Evaluate, **as at
  the review**. Create is unreachable in multiple choice.
- `verdict` — `keep`, `rewrite` (the question is defective, not merely
  low), or `rename` (sound, but refers to a workshop by number or to
  itself).
- `why` — the reason, which is the part that does not survive anywhere
  else. `RECALL FLOOR` marks a fact defended as operationally
  consequential rather than trivia.

## What it is still good for

The 65 open `rewrite`/`rename` verdicts are a worklist, and each carries
the reason it was tagged. The `note` on each file describes the exam's
character — which anti-pattern dominates it, whether it anchors to
workshop steps, whether its scenarios do real work.

`architect-install-certified.json` is the most useful single file: its
`RECALL FLOOR` entries are the argument that collided with the Level 3
recall ceiling, and reading it explains why that exam was rewritten the
way it was rather than by dropping the facts.

## Regenerating

There is no generator. These were written by reading every question.
Anything that reproduced them mechanically would reproduce the levels
and lose the reasons, which are the point.
