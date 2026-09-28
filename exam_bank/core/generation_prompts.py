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
  neighbouring feature, or a partial truth. Similar in length to the key,
  grammatically consistent with the stem. Never "All/None of the above".
- **explanation** - address EVERY choice: why each key is right and each distractor
  wrong. Refer to choices by their text, never by letter, since they get shuffled.
- **key_source_text** - a short quote from the section showing this TOPIC is part of
  the course. It anchors the question to the syllabus and need NOT contain the
  answer. Internal only; never shown to a candidate.

Answer with the JSON array and nothing else. Do not think aloud, explain yourself,
or add commentary before or after it.

EXAMPLE of the exact format expected:
  Scenario: "A retailer runs separate customer, order and loyalty systems, and each \
team keeps its own copy of the customer record."
  Stem: "What are two reasons to use Pentaho Data Integration (PDI) to break down \
those data silos?"
  Keys: ["PDI can provide a comprehensive 360 view of the master data, e.g customer \
or patient.", "PDI creates a central, searchable data repository the entire data estate."]
  Distractors: ["PDI automatically classifies disparate data for easier search and \
retrieval.", "PDI helps businesses comply with key regulations like HIPAA and EHR."]
  Explanation: "'PDI can provide a comprehensive 360 view' — Correct: PDI integrates \
disparate sources to provide a unified master data view. 'PDI creates a central, \
searchable data repository' — Correct: this is a core capability for breaking down \
data silos. 'PDI automatically classifies disparate data' — Incorrect: PDI does not \
automatically classify data; classification requires separate tooling. 'PDI helps \
businesses comply with key regulations' — Incorrect: while compliance may be a \
benefit, it is not a primary reason for breaking down data silos."

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
    parts.append(f"- CRITICAL: Explanation must address EACH choice by its text content (not by letter A/B/C/D, since choices are shuffled)")
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
  "explanation": "'the single correct answer' — Correct: <reason>. 'wrong1' — Incorrect: <reason>. 'wrong2' — Incorrect: <reason>. 'wrong3' — Incorrect: <reason>."
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
  "explanation": "'correct answer 1' — Correct: <reason>. 'correct answer 2' — Correct: <reason>. 'wrong1' — Incorrect: <reason>. 'wrong2' — Incorrect: <reason>."
}}
```

IMPORTANT: The explanation MUST reference each choice by its actual text content, NOT by letter (A/B/C/D). Choices will be shuffled so letters are meaningless.
```""")

    return "\n\n".join(parts)
