"""Cross-platform fallback slide exporter using python-pptx and Pillow.

When PowerPoint COM automation is unavailable (non-Windows platforms, or
Windows without PowerPoint installed), this module generates a simplified
visual representation of each slide as a PNG image.

It extracts text content from the .pptx via python-pptx and renders it
onto a white canvas using Pillow.  The result is not pixel-perfect but
gives a usable preview with title, body bullets, slide number, and a
notes indicator.
"""

from pathlib import Path
from typing import List, Optional, Callable
from dataclasses import dataclass

from pptx import Presentation
from pptx.util import Emu
from PIL import Image, ImageDraw, ImageFont


# Re-export so callers can import from either module.
@dataclass
class ExportedSlide:
    """Information about an exported slide."""
    index: int
    image_path: Optional[Path] = None


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
SLIDE_WIDTH = 1280
SLIDE_HEIGHT = 720

# Layout margins / positions
MARGIN_LEFT = 60
MARGIN_RIGHT = 60
TITLE_Y = 40
BODY_Y = 130
BODY_LINE_HEIGHT = 32
NOTES_INDICATOR_Y = SLIDE_HEIGHT - 50
SLIDE_NUMBER_Y = SLIDE_HEIGHT - 40
SLIDE_NUMBER_X = SLIDE_WIDTH - MARGIN_RIGHT

# Colours
BG_COLOUR = (255, 255, 255)
TITLE_COLOUR = (30, 60, 120)
BODY_COLOUR = (50, 50, 50)
ACCENT_COLOUR = (100, 140, 200)
NOTES_COLOUR = (120, 120, 120)
SLIDE_NUM_COLOUR = (160, 160, 160)
BORDER_COLOUR = (200, 210, 225)

# Font sizes (used with default font when TrueType is unavailable)
TITLE_FONT_SIZE = 28
BODY_FONT_SIZE = 18
SMALL_FONT_SIZE = 14


def _load_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    """Try to load a TrueType font at *size*; fall back to the default bitmap font."""
    # Preferred fonts in order — covers Windows, macOS, common Linux installs.
    candidates = [
        "arial.ttf",
        "Arial.ttf",
        "DejaVuSans.ttf",
        "LiberationSans-Regular.ttf",
        "FreeSans.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
        "/System/Library/Fonts/Helvetica.ttc",
        "C:/Windows/Fonts/arial.ttf",
    ]
    for name in candidates:
        try:
            return ImageFont.truetype(name, size)
        except (OSError, IOError):
            continue
    # Absolute last resort – Pillow's built-in bitmap font (ignores size).
    return ImageFont.load_default()


def _wrap_text(text: str, font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
               max_width: int) -> List[str]:
    """Word-wrap *text* so that no line exceeds *max_width* pixels."""
    words = text.split()
    if not words:
        return []

    lines: List[str] = []
    current_line = words[0]

    for word in words[1:]:
        test_line = f"{current_line} {word}"
        try:
            bbox = font.getbbox(test_line)
            line_width = bbox[2] - bbox[0]
        except AttributeError:
            # Older Pillow without getbbox
            line_width = font.getsize(test_line)[0]  # type: ignore[attr-defined]

        if line_width <= max_width:
            current_line = test_line
        else:
            lines.append(current_line)
            current_line = word

    lines.append(current_line)
    return lines


# ---------------------------------------------------------------------------
# Slide text extraction helpers
# ---------------------------------------------------------------------------

def _extract_title(slide) -> str:
    """Return the slide title text, or a fallback string."""
    if slide.shapes.title and slide.shapes.title.has_text_frame:
        return slide.shapes.title.text_frame.text.strip()

    # Some layouts store the title in a placeholder without the .title shortcut.
    for shape in slide.shapes:
        if shape.has_text_frame and shape.shape_id != 0:
            text = shape.text_frame.text.strip()
            if text:
                return text
    return ""


def _extract_body_bullets(slide) -> List[str]:
    """Return a list of body-text bullet strings (one per paragraph)."""
    bullets: List[str] = []
    title_shape = slide.shapes.title

    for shape in slide.shapes:
        if shape == title_shape:
            continue
        if not shape.has_text_frame:
            continue
        for para in shape.text_frame.paragraphs:
            text = para.text.strip()
            if text:
                # Indent based on paragraph level
                level = para.level if para.level else 0
                indent = "  " * level
                prefix = "\u2022 " if level == 0 else "\u2013 "
                bullets.append(f"{indent}{prefix}{text}")
    return bullets


def _has_notes(slide) -> bool:
    """Return True if the slide has non-empty speaker notes."""
    try:
        notes_slide = slide.notes_slide
        if notes_slide and notes_slide.notes_text_frame:
            return bool(notes_slide.notes_text_frame.text.strip())
    except Exception:
        pass
    return False


