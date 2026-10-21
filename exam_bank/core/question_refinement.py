"""The AI operations the editor offers on a saved question.

Every one of them PROPOSES: it returns a rewrite, findings, an explanation or
an answer key, and never changes the Question it is given. The author takes a
proposal into the editor and saves it, or does not.

- improve_question: the AI rewrite;
- review_answers and qa_check_question: the AI answer check;
- generate_explanation: the AI explanation;
- ai_assign_keys: the AI answer key - which options are correct, for a
  question whose answer was guessed at import.

Four more came across from the NiceGUI app and were never reachable from any
screen: regen_stem, regen_key and regen_distractor (the AI rewrite covers
them) and qa_fix_question. They were deleted in 1.9.0.
"""

import copy as _copy
import json
import re
import string
from typing import List, Optional

from . import providers
from .bank import Question
from .generation_prompts import (
    ANSWER_RULES,
    EXPLANATION_REWRITE_RULES,
    EXPLANATION_RULES,
    GENERATION_SYSTEM_PROMPT,
    PROOFREAD_RULES,
    REWRITE_CHECK_RULES,
    REWRITE_SYSTEM_PROMPT,
    SCENARIO_AND_STEM_RULES,
    WRITING_RULES,
)
from .rewrite_checks import keep_capitals
from .writing_style import tidy, tidy_question

# The rewrite's default ask. The bulk rewrite sends the same one, so a
# question rewritten on its own and one rewritten with its exam come back alike.
#
# A polish, not a re-author (1.14.0): the bank's questions have been through
# review, so the rewrite proofreads them and brings the explanation to the
# house rule, and leaves the rest as it found it. It used to say "Improve this
# question", and a model told to improve rewrites.
#
# 1.18.0: "keep every detail of ... the answers" kept answers that had been cut
# short, so a cut answer is now named as something to fix.
#
# 1.18.1: "rewrite the explanation" re-authored explanations that were already
# right - the gated re-run lost facts and added padding to them - so one that
# meets the rule is now kept.
REWRITE_INSTRUCTION = (
    "Polish this reviewed certification exam question. Proofread every field as an "
    "exacting copy editor, complete any answer that is cut short, and bring the "
    "explanation to the house rule: keep one that already explains only why the "
    "correct answer is right, and rewrite one that does not. Keep every detail of "
    "the scenario and the question, and what every answer claims. Change nothing else."
)
from .generation_parsing import _extract_json_array, _extract_json_object
from .stem_text import question_only


def improve_question(
    question: Question,
    model: str,
    base_url: str = "http://localhost:11434",
    instruction: str = REWRITE_INSTRUCTION,
    system_prompt: str = "",
) -> Optional[Question]:
    """Use AI to improve an existing question: proofread it, and rewrite the
    explanation to the house rule (the correct answer only, in paragraphs,
    key terms in bold)."""
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
- Return key_source_text unchanged.

Apply these rules in this order. Every one of them is checked before the
question can be approved.

1. What to keep, and what to fix:
{PROOFREAD_RULES}

2. The scenario and the question do different jobs - keep them apart. If the
current scenario asks a question, or the current stem opens with statements,
move the statements into the scenario and leave only the question in the stem:
{SCENARIO_AND_STEM_RULES}

3. The answers:
{ANSWER_RULES}

4. The explanation:
{EXPLANATION_RULES}
{EXPLANATION_REWRITE_RULES if (question.explanation or "").strip() else ""}

5. The writing standard - quotes, names and punctuation, in every field:
{WRITING_RULES}

