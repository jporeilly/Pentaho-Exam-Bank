# Glossary

The terms the Exam Bank's screens use, in alphabetical order.

## Adopt

Bring a course's exam questions into the bank, from the course's `exam.json`
(**Courses → Check courses for questions**, then **Adopt into the bank**).
Adopted questions arrive as drafts, with their ids and order kept.

## Apply+, Analyze+

The share of an exam's questions at a Bloom level of Apply or above, or Analyze
or above. Each certification bar sets a floor on both. See
[The Report](../guides/07-report.md).

## Bloom level

How deep a question goes, on Bloom's taxonomy: Remember, Understand, Apply,
Analyze, Evaluate, Create. Recall questions (Remember) are capped by the
certification bars; the deeper levels have floors.

## Certification

What a question is filed under in the bank: usually one per course's exam.
Generate, Import and Publish all ask for one.

## Certification bar

The minimum Bloom mix an exam must have for its certification level:

| Level | Apply+ | Analyze+ | Evaluate | Remember at most |
| --- | --- | --- | --- | --- |
| 1 Practitioner | 50% | 15% | 1% | 30% |
| 2 Specialty | 60% | 30% | 5% | 20% |
| 3 Certified | 70% | 40% | 15% | 15% |

A figure exactly on its line passes. A course with no level, such as a try-it
lab, is not scored against a bar.

## Content Editor, Content Manager

The **Pentaho Content Manager** is the learner's app, which shows a course and
runs its exam. The **Pentaho Content Editor** is where a course's pages are
written; its **Questions** button opens the Exam Bank on the course being
edited. The Exam Bank reads and writes the courses in the Content Manager's
`courses/` folder.

## Distractor

A wrong option: plausible, wrong, and about the length of the correct answer.
See [How a question is written](../writing/01-how-a-question-is-written.md).

## Draw

How many questions one attempt at an exam takes from its pool, at random:
`questionsPerAttempt` in the course's `exam.json`.

## Draw headroom

How much bigger the pool is than one draw, as a share of the pool:
(pool − draw) ÷ pool. Drawing 20 from 30 gives 33%. With no headroom every
candidate sits the same paper, and one sitting exposes the whole pool.

## `exam.json`

A course's exam: its questions, pass mark, draw size and description, in the
course's folder. The Content Manager reads it; the Exam Bank adopts from it and
publishes to it.

## Explanation

Shown to the candidate after the exam: why each correct answer is right and
each distractor is wrong, naming each option by its text.

## Key

The correct answer, or answers, of a question.

## MCP

Model Context Protocol: a standard way for an AI application to call tools
another service offers. AI Chat uses the MCP server of docs.pentaho.com to
search Pentaho's documentation. See
[The Pentaho docs connection](../ai/02-pentaho-docs-connection.md).

## Multi-select

A question with more than one correct answer. It asks for them in its own
words ("Which two …?"); the Content Manager adds *(Choose two)*, and a
candidate scores only by choosing exactly the right set.

## Pass mark

The percentage an attempt must reach to pass, set in `exam.json`.

## Pentaho-Courses

The courses repository that installed Content Managers sync from each time they
start. **Publish and push** writes a course's exam there, so learners get it
without a new installer.

## Pool

Every question in a course's exam, from which each attempt draws.

## Publish

Write the bank's questions for a course into its `exam.json`, replacing the
pool with the questions of the chosen statuses. With **push**, also commit it
and send it to Pentaho-Courses. See [Publishing to a course](../guides/09-publishing.md).

## Question id

A question's durable key: `<course>-m<module>-q<question>`, as in `di-m3-q7`
(DI Practitioner, module 3, question 7). The Content Manager records results
and saved attempts against it. The bank gives every question it files into a
course an id in this format; see
[Generating questions](../guides/03-generating.md#filed-like-the-courses-own-questions).

## Scenario

One to three statements that set the scene for a question: a real working
situation, never a question itself.

## SME Review

Waiting for a subject-matter expert (SME) to review. The statuses a question
moves through are Draft, SME Review, Revised, Approved, Rejected and Retired;
see [Review](../guides/06-review.md).