# ---------------------------------------------------------------------------
# Main class
# ---------------------------------------------------------------------------

class PPTXExporterFallback:
    """Exports PowerPoint slides as PNG images using python-pptx + Pillow.

    This is a cross-platform fallback for ``PPTXExporter`` (which requires
    Windows with PowerPoint installed).  The generated images are simplified
    text-based representations, not full renders.
    """

    def __init__(self, pptx_path: Path, output_dir: Path):
        self.pptx_path = Path(pptx_path)
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # Pre-load fonts once so we don't search the filesystem per-slide.
        self._title_font = _load_font(TITLE_FONT_SIZE)
        self._body_font = _load_font(BODY_FONT_SIZE)
        self._small_font = _load_font(SMALL_FONT_SIZE)

    # ------------------------------------------------------------------
    # Public API (mirrors PPTXExporter)
    # ------------------------------------------------------------------

    def export_slides_as_images(
        self,
        progress_callback: Optional[Callable[[int, int], None]] = None,
    ) -> List[ExportedSlide]:
        """Export all slides as PNG images.

        Returns a list of :class:`ExportedSlide` with the path to each PNG.
        """
        prs = Presentation(str(self.pptx_path))
        slides = list(prs.slides)
        slide_count = len(slides)
        exported: List[ExportedSlide] = []

        for i, slide in enumerate(slides, start=1):
            image_path = self.output_dir / f"slide_{i:03d}.png"
            self._render_slide(slide, i, slide_count, image_path)

            exported.append(ExportedSlide(
                index=i - 1,
                image_path=image_path,
            ))

            if progress_callback:
                progress_callback(i, slide_count)

        return exported

    # ------------------------------------------------------------------
    # Internal rendering
    # ------------------------------------------------------------------

    def _render_slide(self, slide, slide_number: int, total_slides: int,
                      output_path: Path) -> None:
        """Render a single slide to a PNG file."""
        img = Image.new("RGB", (SLIDE_WIDTH, SLIDE_HEIGHT), BG_COLOUR)
        draw = ImageDraw.Draw(img)

        # Thin border to visually frame the slide
        draw.rectangle(
            [0, 0, SLIDE_WIDTH - 1, SLIDE_HEIGHT - 1],
            outline=BORDER_COLOUR,
            width=2,
        )

        # Accent bar at top
        draw.rectangle([0, 0, SLIDE_WIDTH, 6], fill=ACCENT_COLOUR)

        max_text_width = SLIDE_WIDTH - MARGIN_LEFT - MARGIN_RIGHT

        # --- Title ---
        title_text = _extract_title(slide)
        if title_text:
            wrapped_title = _wrap_text(title_text, self._title_font, max_text_width)
            y = TITLE_Y
            for line in wrapped_title:
                draw.text((MARGIN_LEFT, y), line, fill=TITLE_COLOUR,
                          font=self._title_font)
                y += TITLE_FONT_SIZE + 8

            # Separator line below title
            sep_y = y + 4
            draw.line([(MARGIN_LEFT, sep_y), (SLIDE_WIDTH - MARGIN_RIGHT, sep_y)],
                      fill=BORDER_COLOUR, width=1)
        else:
            title_text = ""

        # --- Body bullets ---
        bullets = _extract_body_bullets(slide)
        y = BODY_Y
        for bullet in bullets:
            if y > SLIDE_HEIGHT - 80:
                # Overflow indicator
                draw.text((MARGIN_LEFT, y), "...", fill=BODY_COLOUR,
                          font=self._body_font)
                break

            wrapped = _wrap_text(bullet, self._body_font, max_text_width)
            for line in wrapped:
                if y > SLIDE_HEIGHT - 80:
                    break
                draw.text((MARGIN_LEFT, y), line, fill=BODY_COLOUR,
                          font=self._body_font)
                y += BODY_LINE_HEIGHT
            # Small gap between bullets
            y += 4

        # --- Notes indicator ---
        if _has_notes(slide):
            draw.text(
                (MARGIN_LEFT, NOTES_INDICATOR_Y),
                "\U0001f4dd Speaker Notes Available",
                fill=NOTES_COLOUR,
                font=self._small_font,
            )

        # --- Slide number ---
        number_text = f"{slide_number} / {total_slides}"
        try:
            bbox = self._small_font.getbbox(number_text)
            text_width = bbox[2] - bbox[0]
        except AttributeError:
            text_width = self._small_font.getsize(number_text)[0]  # type: ignore[attr-defined]

        draw.text(
            (SLIDE_NUMBER_X - text_width, SLIDE_NUMBER_Y),
            number_text,
            fill=SLIDE_NUM_COLOUR,
            font=self._small_font,
        )

        img.save(str(output_path), "PNG")