Return ONLY a JSON object with these keys:
```json
{{
  "scenario": "...",
  "stem": "...?",
  {"'keys': ['...', '...']," if is_multi else "'key': '...',"}
  "key_source_text": "...",
  "distractors": ["...", "..."],
  "explanation": "Why the correct answer is right, with the **key term** in bold.\\n\\nA second short paragraph if it helps."
}}
```"""

    response = providers.generate(
        prompt=prompt,
        model=model,
        system=system_prompt or REWRITE_SYSTEM_PROMPT,
        base_url=base_url,
        timeout=120.0,
    )

    # The shared extractor: an explanation may now hold a code block, whose
    # fences sit inside the JSON (generation_parsing).
    data = _extract_json_object(response)
    if data is None:
        return None

    # A COPY. This used to assign straight onto the argument, so calling it
    # handed the model's output to whoever held that Question - and anything
    # that saved afterwards persisted an AI rewrite nobody had accepted. The
    # caller decides what to keep; this function only proposes.
    proposed = _copy.deepcopy(question)
    proposed.scenario = data.get("scenario", proposed.scenario)
    proposed.stem = question_only(data.get("stem", proposed.stem))
    if is_multi and "keys" in data:
        proposed.keys = data["keys"]
        proposed.key = data["keys"][0] if data["keys"] else proposed.key
    elif "key" in data:
        proposed.key = data["key"]
    proposed.key_source_text = data.get("key_source_text", proposed.key_source_text)
    proposed.distractors = data.get("distractors", proposed.distractors)
    proposed.explanation = data.get("explanation", proposed.explanation)
    proposed.option_order = _carry_order(question, proposed)
    # What the model missed of the writing standard's mechanical rules, and
    # any capital it took off an answer (rewrite_checks).
    return keep_capitals(question, tidy_question(proposed))


def _carry_order(question: Question, proposed: Question) -> list[str]:
    """The order the learner sees now, in the proposal's words.

    The model rewords answers in place - the key stays the key, the second
    distractor the second - so each answer keeps its position under its new
    wording. Without this the stored order named the old wording, and once
    every answer was reworded the correct one was shown first (1.15.0).
    """
    if not question.option_order:
        # No recorded order: the exports scatter the answers by the id
        # (exporter.stable_option_order). Recording the key-first list here
        # would put the correct answer first.
        return []
    old = question.correct_answers + list(question.distractors)
    new = proposed.correct_answers + list(proposed.distractors)
    if len(old) != len(new) or len(set(new)) != len(new):
        return []        # options added or merged: no position to keep
    reworded = dict(zip(old, new))
    order = [reworded.get(text, text) for text in question.all_choices]
    return order if sorted(order) == sorted(new) else []


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


def _options(question: Question) -> list[str]:
    """Every option once, in the order the author sees them where known."""
    keys = question.keys if question.question_type == "multi" and question.keys else [question.key]
    combined = []
    for o in [*keys, *question.distractors]:
        if o and o not in combined:
            combined.append(o)
    order = [o for o in (question.option_order or []) if o]
    if order and sorted(set(order)) == sorted(combined):
        return list(dict.fromkeys(order))
    return combined


def _grounding_block(source_text: str) -> str:
    if source_text.strip():
        return ("Course material the question was written from:\n"
                f"{source_text.strip()}\n\n"
                "Use only facts this material states, or that follow directly from it.")
    return ("No course material is available for this question. Use only facts about "
            "Pentaho that you are certain of; say less rather than guess.")


def generate_explanation(
    question: Question,
    model: str,
    base_url: str = "http://localhost:11434",
    source_text: str = "",
) -> str:
    """Propose the explanation: why the correct answer(s) are right, and
    nothing about the wrong options (EXPLANATION_RULES: paragraphs, the key
    terms in bold). Returns "" on failure. Writes nothing: the caller shows
    it, and the author decides.
    """
    keys = question.keys if question.question_type == "multi" and question.keys else [question.key]
    keys = [k for k in keys if k]
    if not keys:
        return ""
    # The wrong options are listed so the model knows what the candidate was
    # choosing between, not to be discussed.
    lines = [f"- {k} (correct)" for k in keys] + \
            [f"- {d} (incorrect - do not discuss)" for d in question.distractors if d and d not in keys]
    prompt = f"""Write the explanation for this certification exam question. Candidates read it after the exam.

{_grounding_block(source_text)}

Scenario: {question.scenario.strip() or "(none)"}
Question: {question.stem.strip()}
Options:
{chr(10).join(lines)}

Rules:
{EXPLANATION_RULES}
- Correct spelling and grammar, and sentences that read smoothly.
- Do not mention a course, a workshop, a lab or "the material": state the facts.
{WRITING_RULES}

