"""Post-generation AI operations: regen, improve, QA check, explanation, key assignment."""

import json
import re
import string
from typing import List, Optional

from . import providers
from .question_bank import Question
from .generation_prompts import GENERATION_SYSTEM_PROMPT, _num_word
from .generation_parsing import _extract_json_array, _extract_json_object


def regen_stem(
    question: Question,
    model: str,
    base_url: str = "http://localhost:11434",
    system_prompt: str = "",
) -> Optional[str]:
    """Regenerate only the stem (and scenario) — all choices stay locked."""
    is_multi = question.question_type == "multi" and question.keys and len(question.keys) > 1
    keys_json = json.dumps(question.keys) if is_multi else json.dumps([question.key])
    num_correct = len(question.keys) if is_multi else 1

    prompt = f"""Rewrite ONLY the stem and scenario for this certification exam question.
All answer choices must remain EXACTLY the same — do NOT change them.

**Current scenario:** {question.scenario}
**Current stem:** {question.stem}
**{"Keys" if is_multi else "Key"} (DO NOT CHANGE):** {keys_json}
**Distractors (DO NOT CHANGE):** {json.dumps(question.distractors)}
**Key source text:** {question.key_source_text}

RULES:
- Write a new scenario and stem that still leads to the same correct answer(s).
- The stem must end with "(Choose {_num_word(num_correct) if num_correct > 1 else 'one'}.)"
- Keep the same difficulty and cognitive level.
- The new stem must still be answerable from the key_source_text.

Return ONLY a JSON object:
```json
{{"scenario": "...", "stem": "...? (Choose {_num_word(num_correct) if num_correct > 1 else 'one'}.)"}}
```"""

    try:
        response = providers.generate(
            prompt=prompt, model=model,
            system=system_prompt or GENERATION_SYSTEM_PROMPT,
            base_url=base_url, timeout=120.0,
        )
    except Exception as e:
        print(f"[REGEN-STEM] AI call failed: {e}")
        return None

    data = _extract_json_object(response)
    if not data:
        return None

    if "stem" in data:
        question.scenario = data.get("scenario", question.scenario)
        question.stem = data["stem"]
        # Ensure "(Choose ...)" is present
        stem = question.stem.strip()
        if "choose" not in stem.lower():
            word = _num_word(num_correct) if num_correct > 1 else "one"
            question.stem = f"{stem} (Choose {word}.)"
        return question.stem
    return None


def regen_key(
    question: Question,
    key_index: int,
    model: str,
    base_url: str = "http://localhost:11434",
    system_prompt: str = "",
) -> Optional[str]:
    """Regenerate a single correct answer (key) — stem and distractors stay locked.

    For single-select questions, key_index is always 0.
    For multi-select, key_index selects which key to replace.
    """
    is_multi = question.question_type == "multi" and question.keys and len(question.keys) > 1
    current_keys = list(question.keys) if is_multi else [question.key]
    old_key = current_keys[key_index] if key_index < len(current_keys) else current_keys[0]

    prompt = f"""Rewrite ONE correct answer for this certification exam question.
The stem, distractors, and all other keys must remain EXACTLY the same.

**Stem (DO NOT CHANGE):** {question.stem}
**Key source text:** {question.key_source_text}
**Current correct answer to replace:** {json.dumps(old_key)}
**Other keys to keep (DO NOT CHANGE):** {json.dumps([k for i, k in enumerate(current_keys) if i != key_index])}
**Distractors (DO NOT CHANGE):** {json.dumps(question.distractors)}

RULES:
- The new key MUST still be factually correct based on the key_source_text.
- It must be a different wording or angle, not identical to the old key.
- It must be similar in length to the distractors.
- Update the explanation to reflect the new wording.

Return ONLY a JSON object:
```json
{{"key": "new correct answer text", "explanation": "A: ... B: ... C: ... D: ..."}}
```"""

    try:
        response = providers.generate(
            prompt=prompt, model=model,
            system=system_prompt or GENERATION_SYSTEM_PROMPT,
            base_url=base_url, timeout=120.0,
        )
    except Exception as e:
        print(f"[REGEN-KEY] AI call failed: {e}")
        return None

    data = _extract_json_object(response)
    if not data or "key" not in data:
        return None

    new_key = data["key"]
    if is_multi:
        question.keys[key_index] = new_key
        if key_index == 0:
            question.key = new_key
    else:
        question.key = new_key

    if "explanation" in data:
        question.explanation = data["explanation"]

    return new_key


