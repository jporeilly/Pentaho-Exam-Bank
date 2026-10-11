"""Prompt construction and constants for AI question generation."""

from typing import List, Optional

from .source import SlideInfo


# What a scenario is and what a stem is, in the one place every prompt that
# writes a question reads it from: generation, the AI rewrite, the AI fix and
# stem regeneration. The two fields do different jobs, and a model left to
# guess puts a question in the scenario or piles the context into the stem.
# core/stem_text.py checks the result, since a model can still ignore this.
SCENARIO_AND_STEM_RULES = """\
- **scenario** - one to three STATEMENTS that set the scene: a real working
  situation, who is involved and what they are dealing with. Statements only -
  never a question, never a "?". It gives the question the context it needs
  without giving away the answer, and never refers to training material.
- **stem** - ONLY the question: one direct question ending in "?". No
  statements in front of it (context belongs in the scenario), and no
  "(Choose ...)" count (the course adds its own from the number of correct
  answers). A multi-select asks for its number in the words of the question -
  "Which two ...?". Avoid negatives ("Which is NOT")."""


# What an explanation is, read by every prompt that writes one: generation,
# the AI rewrite, the AI fix and the AI explanation. Until 1.14.0 the house
# rule was to address every option ("'X' - Correct: ... 'Y' - Incorrect:
# ..."); the owner asked for the correct answer only, set out so it reads
# well after the exam. core/explanation_style.py checks the result, since a
# model can still slip back into the old labels.
EXPLANATION_RULES = """\
- **explanation** - why the correct answer is correct, and nothing else. Do NOT
  discuss the wrong options and do NOT label options "Correct:" or "Incorrect:".
  For a multi-select, explain each correct answer.
- Teach the concept: what it is or does, and why that answers this question.
  State facts plainly, as a subject matter expert.
- One to three short paragraphs of a few sentences each, every paragraph
  under 700 characters. Separate paragraphs with a blank line ("\\n\\n"
  inside the JSON string). No headings, no lists. Every sentence is
  complete, with a subject and a verb - never a fragment that starts with
  "Because" or "Which".
- Put the one to three key terms in **bold** with double asterisks - the
  feature, setting or idea the answer turns on. Bold phrases, never whole
  sentences. Beyond that, only `code` for exact names and values.
- A visual makes the answer easier to see. Add one whenever the question
  turns on an order, a structure or a piece of code - one visual at most, as
  a paragraph of its own after the first:
  - Order: a flow line of PDI's exact step or job entry names joined by
    arrows - Table input → Filter rows → Table output. Never a generic name
    ("Input step") or something that is not a step ("Preview"). Arrows are
    for PDI steps only.
  - Code: a code block of the piece the answer turns on - a JSONPath or
    regular expression, SQL, MDX, XML, a properties or JSON file: a line of
    ``` with the language (json, sql, xml, properties, regex), the code, and
    a line of ```. Inside the JSON string that is
    "\\n\\n```json\\n{...}\\n```\\n\\n". Only code the question gives, or a
    minimal sample of the structure it describes, valid as written (JSON
    that parses).
  - Structure: a small diagram in a code block marked text - a hierarchy's
    levels, a report's bands, nested grants, a folder tree - drawn with
    indentation, one item per line.
  At most 10 lines. A question about a plain fact needs no visual.
- Say each point once, directly, and stop. No sentence that only restates
  another, and no padding such as "This ensures that", "This approach
  allows" or "This design": state the fact itself.
- Refer to an answer by what it says, never by a letter or position: the
  options are shuffled."""

