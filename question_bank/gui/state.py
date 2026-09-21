"""Shared application state and UI references for the Question Bank app."""

from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from ..core.pptx_reader import PPTXReader
from ..core.source import SlideInfo
from ..core.question_bank import Question, QuestionBankDB, Certification
from ..utils.config import DB_PATH


# ── Event names (constants to avoid typos) ─────────────────────
EVT_QUESTIONS_CHANGED = "questions_changed"      # generated questions list changed
EVT_BANK_CHANGED = "bank_changed"                # saved questions in bank changed
EVT_STATS_CHANGED = "stats_changed"              # bank stats need refresh
EVT_CERTIFICATIONS_CHANGED = "certifications_changed"  # certs/topics/sidebar
EVT_FILES_CHANGED = "files_changed"              # loaded file list changed
EVT_SLIDE_CHANGED = "slide_changed"              # slide preview needs refresh
EVT_ACTION_BAR_CHANGED = "action_bar_changed"    # action bar (generate/progress)
EVT_ADMIN_CHANGED = "admin_changed"              # admin tab data changed


class EventBus:
    """Simple synchronous pub/sub event bus for cross-component communication."""

    def __init__(self):
        self._handlers: Dict[str, List[Callable]] = defaultdict(list)

    def on(self, event: str, handler: Callable):
        """Register a handler for an event. Duplicates are ignored."""
        if handler not in self._handlers[event]:
            self._handlers[event].append(handler)

    def off(self, event: str, handler: Callable):
        """Remove a handler for an event."""
        handlers = self._handlers.get(event, [])
        self._handlers[event] = [h for h in handlers if h is not handler]

    def emit(self, event: str, **kwargs):
        """Fire all handlers for an event. Handlers are called synchronously."""
        for handler in list(self._handlers.get(event, [])):
            try:
                handler(**kwargs) if kwargs else handler()
            except Exception as e:
                print(f"[EventBus] Error in handler for '{event}': {e}")

    def emit_many(self, *events: str):
        """Emit multiple events in sequence (convenience for common patterns)."""
        for event in events:
            self.emit(event)


@dataclass
class LoadedFile:
    """A PPTX/PDF file loaded into the app."""
    path: Path
    reader: Optional[PPTXReader] = None
    slide_count: int = 0
    certification_id: str = ""      # Which certification this deck is assigned to
    topic: str = ""                  # Topic label for generated questions
    slide_images: List[Optional[Path]] = field(default_factory=list)  # PNG paths per slide

    def load(self) -> bool:
        self.reader = PPTXReader(self.path)
        if self.reader.load():
            self.slide_count = self.reader.slide_count
            self.slide_images = [None] * self.slide_count
            return True
        return False


@dataclass
class AppState:
    """Mutable application state shared across all components."""
    # Event bus for cross-component communication
    bus: EventBus = field(default_factory=EventBus)

    # Loaded files
    files: List[LoadedFile] = field(default_factory=list)
    selected_file_idx: int = -1
    current_slide_idx: int = 0

    # Preview cache bust counter (increment to force browser image refresh)
    preview_cache_bust: int = 0

    # Question bank
    db: QuestionBankDB = field(default_factory=lambda: QuestionBankDB(DB_PATH))

    # Generated questions (current batch, before saving)
    generated_questions: List[Question] = field(default_factory=list)

    # Currently editing question
    editing_question: Optional[Question] = None

    # Bank browser filters
    filter_text: str = ""
    filter_topic: str = ""
    filter_difficulty: str = ""
    filter_bloom: str = ""
    filter_status: str = ""

    # Active sidebar selections (used for docs-based generation without a file)
    active_cert_id: str = ""
    active_topic: str = ""
    active_mcp_servers: List[str] = field(default_factory=list)  # selected server URLs for docs gen

    # Processing state
    is_generating: bool = False
    progress_fraction: float = 0.0
    progress_message: str = ""

    @property
    def selected_file(self) -> Optional[LoadedFile]:
        if 0 <= self.selected_file_idx < len(self.files):
            return self.files[self.selected_file_idx]
        return None

    @property
    def current_slide(self) -> Optional[SlideInfo]:
        f = self.selected_file
        if f and f.reader and 0 <= self.current_slide_idx < f.slide_count:
            return f.reader.get_slide(self.current_slide_idx)
        return None


@dataclass
class UIRefs:
    """Direct UI references (not event-based)."""
    on_generate: Optional[Callable] = None
    on_generate_batch: Optional[Callable] = None
    # Tab references for programmatic switching
    tabs: Any = None
    generate_tab: Any = None  # the Slides/Generate tab element
    # Slide navigation (exposed for keyboard shortcuts)
    nav_slide: Optional[Callable] = None
    # Save all generated questions (exposed for keyboard shortcuts)
    save_all_questions: Optional[Callable] = None