def regen_distractor(
    question: Question,
    distractor_index: int,
    model: str,
    base_url: str = "http://localhost:11434",
    system_prompt: str = "",
) -> Optional[str]:
    """Regenerate a single distractor — stem and keys stay locked."""
    old_dist = question.distractors[distractor_index] if distractor_index < len(question.distractors) else ""
    is_multi = question.question_type == "multi" and question.keys and len(question.keys) > 1
    keys_json = json.dumps(question.keys) if is_multi else json.dumps([question.key])

    other_distractors = [d for i, d in enumerate(question.distractors) if i != distractor_index]

    prompt = f"""Write ONE new distractor (wrong answer) for this certification exam question.
The stem, correct answer(s), and other distractors must remain EXACTLY the same.

**Stem (DO NOT CHANGE):** {question.stem}
**{"Keys" if is_multi else "Key"} (DO NOT CHANGE):** {keys_json}
**Distractor to REPLACE:** {json.dumps(old_dist)}
**Other distractors to keep (DO NOT CHANGE):** {json.dumps(other_distractors)}
**Key source text:** {question.key_source_text}

RULES:
- The new distractor must be plausible but clearly WRONG.
- It must NOT duplicate any existing key or distractor.
- It must be similar in length to the correct answer(s).
- It should be a common misconception or partial truth related to the topic.
- Update the explanation to address the new distractor by letter.

Return ONLY a JSON object:
```json
{{"distractor": "new wrong answer text", "explanation": "A: ... B: ... C: ... D: ..."}}
```"""

    try:
        response = providers.generate(
            prompt=prompt, model=model,
            system=system_prompt or GENERATION_SYSTEM_PROMPT,
            base_url=base_url, timeout=120.0,
        )
    except Exception as e:
        print(f"[REGEN-DIST] AI call failed: {e}")
        return None

    data = _extract_json_object(response)
    if not data or "distractor" not in data:
        return None

    question.distractors[distractor_index] = data["distractor"]
    if "explanation" in data:
        question.explanation = data["explanation"]

    return data["distractor"]


def improve_question(
    question: Question,
    model: str,
    base_url: str = "http://localhost:11434",
    instruction: str = "Improve this question following certification exam best practices.",
    system_prompt: str = "",
) -> Optional[Question]:
    """Use AI to improve an existing question."""
    is_multi = question.question_type == "multi" and question.keys and len(question.keys) > 1
    keys_str = json.dumps(question.keys) if is_multi else json.dumps(question.key)

    prompt = f"""{instruction}

Current question:
- Scenario: {question.scenario}
- Stem: {question.stem}
- Question Type: {question.question_type}
- {"Keys" if is_multi else "Key"}: {keys_str}
- Key Source Text: {question.key_source_text}
- Distractors: {json.dumps(question.distractors)}
- Explanation: {question.explanation}

IMPORTANT:
- Keep the key answer(s) grounded in the original slide content.
- The key_source_text must still reference the original source material.
- ALL choices (keys + distractors) must be similar in length and detail.
- The explanation MUST address each choice by its text content (NOT by letter A/B/C/D, since choices are shuffled).
- For multi-select: stem must end with "(Choose N.)"

Return ONLY a JSON object with these keys:
```json
{{
  "scenario": "...",
  "stem": "...?",
  {"'keys': ['...', '...']," if is_multi else "'key': '...',"}
  "key_source_text": "...",
  "distractors": ["...", "..."],
  "explanation": "'choice text' — Correct/Incorrect: <reason>. 'next choice' — ..."
}}
```"""

    response = providers.generate(
        prompt=prompt,
        model=model,
        system=system_prompt or GENERATION_SYSTEM_PROMPT,
        base_url=base_url,
        timeout=120.0,
    )

    fence_match = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", response, re.DOTALL)
    text = fence_match.group(1) if fence_match else response

    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1:
        return None

    try:
        data = json.loads(text[start:end + 1])
        question.scenario = data.get("scenario", question.scenario)
        question.stem = data.get("stem", question.stem)
        if is_multi and "keys" in data:
            question.keys = data["keys"]
            question.key = data["keys"][0] if data["keys"] else question.key
        elif "key" in data:
            question.key = data["key"]
        question.key_source_text = data.get("key_source_text", question.key_source_text)
        question.distractors = data.get("distractors", question.distractors)
        question.explanation = data.get("explanation", question.explanation)
        return question
    except json.JSONDecodeError:
        return None


