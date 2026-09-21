"""Shared context for import tab sub-modules.

Holds mutable state and references that all import sub-modules need access to,
avoiding deep closure coupling while keeping the import tab modular.
"""

from dataclasses import dataclass, field
from typing import Callable, Optional

from nicegui.element import Element

from ..state import AppState, UIRefs


@dataclass
class ImportContext:
    """Shared mutable context for the import tab and its sub-modules."""

    state: AppState = None                        # type: ignore[assignment]
    refs: UIRefs = None                           # type: ignore[assignment]

    # Mutable containers for UI state
    imported_questions: list = field(default_factory=list)  # [(Question, passed, details, dupe_info)]
    import_cert_id: dict = field(default_factory=lambda: {"value": ""})
    import_topic: dict = field(default_factory=lambda: {"value": ""})
    import_reader: dict = field(default_factory=lambda: {"reader": None, "source_file": ""})
    validation_mode: dict = field(default_factory=lambda: {"value": "pptx"})
    autofix_enabled: dict = field(default_factory=lambda: {"value": False})

    # NiceGUI elements (set during build)
    callback_anchor: Optional[Element] = None

    # Callbacks (set during build)
    refresh: Optional[Callable] = None