# Spelling, grammar and flow, for the prompts that rewrite existing text.
# Conservative on purpose: a live trial (2026-10-10, gemma4:12b, seven
# reviewed questions) turned "...a file larger than available RAM?" into
# "How does PDI handle the data volume in this transformation?" - fluent,
# and no longer the question. These questions have been reviewed; a rewrite
# polishes them, it does not re-author them.
#
# Tightened 2026-10-11 from the first 100 reviewed rewrites (1.17.0). What a
# 12B model did when told only "proofread": cut the scenario detail the
# question turns on ("processed in the order they are written", the very
# clue), added the answer's reason to the scenario, swapped the author's terms
# for synonyms ("driver job" -> "master job"), changed a word in a wrong
# answer ("decoded" -> "deployed"), lowercased every answer, and gave the
# correct answer alone a full stop. Each rule below names one of those.
#
# 1.18.0: the owner found answers cut short ("URLs and codes split into
# several") that a rewrite told to "copy each answer exactly" had kept. A cut
# answer is now named as an error to fix, and what makes an answer right
# moved to ANSWER_RULES, which generation shares.
PROOFREAD_RULES = """\
- Proofread as an exacting copy editor: spelling, grammar, punctuation,
  capitalization, agreement, and sentences a reader takes in at the first
  reading. Fix every error; change nothing that is not one. Where a sentence
  is already correct, keep it word for word.
- Scenario and question: keep every sentence, fact, name, number and
  condition. Never shorten, summarize or drop a detail - the question may
  turn on it. Never add a reason, a cause or a hint. Keep the author's terms
  (a driver job stays a driver job); do not swap them for synonyms.
- Answers: keep what each one claims, and copy it exactly unless it holds an
  error. An answer that is cut short, is missing a word it needs, or is hard
  to read IS an error: complete it with the fewest words that make it read
  whole, without changing what it claims.
- Do not change which answers are correct."""

# What makes the answers right, for every prompt that writes them: generation,
# the rewrite and the fix (1.18.0). Each rule has a check behind it -
# writing_style.answer_notes and style_notes, validation.problems_with, and
# the model's own check (REWRITE_CHECK_RULES) - so a question that follows
# them passes.
ANSWER_RULES = """\
- Every answer is complete: a whole phrase or sentence that reads on its own
  and says exactly what it means, with every word it needs. Never cut an
  answer short to fit a length - "URLs and codes split into several" is cut
  short; "URLs and codes split into several tokens" is complete. An answer
  never ends on a word such as "the", "of", "and" or "several".
- The answers to one question share one form: all full sentences ending in a
  period, or all short phrases with none, each starting with a capital
  letter.
- No answer stands out - not by its length, its detail, its wording, its
  punctuation or its formatting. The correct answer is about as long as the
  wrong ones. If it has `code` in it, the wrong answers name things in
  `code` too, or no answer uses it.
- Every answer differs from the others and none is empty. A rewrite keeps the
  number of correct and wrong answers as it is."""

# The rewrite's own system prompt (1.18.0). Until 1.17.0 the rewrite ran under
# GENERATION_SYSTEM_PROMPT - "write exam questions about the concept this
# course section teaches" - while its instruction said "polish this reviewed
# question": two jobs at odds, and a 12B model resolved them by re-authoring.
REWRITE_SYSTEM_PROMPT = """\
You are an exacting copy editor and a Pentaho subject matter expert. You
polish certification exam questions that have already been reviewed, to one
template, so that every question in an exam looks and reads the same. You fix
what is wrong - spelling, grammar, punctuation, an answer cut short, an
explanation that discusses the wrong options - and keep everything that is
right exactly as it is. You never re-author a question, change what it tests,
or change which answer is correct. Return ONLY valid JSON."""

# Quotes, names and punctuation (1.15.0). The owner, reviewing the first bulk
# rewrite: single quotes everywhere, used no standard way. A survey of the
# 489 questions found 143 single-quoted spans doing six jobs - a field name
# ('region_code'), a value ('undefined'), a path, a step ('Stream Lookup'), an
# ordinary word ('sales' records), an option's text - and "Stream Lookup"
# beside PDI's own "Stream lookup". One rule per job, below; the mechanical
# part is applied after the model as well (core/writing_style.py), because a
# model told the rule still slips.
WRITING_RULES = """\
- `code` (backticks) only for an exact name or literal as it appears in a
  file, field, query or screen: field, column, table and key names, file
  names, paths, variables, expressions, and literal values as typed -
  `region_code`, `$.customers[*].region_code`, `kettle.properties`,
  `${INPUT_DIR}`, `Y`. Never in quotation marks. NOT for ordinary nouns
  (customer data, order records, a region file) and NOT for numbers in a
  sentence (a price of 49.99, 20 rows).
- PDI steps, job entries, perspectives and menu items are named exactly as PDI
  shows them, as plain text without quotes: Stream lookup, Filter rows, Text
  file input, Select values. Add "step" or "option" where the name could be
  read as an ordinary word: the Copy option.
- No quotation marks around ordinary words or for emphasis: sales records, not
  'sales' records. Never single quotes. Double quotes only for words quoted
  exactly as written, such as an error message.
- Straight quotes and apostrophes, never curly ones. No contractions: does
  not, cannot, it is.
- American spelling (normalize, behavior, color), except in a product's own
  names (Row normaliser).
- Bold (double asterisks) only for the explanation's key terms - never in the
  scenario, the question or an answer, where it would make words stand out.
- A serial comma before "and" or "or" in a list of three or more: fields,
  rows, and steps.
- Numbers: one to nine in words, 10 and above in digits, and digits for every
  value, size or count with a unit (5 GB, 3 ms); thousands with commas
  (10,000)."""

