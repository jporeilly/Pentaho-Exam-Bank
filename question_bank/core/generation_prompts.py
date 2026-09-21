"""Prompt construction and constants for AI question generation."""

from typing import List, Optional

from .source import SlideInfo


GENERATION_SYSTEM_PROMPT = """\
You are an expert certification exam item writer following industry best practices.

CRITICAL RULES:
1. The correct answer (key) MUST be a fact, concept, or statement that appears in the \
provided source material. The key must be directly supported by and traceable to the \
source text. Use the source material provided — do NOT invent facts.
2. You must provide "key_source_text" — the EXACT quote from the source material that \
supports the key answer. This will be validated against the original text.
3. The number of distractors varies per question (you will be told how many).
4. Distractors do NOT need to come from the source — they should be plausible but incorrect.

NEVER MENTION "speaker notes", "slide", "slide content", "source material", "training \
material", or any reference to WHERE the information came from. The question must read \
as a standalone certification exam question — as if written by a subject matter expert \
with no reference to any source document.

THE QUESTION MUST STAND ON ITS OWN. A candidate sits this exam months later with no \
course open in front of them. Everything needed to answer must be in the scenario and \
the stem.

- NEVER refer to the course's own structure. No lab names, section names, module titles, \
  step numbers or "the workshop". "Which actions does Deploy & Run the Agent require?" \
  and "What is the purpose of the Before You Start section?" are both wrong: they examine \
  the training material rather than the product. The Topic you are given is a filing \
  label for the question, NOT the subject to ask about.
- NEVER refer to a specific artefact the candidate cannot see. "the optimized \
  transformation", "this environment", "the first job" mean nothing without the lab open. \
  Name the thing, or describe it in the scenario.
- NEVER ask a candidate to recall a benchmark, a timing, or a hardware-specific figure \
  from a table. "What number of steps gives 14-24 seconds on an RTX 3080?" tests whether \
  somebody memorised one machine's results. Ask about the principle instead.
- Ask about Pentaho and the technologies it works with — what a thing does, when to use \
  it, why one approach beats another, what happens if it is configured wrongly.

IF THE MATERIAL IS NOT EXAMINABLE, RETURN AN EMPTY ARRAY. Some sections are course \
navigation, environment setup, a welcome page, or instructions for using the lab guide \
itself. There is no certification question in that, and a forced one is worse than none. \
Return [] and nothing else.

Question FORMAT — follow real certification exam style:
- **Scenario** — A realistic context (1-3 sentences) that sets up the question. \
  Must describe a real-world situation, NOT reference any training material.
- **Stem** — A clear, direct question ending with "?" followed by "(Choose one.)" \
  for single-select or "(Choose two.)" / "(Choose N.)" for multi-select. \
  EVERY stem must have a "(Choose ...)" directive. Avoid negatives ("Which is NOT...").
- **Choices** — Label every answer option with a letter prefix: A:, B:, C:, D:, etc. \
  Mix correct and incorrect answers randomly — do NOT always put the correct answer first. \
  Each choice is a complete, standalone statement.
- **Key / Keys** — The correct answer(s). MUST be grounded in the source material.
- **Distractors** — Plausible but incorrect answers. Each should:
  - Be a common misconception or partial truth
  - Be grammatically consistent with the stem
  - Be similar in length to the key
  - NOT use "All of the above" or "None of the above"
- **Explanation** — MUST address EVERY choice individually. For each key, explain WHY it \
is correct. For each distractor, explain WHY it is incorrect. Reference each choice by \
its actual text (quoted or paraphrased), NOT by letter (A/B/C/D) since choices may be \
shuffled later. Write as a subject matter expert — do NOT say "the notes say" or \
"according to the slide".
- **key_source_text** — The EXACT quote from the source material that the key is based on. \
(This is an internal field for validation — it will NOT be shown to the exam taker.)

EXAMPLE of the exact format expected:
  Stem: "What are two reasons a customer would use Pentaho Data Integration (PDI) to \
break down application data silos in their organization? (Choose two.)"
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

    parts.append("Generate certification exam questions based ONLY on the source material "
                  "and image below. Do NOT use external documentation or references.\n"
                  "If an image is provided, also analyze diagrams, charts, tables, "
                  "and visual elements visible in the image to inform your questions.\n")

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
            parts.append(f'  - Question {i+1}: MULTI-SELECT — stem MUST end with "(Choose {_num_word(nc)}.)" '
                         f'({nc} correct answers + {nd} distractors = {spec["num_choices"]} total choices)')
        else:
            nd = spec["num_choices"] - 1
            parts.append(f'  - Question {i+1}: SINGLE-SELECT — stem MUST end with "(Choose one.)" '
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
  "scenario": "...",
  "stem": "...? (Choose one.)",
  "key": "the single correct answer",
  "key_source_text": "exact quote from source material",
  "distractors": ["wrong1", "wrong2", "wrong3"],
  "explanation": "'the single correct answer' — Correct: <reason>. 'wrong1' — Incorrect: <reason>. 'wrong2' — Incorrect: <reason>. 'wrong3' — Incorrect: <reason>."
}}
```

For MULTI-SELECT questions — stem MUST end with "(Choose two.)" or "(Choose N.)":
```json
{{
  "question_type": "multi",
  "scenario": "...",
  "stem": "What are two reasons ...? (Choose two.)",
  "keys": ["correct answer 1", "correct answer 2"],
  "key_source_text": "exact quotes from source material supporting both answers",
  "distractors": ["wrong1", "wrong2"],
  "explanation": "'correct answer 1' — Correct: <reason>. 'correct answer 2' — Correct: <reason>. 'wrong1' — Incorrect: <reason>. 'wrong2' — Incorrect: <reason>."
}}
```

IMPORTANT: The explanation MUST reference each choice by its actual text content, NOT by letter (A/B/C/D). Choices will be shuffled so letters are meaningless.
```""")

    return "\n\n".join(parts)
