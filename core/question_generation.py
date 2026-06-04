"""Core question generation pipeline using Ollama AI."""

import json
import re
from typing import List, Optional

from . import ollama_client
from .question_bank import Question
from .pptx_reader import SlideInfo
from .generation_prompts import (
    GENERATION_SYSTEM_PROMPT, _build_question_specs, build_prompt, _num_word,
)
from .generation_parsing import _extract_json_array, _extract_json_object, validate_key_against_notes


# Warnings that the AI can fix by rewriting the question
_FIXABLE_WARNINGS = {
    "Answer lengths are unbalanced",
    "A distractor is identical to a correct answer",
    "'All/None of the above' is a weak distractor",
}


def _get_fixable_warnings(q: Question) -> List[str]:
    """Return only the warnings that can be auto-fixed by AI rewrite."""
    warnings = q.validate()
    return [w for w in warnings if any(fw in w for fw in _FIXABLE_WARNINGS)]


def _auto_fix_question(
    question: Question,
    warnings: List[str],
    model: str,
    base_url: str = "http://localhost:11434",
    system_prompt: str = "",
) -> Optional[Question]:
    """Fix only the choices (key/distractors) and explanation — nothing else.

    The stem, scenario, key_source_text, and all metadata stay untouched.
    Only retries once to avoid infinite loops.
    """
    is_multi = question.question_type == "multi" and question.keys and len(question.keys) > 1
    keys_json = json.dumps(question.keys) if is_multi else json.dumps([question.key])
    warning_list = "\n".join(f"- {w}" for w in warnings)

    prompt = f"""The following certification exam question has quality issues in its answer choices.
Rewrite ONLY the answer choices and explanation to fix them. Do NOT change the stem or scenario.

**Stem (DO NOT CHANGE):** {question.stem}
**Key source text (DO NOT CHANGE):** {question.key_source_text}

**Current {"keys" if is_multi else "key"}:** {keys_json}
**Current distractors:** {json.dumps(question.distractors)}
**Current explanation:** {question.explanation}

**Issues to fix:**
{warning_list}

RULES:
- Rewrite the key(s) and distractors so ALL choices are similar in length and detail.
- The key(s) must remain factually identical to the original — same meaning, just reworded \
if needed for length balance.
- Replace any distractor that duplicates a key with a different plausible wrong answer.
- Replace "All/None of the above" with a specific, plausible wrong answer.
- The explanation must address each choice (A, B, C, D) individually by letter.

Return ONLY a JSON object with these keys (nothing else):
```json
{{
  {"\"keys\": [\"...\", \"...\"]," if is_multi else "\"key\": \"...\","}
  "distractors": ["...", "..."],
  "explanation": "A: Correct/Incorrect — <reason>. B: ..."
}}
```"""

    try:
        response = ollama_client.generate(
            prompt=prompt,
            model=model,
            system=system_prompt or GENERATION_SYSTEM_PROMPT,
            base_url=base_url,
            timeout=120.0,
        )
    except Exception as e:
        print(f"[AUTO-FIX] AI call failed: {e}")
        return None

    fence_match = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", response, re.DOTALL)
    text = fence_match.group(1) if fence_match else response

    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1:
        return None

    try:
        data = json.loads(text[start:end + 1])
    except json.JSONDecodeError:
        return None

    # Apply only choices + explanation — leave everything else untouched
    if is_multi and "keys" in data and isinstance(data["keys"], list):
        question.keys = data["keys"]
        question.key = data["keys"][0] if data["keys"] else question.key
    elif "key" in data and isinstance(data["key"], str):
        question.key = data["key"]

    if "distractors" in data and isinstance(data["distractors"], list):
        question.distractors = data["distractors"]

    if "explanation" in data:
        question.explanation = data["explanation"]

    # Verify the fix actually helped
    remaining = _get_fixable_warnings(question)
    if len(remaining) < len(warnings):
        return question  # improved, even if not perfect
    return None  # fix didn't help, caller keeps original