# For a rewrite of an explanation that already exists. The same trial had the
# model replace a verified fact (a canvas preview starts every step, so a
# connected output step DOES write) with an invented opposite ("without ...
# writing to a destination"). The facts are the reviewed part; keep them.
EXPLANATION_REWRITE_RULES = """\
- If the CURRENT explanation already explains only why the correct answer is
  right, with no padding, it has been reviewed: keep its sentences word for
  word, fixing only an error. Do not reword it, lengthen it or add to it -
  except one visual (a flow line, a code block or a text diagram) as a
  paragraph of its own, where the question turns on an order, a structure or
  code and it has none.
- Otherwise, rewrite the CURRENT explanation; do not write a new one. Keep every fact it
  gives about why the correct answer is right - every caveat, condition,
  number, setting name and example (a formula, an expression, a path) - and
  drop only what it says about the wrong options.
- Add no claim the current explanation does not make: no benefits, no "best
  practice", no features it does not name. If it says little, the new one
  says little. A flow line of steps the question names, or a code block of
  code or structure the question gives, is not a new claim."""

# What the second pass checks in every rewrite (1.17.0): the answer and the
# explanation are CORRECT, nothing was lost or added, and the language is
# clean. Its findings are notes on the proposal, so a rewrite with any of
# them waits for the author instead of being accepted with the rest.
REWRITE_CHECK_RULES = """\
- The answer marked correct is correct, and no answer marked wrong is also
  correct.
- The explanation is accurate, agrees with the correct answer, and says each
  point once, without padding.
- The rewrite lost no fact, condition or caveat from the original scenario or
  question, and nothing the original explanation says about why the correct
  answer is right. (Dropping what it said about the wrong answers is
  intended - that is not a loss.) It added no claim the original does not
  make.
- Every answer is complete and reads clearly on its own: none is cut short or
  missing a word it needs - a noun, an article, a verb or an object. The
  correct answer does not stand out from the wrong ones by its length,
  detail, wording or form.
- No spelling, grammar, punctuation or capitalization error is left, and
  every sentence reads clearly at the first reading."""