def qa_check_question(
    question: Question,
    model: str,
    base_url: str = "http://localhost:11434",
) -> List[dict]:
    """Run an AI QA check on a question for spelling, grammar, clarity, and exam best practices.

    Returns a list of issues: [{"field": "stem", "issue": "...", "severity": "error|warning"}]
    """
    is_multi = question.question_type == "multi" and question.keys and len(question.keys) > 1
    keys_str = json.dumps(question.keys) if is_multi else json.dumps(question.key)

    prompt = f"""You are a proofreader for certification exam questions.
Your ONLY job is to find spelling, grammar, and syntax errors.

Check each field below for:
- **Spelling**: misspelled words, typos, incorrect technical terms
- **Grammar**: subject-verb agreement, tense consistency, missing/extra articles, wrong prepositions
- **Syntax**: missing punctuation, extra spaces, broken sentences, mismatched quotes/brackets
- **Stem format**: must end with "?"

Do NOT flag style preferences, question design, answer quality, or exam best practices.
Do NOT suggest rewording for "clarity" unless the sentence is genuinely broken.

Question to review:
- Scenario: {question.scenario or "(none)"}
- Stem: {question.stem}
- {"Keys" if is_multi else "Key"}: {keys_str}
- Distractors: {json.dumps(question.distractors)}

Return ONLY a JSON array of issues. Each issue:
- "field": exactly one of "scenario", "stem", "key", "distractor"
- "value": the exact text containing the error (the specific choice or sentence)
- "issue": the error and suggested correction
- "severity": "error" for spelling/grammar mistakes, "warning" for punctuation/formatting

If the question has no errors, return: []

```json
[{{"field": "stem", "value": "Which optons describe...", "issue": "'optons' should be 'options'", "severity": "error"}}]
```"""

    response = providers.generate(
        prompt=prompt,
        model=model,
        system="You are a meticulous QA reviewer. Return ONLY valid JSON.",
        base_url=base_url,
        timeout=90.0,
    )

    parsed = _extract_json_array(response)
    if parsed is None:
        fence_match = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", response, re.DOTALL)
        if fence_match:
            try:
                parsed = json.loads(fence_match.group(1))
            except json.JSONDecodeError:
                pass

    if not isinstance(parsed, list):
        return [{"field": "general", "issue": "QA check failed — could not parse AI response", "severity": "warning"}]

    issues = []
    for item in parsed:
        if isinstance(item, dict) and "issue" in item:
            issues.append({
                "field": item.get("field", "general"),
                "issue": item["issue"],
                "severity": item.get("severity", "warning"),
            })
    return issues