Return only the explanation text, with a blank line between paragraphs."""
    try:
        response = providers.generate(
            prompt=prompt,
            model=model,
            system=("You write explanations for Pentaho certification exam questions: "
                    "accurate, concise, and about the correct answer only."),
            base_url=base_url,
            timeout=90.0,
        )
    except Exception:
        return ""
    text = (response or "").strip()
    fence = re.match(r"^```\w*\s*\n(.*?)\n?```$", text, re.DOTALL)
    if fence:
        text = fence.group(1).strip()
    if len(text) > 1 and text[0] == text[-1] == '"':
        text = text[1:-1].strip()
    return tidy(text)


_COUNT_WORDS = {"two": 2, "three": 3, "four": 4, "five": 5}


def _question_block(q: Question) -> str:
    keys = q.correct_answers
    lines = [f"Scenario: {q.scenario.strip() or '(none)'}", f"Question: {q.stem.strip()}", "Answers:"]
    lines += [f"- {k} (marked correct)" for k in keys]
    lines += [f"- {d} (marked wrong)" for d in q.distractors if d and d not in keys]
    lines.append(f"Explanation: {q.explanation.strip() or '(none)'}")
    return "\n".join(lines)


# The second pass over a rewrite (1.17.0). The owner, after the first two
# exams: "it must check at a deeper level the grammar, spelling, readability,
# punctuation, and that the answer(s) and explanation are correct". One model
# call, separate from the one that wrote the rewrite - a writer reviewing its
# own text in the same breath finds little - grounded on the course pages when
# there are any. It reports; it never edits. An unreadable reply is itself a
# finding, so an unchecked rewrite can never pass as a clean one.
CHECK_FAILED = "The answer and language check did not run, so read this one closely."


def check_rewrite(
    original: Optional[Question],
    proposed: Question,
    model: str,
    base_url: str = "http://localhost:11434",
    source_text: str = "",
) -> List[tuple]:
    """(field, message) findings on a question; [] when it is clean.

    With an ``original`` it checks a rewrite against it (the bulk rewrite,
    1.17.0). Without one it checks the question as it stands (1.18.0): the
    gate a hand-edited question passes before it is approved, the same rules
    less "nothing lost or added", which needs something to compare with."""
    rules = REWRITE_CHECK_RULES
    if original is None:
        rules = _drop_rule(REWRITE_CHECK_RULES, "The rewrite lost")
        what = "a certification exam question before it is approved"
        body = f"QUESTION (to check):\n{_question_block(proposed)}\n\nCheck the QUESTION:"
        compare = ""
    else:
        what = "a rewritten certification exam question before it is accepted"
        body = (f"ORIGINAL (reviewed and approved):\n{_question_block(original)}\n\n"
                f"REWRITE (to check):\n{_question_block(proposed)}\n\nCheck the REWRITE:")
        compare = (
            '\n  "lost": [],\n  "added": [],')
    prompt = f"""You review {what}.

{_grounding_block(source_text)}

{body}
{rules}

Report only real problems, each with the exact words concerned. Do not report
style preferences. Do not rewrite anything.