GENERATION_SYSTEM_PROMPT = """\
You are an expert certification exam item writer.

You are given one section of a training course. Use it to work out WHICH concept,
product or feature is being taught, then write exam questions about that concept.

1. EXAMINE THE CONCEPT, NOT THE WORKSHOP. A workshop exists to reinforce a concept
by having someone practise it; the concept is what the exam is about and the
workshop is scaffolding. Test whether the candidate understands the thing itself -
how it works, when to use it, why one approach beats another, what breaks if it is
configured badly. Never test recall of the exercise: which button to click, what a
sample file held, what one run produced. If rewriting the workshop with a different
example would spoil your question, you have examined the workshop.

2. THE ANSWER MUST BE TRUE. Use established knowledge of Pentaho and the
technologies around it. It need not be a sentence from the material, but it must be
correct - a plausible invention is the worst thing you can produce, because it will
be marked right in a real exam. Unsure of a fact? Ask about something you are sure of.

3. THE QUESTION MUST STAND ALONE. A candidate answers it months later with no course
in front of them. Never name a lab, section, module or step, and never mention
"the workshop", "the source material" or where anything came from. Never refer to
something they cannot see - "the optimized transformation", "this environment".
Never ask them to recall a benchmark or a hardware-specific timing. The Topic you
are given is a filing label, not the subject to ask about.

   The test: could a competent practitioner who never took this course answer it
   from knowing the product? If not, rewrite it.

4. IF THE SECTION IS NOT EXAMINABLE, RETURN [] AND NOTHING ELSE. Navigation,
environment setup, a welcome page, instructions for using the guide - there is no
certification question in any of it, and a forced one is worse than none.

FORMAT - real certification exam style:
""" + SCENARIO_AND_STEM_RULES + """
- **key** / **keys** - the correct answer(s): true, and about the concept.
- **distractors** - plausible but wrong. A common misconception, a confusion with a
  neighboring feature, or a partial truth. Similar in length to the key,
  grammatically consistent with the stem. Never "All/None of the above".
""" + ANSWER_RULES + """
""" + EXPLANATION_RULES + """
- **key_source_text** - a short quote from the section showing this TOPIC is part of
  the course. It anchors the question to the syllabus and need NOT contain the
  answer. Internal only; never shown to a candidate.

WRITING - quotes, names and punctuation, in every field a candidate sees:
""" + WRITING_RULES + """

Answer with the JSON array and nothing else. Do not think aloud, explain yourself,
or add commentary before or after it.

EXAMPLE of the exact format expected:
  Scenario: "A retailer runs separate customer, order and loyalty systems, and each \
team keeps its own copy of the customer record."
  Stem: "What are two reasons to use Pentaho Data Integration (PDI) to break down \
those data silos?"
  Keys: ["PDI can provide a complete 360-degree view of the master data, such as \
customer or patient records.", "PDI creates a central, searchable data repository for \
the entire data estate."]
  Distractors: ["PDI automatically classifies disparate data for easier search and \
retrieval.", "PDI helps businesses comply with key regulations like HIPAA and EHR."]
  Explanation: "PDI **integrates disparate sources** into one unified view of the \
master data, so every team works from the same customer record instead of its own \
copy.\\n\\nBecause the integrated data lands in one place, it also becomes a \
**central, searchable repository** for the whole data estate."

Follow Bloom's Taxonomy levels for cognitive rigor:
- Remember: Recall facts
- Understand: Explain concepts
- Apply: Use knowledge in new situations
- Analyze: Break down and examine
- Evaluate: Make judgments
- Create: Produce new work

Return your response as a JSON array of question objects."""


def _build_question_specs(num_questions: int, num_keys: int = 1, num_distractors: int = 3) -> List[dict]:
    """Build specs for each question using explicit key and distractor counts.

    Returns a list of dicts like:
        [{"type": "single", "num_choices": 4}, {"type": "multi", "num_correct": 2, "num_choices": 5}, ...]
    When num_keys > 1, all questions are multi-select. Otherwise single-select.
    """
    specs = []
    total_choices = num_keys + num_distractors
    for _ in range(num_questions):
        if num_keys > 1:
            specs.append({"type": "multi", "num_correct": num_keys, "num_choices": total_choices})
        else:
            specs.append({"type": "single", "num_choices": total_choices})
    return specs


def specs_from_rows(rows: List[dict]) -> List[dict]:
    """Turn ``[{"keys": 1, "distractors": 3}, {"keys": 2, "distractors": 3}]``
    into the spec dicts the generator uses.

    One row is one question SHAPE, and a run cycles through them — which is
    what makes a mixed run possible. ``_build_question_specs`` above produces
    the same shape N times, so a run built from it is uniform however it is
    shuffled.

    Rows with nothing correct or nothing wrong are dropped rather than sent:
    a question with no distractors has one option, and a question with no key
    has no answer.
    """
    specs: List[dict] = []
    for row in rows:
        keys = int(row.get("keys", 1) or 0)
        distractors = int(row.get("distractors", 3) or 0)
        if keys < 1 or distractors < 1:
            continue
        total = keys + distractors
        if keys > 1:
            specs.append({"type": "multi", "num_correct": keys, "num_choices": total})
        else:
            specs.append({"type": "single", "num_choices": total})
    return specs


def _num_word(n: int) -> str:
    """Convert small int to word for stems: 2 -> 'two', 3 -> 'three'."""
    return {2: "two", 3: "three", 4: "four"}.get(n, str(n))