def qa_fix_question(
    question: Question,
    issues: List[dict],
    model: str,
    base_url: str = "http://localhost:11434",
    system_prompt: str = "",
) -> Optional[Question]:
    """Auto-fix a question based on QA issues. Returns the fixed question or None on failure.

    Uses the QA issues as specific instructions for what to fix.
    """
    if not issues:
        return question

    is_multi = question.question_type == "multi" and question.keys and len(question.keys) > 1
    keys_str = json.dumps(question.keys) if is_multi else json.dumps(question.key)

    # Format issues as fix instructions
    fix_instructions = []
    for issue in issues:
        field = issue.get("field", "general")
        desc = issue.get("issue", "")
        severity = issue.get("severity", "warning")
        fix_instructions.append(f"- [{severity.upper()}] {field}: {desc}")
    fixes_text = "\n".join(fix_instructions)

    prompt = f"""Fix the following certification exam question based on the QA issues found.

Current question:
- Scenario: {question.scenario}
- Stem: {question.stem}
- Question Type: {question.question_type}
- {"Keys" if is_multi else "Key"}: {keys_str}
- Key Source Text: {question.key_source_text}
- Distractors: {json.dumps(question.distractors)}
- Explanation: {question.explanation}

QA ISSUES TO FIX:
{fixes_text}

INSTRUCTIONS:
- Fix ALL the issues listed above.
- Keep the key answer(s) grounded in the original source material.
- The key_source_text must still reference the original source material.
- ALL choices (keys + distractors) must be similar in length and detail.
- The explanation MUST address each choice by its actual text content (NOT by letter A/B/C/D).
  Format: "'choice text' — Correct/Incorrect: <reason>." for each key and distractor.
- For multi-select: stem must end with "(Choose N.)"
- NEVER mention slides, speaker notes, or source material.

Return ONLY a JSON object with these keys:
```json
{{
  "scenario": "...",
  "stem": "...?",
  {"'keys': ['...', '...']," if is_multi else "'key': '...',"}
  "key_source_text": "...",
  "distractors": ["...", "..."],
  "explanation": "'choice text' — Correct: <reason>. 'choice text' — Incorrect: <reason>. ..."
}}
```"""

    response = providers.generate(
        prompt=prompt,
        model=model,
        system=system_prompt or GENERATION_SYSTEM_PROMPT,
        base_url=base_url,
        timeout=120.0,
    )

    fence_match = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", response, re.DOTALL)
    text = fence_match.group(1) if fence_match else response

    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1:
        return None

    try:
        data = json.loads(text[start:end + 1])
        question.scenario = data.get("scenario", question.scenario)
        question.stem = data.get("stem", question.stem)
        if is_multi and "keys" in data:
            question.keys = data["keys"]
            question.key = data["keys"][0] if data["keys"] else question.key
        elif "key" in data:
            question.key = data["key"]
        question.key_source_text = data.get("key_source_text", question.key_source_text)
        question.distractors = data.get("distractors", question.distractors)
        question.explanation = data.get("explanation", question.explanation)
        return question
    except json.JSONDecodeError:
        return None


def generate_explanation(
    question: Question,
    speaker_notes: str,
    model: str,
    base_url: str = "http://localhost:11434",
) -> str:
    """Generate an explanation for why the correct answer(s) are correct, citing speaker notes.

    Returns the explanation text, or empty string on failure.
    """
    is_multi = question.question_type == "multi" and question.keys and len(question.keys) > 1
    keys_str = json.dumps(question.keys) if is_multi else json.dumps(question.key)

    prompt = f"""Based on the speaker notes below, explain why the correct answer(s) are correct
and why each distractor is incorrect. Reference specific facts from the notes.

Speaker Notes:
{speaker_notes}

Question: {question.stem}
{"Keys" if is_multi else "Key"}: {keys_str}
Distractors: {json.dumps(question.distractors)}

Write ONE LINE PER OPTION. Each line must follow this exact format:
'option text' — Correct: reason citing notes.
'option text' — Incorrect: reason citing notes.

Put each option on its OWN LINE (separated by newlines). Use the exact option text in single quotes.
Every option (both keys and distractors) must have its own line.

Return ONLY the explanation text, no JSON wrapping."""

    try:
        response = providers.generate(
            prompt=prompt,
            model=model,
            system="You are an exam question reviewer. Write concise, factual explanations citing the source notes.",
            base_url=base_url,
            timeout=60.0,
        )
        return response.strip() if response else ""
    except Exception:
        return ""