def generate_questions(
    slide: SlideInfo,
    model: str,
    base_url: str = "http://localhost:11434",
    num_questions: int = 2,
    difficulty: str = "Medium",
    bloom_level: str = "Apply",
    certification_id: str = "",
    source_file: str = "",
    custom_instructions: str = "",
    system_prompt: str = "",
    num_keys: int = 1,
    num_distractors: int = 3,
    topic: str = "",
    slide_image: str = "",
    progress_callback=None,
    question_specs: Optional[List[dict]] = None,
) -> List[Question]:
    """Generate questions from a slide using Ollama.

    Correct answers are enforced to come from speaker notes.
    If slide_image is provided (path to PNG), it is sent to vision-capable models.
    If question_specs is provided, it overrides num_questions/num_keys/num_distractors.
    """
    if question_specs is None:
        question_specs = _build_question_specs(num_questions, num_keys, num_distractors)
    num_questions = len(question_specs)

    prompt = build_prompt(
        slide=slide,
        num_questions=num_questions,
        difficulty=difficulty,
        bloom_level=bloom_level,
        certification=certification_id,
        custom_instructions=custom_instructions,
        question_specs=question_specs,
    )

    # Pass slide image for vision-capable models (e.g. llava, llama3.2-vision)
    images = [slide_image] if slide_image else None

    response = ollama_client.generate(
        prompt=prompt,
        model=model,
        system=system_prompt or GENERATION_SYSTEM_PROMPT,
        base_url=base_url,
        timeout=180.0,
        images=images,
    )

    items = _extract_json_array(response)
    if not items:
        return []

    questions = []
    for i, item in enumerate(items):
        if not isinstance(item, dict):
            continue

        q_type = item.get("question_type", "single")

        q = Question(
            scenario=item.get("scenario", ""),
            stem=item.get("stem", ""),
            question_type=q_type,
            key=item.get("key", ""),                      # single-select
            keys=item.get("keys", []),                     # multi-select
            key_source_text=item.get("key_source_text", ""),
            distractors=item.get("distractors", []),
            explanation=item.get("explanation", ""),
            source_file=source_file,
            source_slides=[slide.index],
            key_source_slide=slide.index,
            topic=topic or slide.title or "",
            difficulty=difficulty,
            bloom_level=bloom_level,
            certification_id=certification_id,
            status="draft",
        )

        # For multi-select, also set key to first correct for backward compat
        if q_type == "multi" and q.keys and not q.key:
            q.key = q.keys[0]

        # Auto-append "(Choose N.)" to ALL stems if AI forgot it
        stem = q.stem.strip()
        if "choose" not in stem.lower():
            if q_type == "multi" and q.keys and len(q.keys) >= 2:
                choose_word = _num_word(len(q.keys))
            else:
                choose_word = "one"
            if stem.endswith("?"):
                q.stem = f"{stem} (Choose {choose_word}.)"
            else:
                q.stem = f"{stem} (Choose {choose_word}.)"

        # Validate that the key is traceable to the speaker notes
        if not validate_key_against_notes(q, slide):
            # Tag the question so reviewers know validation failed
            q.tags = list(set(q.tags + ["key-not-validated"]))

        # Auto-fix quality issues by sending back to AI for improvement
        fixable = _get_fixable_warnings(q)
        if fixable:
            fix_desc = "; ".join(fixable)
            print(f"[GENERATE] Auto-fixing question {i+1}: {fix_desc}")
            if progress_callback:
                progress_callback(0, 1, f"Q{i+1}: fixing — {fix_desc}")
            fixed = _auto_fix_question(
                q, fixable, model=model, base_url=base_url,
                system_prompt=system_prompt or GENERATION_SYSTEM_PROMPT,
            )
            if fixed:
                q = fixed
                print(f"[GENERATE] Auto-fix succeeded for question {i+1}")
            else:
                print(f"[GENERATE] Auto-fix failed for question {i+1}, keeping original")

        questions.append(q)

    return questions


def generate_questions_batch(
    slides: List[SlideInfo],
    model: str,
    base_url: str = "http://localhost:11434",
    num_per_slide: int = 2,
    difficulty: str = "Medium",
    bloom_level: str = "Apply",
    certification_id: str = "",
    source_file: str = "",
    system_prompt: str = "",
    progress_callback=None,
    num_keys: int = 1,
    num_distractors: int = 3,
    topic: str = "",
    custom_instructions: str = "",
    slide_images: Optional[List[Optional[str]]] = None,
    question_specs: Optional[List[dict]] = None,
) -> List[Question]:
    """Generate questions for multiple slides.

    Args:
        progress_callback: Optional callable(current, total, message) for UI updates.
        topic: If set, overrides slide title as the question topic.
        custom_instructions: Extra instructions appended to the generation prompt.
        slide_images: Optional list of image paths (one per slide, None if unavailable).
    """
    all_questions = []
    total = len(slides)

    # Source shapes the progress wording: PCM/docs items are sections, not slides.
    is_docs = bool(source_file and source_file.startswith("docs:"))
    is_pcm = bool(source_file and source_file.startswith("pcm:"))

    for i, slide in enumerate(slides):
        if not slide.speaker_notes.strip() and not slide.body_text:
            if progress_callback:
                label = (slide.title or f"item {i + 1}") if (is_docs or is_pcm) else f"Slide {slide.index + 1}"
                progress_callback(i + 1, total, f"{label}: No content, skipping")
            continue

        if progress_callback:
            # Use the section title for docs/PCM content, slide number for PPTX.
            if is_docs:
                progress_callback(i, total, f"Generating from docs: {slide.title or source_file}...")
            elif is_pcm:
                progress_callback(i, total, f"Generating from section {i + 1}/{total}: {slide.title or 'course content'}...")
            else:
                progress_callback(i, total, f"Generating for slide {slide.index + 1}...")

        # Get slide image path if available
        img_path = ""
        if slide_images and i < len(slide_images) and slide_images[i]:
            img_path = str(slide_images[i])

        questions = generate_questions(
            slide=slide,
            model=model,
            base_url=base_url,
            num_questions=num_per_slide,
            difficulty=difficulty,
            bloom_level=bloom_level,
            certification_id=certification_id,
            source_file=source_file,
            system_prompt=system_prompt,
            num_keys=num_keys,
            num_distractors=num_distractors,
            topic=topic,
            custom_instructions=custom_instructions,
            question_specs=question_specs,
            slide_image=img_path,
            progress_callback=progress_callback,
        )
        all_questions.extend(questions)

    if progress_callback:
        progress_callback(total, total, f"Done — {len(all_questions)} questions generated")

    return all_questions