Return ONLY a JSON object:
{{
  "answer_correct": true,
  "answer_problem": "",
  "also_correct": [],
  "explanation_correct": true,
  "explanation_problem": "",{compare}
  "incomplete_answers": [],
  "answer_stands_out": "",
  "language": [{{"field": "scenario|question|answers|explanation", "text": "...", "fix": "..."}}]
}}
"also_correct" lists answers marked wrong that are also correct. "incomplete_answers"
lists, word for word, any answer that is cut short, missing a word it needs, or hard to
read on its own. "answer_stands_out" says how the correct answer stands out from the
wrong ones - by length, detail, wording or form - or is empty.""" + ("" if original is None else """
"lost" lists facts, conditions or caveats of the ORIGINAL missing from the REWRITE - but
NOT what the original explanation said about the wrong answers: the rewrite drops that
on purpose. "added" lists claims in the REWRITE that the ORIGINAL does not make.""") + """
Empty lists and strings when there is nothing."""
    try:
        reply = providers.generate(
            prompt=prompt,
            model=model,
            system=("You are a meticulous technical editor and Pentaho subject matter expert. "
                    "Return ONLY valid JSON."),
            base_url=base_url,
            timeout=120.0,
        )
    except Exception:
        return [("explanation", CHECK_FAILED)]
    data = _extract_json_object(reply or "")
    if not isinstance(data, dict) or "answer_correct" not in data:
        return [("explanation", CHECK_FAILED)]

    def words(x) -> str:
        return str(x).strip()

    found: List[tuple] = []
    if data.get("answer_correct") is False:
        found.append(("options", "The check doubts the answer marked correct: "
                      + (words(data.get("answer_problem")) or "no reason given") + "."))
    for a in data.get("also_correct") or []:
        if words(a):
            found.append(("options", f"The check says this wrong answer may also be correct: {words(a)}"))
    if data.get("explanation_correct") is False:
        found.append(("explanation", "The check doubts the explanation: "
                      + (words(data.get("explanation_problem")) or "no reason given") + "."))
    if original is not None:
        for x in data.get("lost") or []:
            if words(x):
                found.append(("explanation", f"The rewrite may have lost: {words(x)}"))
        for x in data.get("added") or []:
            if words(x):
                found.append(("explanation", f"The rewrite may have added: {words(x)}"))
    for a in data.get("incomplete_answers") or []:
        if words(a):
            found.append(("options", f"The check says this answer is cut short or unclear: {words(a)}"))
    if words(data.get("answer_stands_out") or ""):
        found.append(("options", "The check says the correct answer stands out: "
                      + words(data.get("answer_stands_out")) + "."))
    fields = {"scenario": "scenario", "question": "stem", "answers": "options", "explanation": "explanation"}
    for item in data.get("language") or []:
        if isinstance(item, dict) and words(item.get("text", "")):
            fix = words(item.get("fix", ""))
            found.append((fields.get(str(item.get("field", "")).lower(), "explanation"),
                          f"Language: \"{words(item['text'])}\"" + (f" -> \"{fix}\"" if fix else "")))
    return found


def _drop_rule(rules: str, opening: str) -> str:
    """A bullet list of rules, less the bullet that starts with `opening`."""
    bullets = [b for b in rules.split("\n- ")]
    bullets[0] = bullets[0][2:] if bullets[0].startswith("- ") else bullets[0]
    return "\n".join("- " + b for b in bullets if not b.startswith(opening))


def expected_key_count(question: Question) -> int:
    """How many correct answers the question asks for.

    The house form says so in the question - "Which two ...?" - and older
    stems in a directive - "(Choose two)". Failing both, a multi-select
    question keeps the count it has (at least two), a single-select one.
    """
    stem = question.stem or ""
    m = re.search(r"\bwhich\s+(two|three|four|five)\b", stem, re.IGNORECASE) or \
        re.search(r"(?:choose|select|pick)\s+(two|three|four|five|\d+)", stem, re.IGNORECASE)
    if m:
        word = m.group(1).lower()
        return _COUNT_WORDS.get(word) or int(word)
    if question.question_type == "multi":
        return max(2, len([k for k in question.keys if k]))
    return 1


def ai_assign_keys(
    question: Question,
    model: str,
    base_url: str = "http://localhost:11434",
    source_text: str = "",
    expected: int = 0,
) -> Optional[dict]:
    """Propose which options are correct - for a question whose answer was
    guessed at import (a plain-text file marks none, so the first option is
    taken and the question tagged ``key-unverified``).

    Returns ``{"keys", "distractors", "keySourceText", "analysis"}``, the
    options by their text, or None when the model's answer is unusable -
    including when it picks a different number of answers than the question
    asks for. Writes nothing: until 1.9.0 this assigned the answer straight
    onto the question it was given.
    """
    options = _options(question)
    if len(options) < 2 or len(options) > 26:
        return None
    n = expected or expected_key_count(question)
    letters = string.ascii_uppercase[:len(options)]
    listed = "\n".join(f"{letters[i]}: {o}" for i, o in enumerate(options))

    prompt = f"""Decide which answer options to this certification exam question are correct.

{_grounding_block(source_text)}

Scenario: {question.scenario.strip() or "(none)"}
Question: {question.stem.strip()}

Options:
{listed}

The question has EXACTLY {n} correct answer(s).

STEP 1: For each option ({", ".join(letters)}), quote the sentence that supports or contradicts it; if there is none, say so.
STEP 2: Select EXACTLY {n} option(s) that are correct.

