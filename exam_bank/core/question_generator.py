"""AI-powered question generation — backward-compatible re-exports.

This module was refactored into four focused submodules:
  - generation_prompts.py  — Prompt construction and constants
  - generation_parsing.py  — JSON extraction and validation utilities
  - question_generation.py — Core generation pipeline
  - question_refinement.py — Post-generation AI operations (regen, QA, explain, key assignment)

All public names are re-exported here for backward compatibility.
For new code, import directly from the submodule.
"""

# Prompt construction and constants
from .generation_prompts import (
    GENERATION_SYSTEM_PROMPT,
    _build_question_specs,
    build_prompt,
    _num_word,
)

# JSON extraction and validation utilities
from .generation_parsing import (
    _extract_json_array,
    _extract_json_object,
    validate_key_against_notes,
)

# Core generation pipeline
from .question_generation import (
    generate_questions,
    generate_questions_batch,
    _FIXABLE_WARNINGS,
    _get_fixable_warnings,
    _auto_fix_question,
)

# Post-generation AI operations
from .question_refinement import (
    regen_stem,
    regen_key,
    regen_distractor,
    improve_question,
    qa_check_question,
    qa_fix_question,
    generate_explanation,
    ai_assign_keys,
)
