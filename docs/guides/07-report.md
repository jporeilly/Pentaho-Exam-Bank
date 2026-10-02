# The Report

The **Report** screen breaks down one exam at a time. Choose the exam at the
top.

- **Tiles**: how many questions, the share at Apply or above and at Analyze or
  above, the share that opens with a scenario, the draw headroom (how much
  bigger the pool is than one attempt), and how many are approved.
- **Bloom classification**: how deep the questions go, Remember to Evaluate.
- **Certification bar**: whether the exam clears the bar for its level. Each
  bar is a floor on the share at Apply or above, at Analyze or above and at
  Evaluate, and a ceiling on Remember:

  | Level | Apply+ | Analyze+ | Evaluate | Remember at most |
  | --- | --- | --- | --- | --- |
  | 1 Practitioner | 50% | 15% | 1% | 30% |
  | 2 Specialty | 60% | 30% | 5% | 20% |
  | 3 Certified | 70% | 40% | 15% | 15% |

  A figure exactly on its line passes. A course with no level (a try-it lab)
  is not scored against a bar.
- **By workshop**: the same breakdown per module, in course order.
- **Review pipeline**: how many questions are at each status.
- **Findings**: what the numbers say to do, by the same rules for every exam —
  for example questions without a scenario, a pool too small for its draw, or
  two questions that are near-duplicates.
- **Question similarity**: for every question, the most similar other question
  in the same exam, scored 0–100% (see below).
- **Every question, as classified**: the full list, filterable by Bloom level.
  Its **Nearest** column shows each question's closest neighbour and the score.

## Question similarity

Two questions that ask the same thing waste a slot in the pool and, drawn into
the same paper, can give each other away. The section shows:

- the median and highest nearest-neighbour score, and how many pairs fall in
  each band;
- a chart of how many questions have their nearest neighbour at 0–9%, 10–19%
  and so on;
- the closest pairs, each with its score and the words the two share.

| Score | Band | What to do |
| --- | --- | --- |
| 55% and above | Likely duplicate (red) | Keep one, or rewrite one to test something else. Raises a finding. |
| 40–54% | Overlap (amber) | Check the two test different things. No finding: related questions in one course are expected. |
| Under 40% | Distinct | Nothing. |

The score compares the wording of each question's scenario, question and
correct answer(s), weighting words by how rare they are within the exam, so a
course's own vocabulary does not make all of its questions look alike. Wrong
answers are left out: they are varied on purpose. Across the course exams the
median nearest neighbour scores about 18%, and 45% is already rare.