Return ONLY a JSON object:
{{
  "analysis": {{"A": {{"quote": "the supporting or contradicting sentence, or 'none'", "supported": true}}}},
  "correct_letters": ["A"],
  "key_source_text": "the sentence that best supports the correct answer(s)"
}}"""
    try:
        response = providers.generate(
            prompt=prompt,
            model=model,
            system=("You are a certification exam validator. Decide the correct answers "
                    "strictly from the material given."),
            base_url=base_url,
            timeout=120.0,
        )
    except Exception:
        return None

    fence = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", response or "", re.DOTALL)
    text = fence.group(1) if fence else (response or "")
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end <= start:
        return None
    try:
        data = json.loads(text[start:end + 1])
    except json.JSONDecodeError:
        return None
    chosen = data.get("correct_letters")
    if not isinstance(chosen, list):
        return None
    chosen = {str(c).strip().upper() for c in chosen}
    keys = [o for i, o in enumerate(options) if letters[i] in chosen]
    if len(keys) != n:
        return None

    analysis = data.get("analysis") if isinstance(data.get("analysis"), dict) else {}
    return {
        "keys": keys,
        "distractors": [o for o in options if o not in keys],
        "keySourceText": str(data.get("key_source_text") or "").strip(),
        "analysis": [
            {
                "option": o,
                "correct": o in keys,
                "quote": str((analysis.get(letters[i]) or {}).get("quote") or "").strip()
                if isinstance(analysis.get(letters[i]), dict) else "",
            }
            for i, o in enumerate(options)
        ],
    }


#: What `review_answers` is allowed to say about a field.
ANSWER_REVIEW_FIELDS = ("key", "distractor", "options", "stem")


def review_answers(
    question: Question,
    model: str,
    base_url: str = "http://localhost:11434",
) -> List[dict]:
    """Judge the ANSWERS: is the key right, and are the distractors wrong?

    `qa_check_question` is a proofreader and says so in its own prompt - "Do
    NOT flag ... answer quality". Nothing checked whether the question is
    actually answerable as written, which is the failure that reached
    production: `analyst-ba-practitioner/ir-q9` listed four output formats
    and marked all four correct, so it could not be got wrong, and no
    automated check noticed for as long as it shipped.

    Returns [{"field", "value", "issue", "severity"}], severity "error" for
    something that makes the question wrong or unanswerable and "warning" for
    something that weakens it. An empty list means the reviewer found
    nothing - NOT that the question is certified correct. It is a second
    opinion from a model, and the author decides.
    """
    is_multi = question.question_type == "multi" and question.keys and len(question.keys) > 1
    keys = list(question.keys) if is_multi else [question.key]

    prompt = f"""You are reviewing whether a certification exam question can be
answered correctly as written. Judge the ANSWERS, not the prose.

Look for, in this order:
- **A key that is wrong**: the marked answer is not actually correct.
- **A distractor that is also correct**: it would have to be accepted too, so
  the question has more than one right answer.
- **No real distractors**: every option is correct, or the options are
  restatements of each other, so the question cannot be got wrong.
- **A giveaway**: the key is the only long/specific/grammatically-agreeing
  option, so it can be picked without knowing the subject.
- **Overlapping options**: two choices that cannot be told apart.
- **An unanswerable stem**: the stem does not determine a single answer.

Question:
- Scenario: {question.scenario or "(none)"}
- Stem: {question.stem}
- {"Keys (all marked correct)" if is_multi else "Key (marked correct)"}: {json.dumps(keys)}
- Distractors (marked incorrect): {json.dumps(question.distractors)}
- Explanation: {question.explanation or "(none)"}

Report only what is WRONG. Do not restate what is fine, and do not comment on
spelling, grammar or style - a separate proofreader does that.

Return ONLY a JSON array. Each entry:
- "field": one of "key", "distractor", "options", "stem"
- "value": the exact text at fault, or "" when it is about the set as a whole
- "issue": what is wrong and what would fix it
- "severity": "error" if the question is wrong or unanswerable, else "warning"

Return [] if you find nothing.
"""

    response = providers.generate(
        prompt=prompt,
        model=model,
        system=system_prompt_for_review(),
        base_url=base_url,
        timeout=120.0,
    )

    items = _extract_json_array(response)
    if not isinstance(items, list):
        return []

    out: List[dict] = []
    for raw in items:
        if not isinstance(raw, dict):
            continue
        field = str(raw.get("field", "")).strip().lower()
        severity = str(raw.get("severity", "")).strip().lower()
        issue = str(raw.get("issue", "")).strip()
        if not issue:
            continue
        out.append({
            # An unrecognised field is reported against the set rather than
            # dropped: the finding may still be worth reading, and silently
            # discarding a model's answer is how a reviewer stops being one.
            "field": field if field in ANSWER_REVIEW_FIELDS else "options",
            "value": str(raw.get("value", "")),
            "issue": issue,
            "severity": "error" if severity == "error" else "warning",
        })
    return out


def system_prompt_for_review() -> str:
    return (
        "You review certification exam questions for correctness. You are "
        "terse, you only report faults, and you never invent a fault to have "
        "something to say. An empty array is a valid and common answer."
    )