def build_prompt(
    slide: SlideInfo,
    num_questions: int = 2,
    difficulty: str = "Medium",
    bloom_level: str = "Apply",
    certification: str = "",
    custom_instructions: str = "",
    question_specs: Optional[List[dict]] = None,
) -> str:
    """Build the generation prompt from slide content."""
    if question_specs is None:
        question_specs = _build_question_specs(num_questions)

    parts = []

    parts.append(
        "Below is one section of a training course. Identify the concept, product "
        "or feature it teaches, then write certification questions about THAT — "
        "not about the exercise used to teach it.\n"
        "Draw on what you know about the subject; the section tells you what is in "
        "scope, it is not the answer key.\n"
    )

    if slide.title:
        # Labelled as filing, not subject. Given plainly as "**Topic:**" the
        # model treats the course's own navigation as the thing to examine and
        # writes "What is the purpose of the Before You Start section?".
        parts.append(
            f"**Topic (a filing label for the question — do NOT ask about it, "
            f"and do NOT mention it in the question):** {slide.title}"
        )
    if slide.body_text:
        parts.append(f"**Content:**\n{slide.body_text}")
    if slide.speaker_notes:
        parts.append(f"**Source Material:**\n{slide.speaker_notes}")

    parts.append(f"\n**Requirements:**")
    parts.append(f"- Generate exactly {num_questions} question(s)")
    parts.append(f"- Difficulty: {difficulty}")
    parts.append(f"- Bloom's Taxonomy Level: {bloom_level}")
    if certification:
        parts.append(f"- Certification: {certification}")

    # Varying format per question
    parts.append(f"- VARYING question formats:")
    for i, spec in enumerate(question_specs):
        if spec["type"] == "multi":
            nc = spec["num_correct"]
            nd = spec["num_choices"] - nc
            parts.append(f'  - Question {i+1}: MULTI-SELECT — the question asks for exactly {_num_word(nc)} '
                         f'answers ("Which {_num_word(nc)} ...?") '
                         f'({nc} correct answers + {nd} distractors = {spec["num_choices"]} total choices)')
        else:
            nd = spec["num_choices"] - 1
            parts.append(f'  - Question {i+1}: SINGLE-SELECT — the question has one correct answer '
                         f"(1 correct + {nd} distractors = {spec['num_choices']} total choices)")

    parts.append(f"- CRITICAL: All correct answers MUST come from the Source Material above")
    parts.append(f"- CRITICAL: 'key_source_text' must be an EXACT quote from the Source Material")
    parts.append(f"- If no Source Material exists, use the Content text instead")
    parts.append(f"- Distractors can be anything plausible but must NOT be in the source content")
    parts.append(f"- Format choices like a real certification exam (A:, B:, C:, D:)")
    parts.append("- CRITICAL: The explanation says why the correct answer(s) are right - never "
                 "discuss the wrong options or label options Correct/Incorrect. One to three "
                 "short paragraphs, the key terms in **bold**.")
    parts.append(f"- NEVER mention 'speaker notes', 'slides', 'source material', or 'training material' "
                 f"in the scenario, stem, choices, or explanation. Write as a subject matter expert.")

    if custom_instructions:
        parts.append(f"\n**Additional Instructions:**\n{custom_instructions}")

    parts.append(f"""
Return ONLY a JSON array. Each element must have these exact keys:

For SINGLE-SELECT questions:
```json
{{
  "question_type": "single",
  "scenario": "One to three statements that set the scene. No question here.",
  "stem": "Only the question, ending in ?",
  "key": "the single correct answer",
  "key_source_text": "exact quote from source material",
  "distractors": ["wrong1", "wrong2", "wrong3"],
  "explanation": "Why the correct answer is right, with the **key term** in bold.\\n\\nA second short paragraph if it helps."
}}
```

For MULTI-SELECT questions — the question names how many it wants ("Which two ...?"):
```json
{{
  "question_type": "multi",
  "scenario": "One to three statements that set the scene. No question here.",
  "stem": "What are two reasons ...?",
  "keys": ["correct answer 1", "correct answer 2"],
  "key_source_text": "exact quotes from source material supporting both answers",
  "distractors": ["wrong1", "wrong2"],
  "explanation": "Why **correct answer 1** is right.\\n\\nWhy **correct answer 2** is right."
}}
```

IMPORTANT: The explanation covers the correct answer(s) only, never the wrong options:
{EXPLANATION_RULES}
```""")

    return "\n\n".join(parts)