def ai_assign_keys(
    question: Question,
    speaker_notes: str,
    model: str,
    base_url: str = "http://localhost:11434",
    slide_image: str = "",
) -> bool:
    """Use AI to determine which options are correct answers vs distractors.

    Sends all options + speaker notes (+ optional slide image) to Ollama.
    The AI identifies which options are supported by the source material.
    Mutates the question in-place: sets key/keys, distractors, key_source_text,
    explanation, and removes the key-unverified tag.

    Returns True if keys were successfully assigned, False otherwise.
    """
    all_options = list(question.distractors)  # all options are in distractors for unverified
    if question.key:
        all_options = [question.key] + [d for d in all_options if d != question.key]
    if not all_options or not speaker_notes.strip():
        return False

    # Detect expected number of correct answers from stem
    num_expected = 1
    choose_match = re.search(
        r'(?:Choose|Select)\s+(two|three|four|five|\d+)',
        question.stem, re.IGNORECASE,
    )
    if choose_match:
        word_map = {"two": 2, "three": 3, "four": 4, "five": 5}
        val = choose_match.group(1).lower()
        num_expected = word_map.get(val, int(val) if val.isdigit() else 1)

    # Build lettered option list
    options_text = "\n".join(
        f"{string.ascii_uppercase[i]}: {opt}"
        for i, opt in enumerate(all_options)
        if i < 26
    )

    prompt = f"""Based ONLY on the source material below, determine which answer options are correct.

**Source Material (Speaker Notes):**
{speaker_notes}

**Question:** {question.stem}

**Options:**
{options_text}

The question expects EXACTLY {num_expected} correct answer(s).

STEP 1: For EACH option ({', '.join(string.ascii_uppercase[i] for i in range(min(len(all_options), 26)))}), \
quote the specific sentence from the source material that supports or contradicts it.
If no supporting quote exists, the option is a distractor (incorrect).

STEP 2: Based on your analysis, select EXACTLY {num_expected} option(s) that are DIRECTLY supported \
by the source material. Count carefully — you must pick exactly {num_expected}.

Return ONLY a JSON object with these exact keys:
```json
{{
  "analysis": {{
    "A": {{"quote": "exact quote or 'no supporting quote found'", "supported": true/false}},
    "B": {{"quote": "...", "supported": true/false}}
  }},
  "correct_letters": ["A", "C"],
  "key_source_text": "exact quote from source material supporting the correct answer(s)",
  "explanation": "'option text' — Correct: reason citing source.\\n'option text' — Incorrect: reason."
}}
```

CRITICAL RULES:
- "correct_letters" must contain EXACTLY {num_expected} letter(s) — no more, no fewer
- Only options with direct quotes from the source material can be correct
- "key_source_text" must be an EXACT quote from the source material
- Explanation must address EVERY option on its own line, stating Correct or Incorrect with reasoning
- Each line of the explanation should start with the option text in single quotes"""

    images = [slide_image] if slide_image else None
    try:
        response = providers.generate(
            prompt=prompt,
            model=model,
            system="You are a certification exam validator. Identify correct answers based strictly on the source material provided.",
            base_url=base_url,
            timeout=120.0,
            images=images,
        )
    except Exception:
        return False

    # Parse response
    fence_match = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", response, re.DOTALL)
    text = fence_match.group(1) if fence_match else response
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1:
        return False

    try:
        data = json.loads(text[start:end + 1])
    except json.JSONDecodeError:
        return False

    correct_letters = data.get("correct_letters", [])
    if not correct_letters or not isinstance(correct_letters, list):
        return False

    # Map letters back to option text
    new_keys = []
    new_distractors = []
    for i, opt in enumerate(all_options):
        letter = string.ascii_uppercase[i] if i < 26 else ""
        if letter in correct_letters:
            new_keys.append(opt)
        else:
            new_distractors.append(opt)

    if not new_keys:
        return False

    # Assign to question
    question.key = new_keys[0]
    if len(new_keys) > 1:
        question.keys = new_keys
        question.question_type = "multi"
    else:
        question.keys = []
        question.question_type = "single"
    question.distractors = new_distractors

    if data.get("key_source_text"):
        question.key_source_text = data["key_source_text"]
    # Do NOT save the AI explanation here — it is often inconsistent with
    # correct_letters.  Let the separate "Generate Explanations" step create
    # the explanation using the already-corrected key assignments.

    # Remove unverified tag
    question.tags = [t for t in question.tags if t != "key-unverified"]
    return True
