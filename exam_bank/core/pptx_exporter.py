"""PowerPoint exporter for creating slide images via COM automation.

Uses Microsoft PowerPoint's COM interface to export each slide as a PNG image.
This gives pixel-perfect rendering of all shapes, charts, SmartArt, etc.
Falls back gracefully if PowerPoint is not installed.
"""

from pathlib import Path
from typing import List, Optional, Callable
from dataclasses import dataclass


@dataclass
class ExportedSlide:
    """Information about an exported slide."""
    index: int
    image_path: Optional[Path] = None


class PPTXExporter:
    """Exports PowerPoint slides as PNG images via COM automation.

    Uses win32com to drive PowerPoint and export each slide as a high-quality
    PNG image. If PowerPoint is already running, attaches to it (and won't
    quit it on cleanup). If not, launches a hidden instance.
    """

    def __init__(self, pptx_path: Path, output_dir: Path):
        self.pptx_path = Path(pptx_path)
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self._powerpoint = None
        self._presentation = None
        self._we_started_powerpoint = False

    def _init_powerpoint(self):
        """Initialize PowerPoint COM object for slide export.

        Uses win32com to automate PowerPoint via COM. CoInitialize is required
        because this may run in a background thread.
        If PowerPoint is already running, attach to it (and won't quit on cleanup).
        """
        try:
            import win32com.client
            import pythoncom
            pythoncom.CoInitialize()
            # Try to attach to an already-running PowerPoint instance first
            try:
                self._powerpoint = win32com.client.GetActiveObject("PowerPoint.Application")
                self._we_started_powerpoint = False
            except Exception:
                self._powerpoint = win32com.client.Dispatch("PowerPoint.Application")
                self._we_started_powerpoint = True
                # Try to hide; some Windows configs refuse — minimise instead
                try:
                    self._powerpoint.Visible = False
                except Exception:
                    self._powerpoint.Visible = True
                    self._powerpoint.WindowState = 2  # ppWindowMinimized
        except Exception as e:
            raise RuntimeError(f"Failed to initialize PowerPoint: {e}")

    def _open_presentation(self):
        """Open the presentation in PowerPoint."""
        if self._powerpoint is None:
            self._init_powerpoint()
        try:
            self._presentation = self._powerpoint.Presentations.Open(
                str(self.pptx_path.absolute()),
                ReadOnly=True,
                Untitled=False,
                WithWindow=False,
            )
        except Exception as e:
            raise RuntimeError(f"Failed to open presentation: {e}")

    def export_slides_as_images(
        self,
        progress_callback: Optional[Callable[[int, int], None]] = None,
    ) -> List[ExportedSlide]:
        """Export all slides as PNG images.

        Returns a list of ExportedSlide with the path to each PNG.
        """
        try:
            self._open_presentation()
            exported = []
            slide_count = self._presentation.Slides.Count

            for i in range(1, slide_count + 1):
                slide = self._presentation.Slides(i)
                image_path = self.output_dir / f"slide_{i:03d}.png"
                slide.Export(str(image_path.absolute()), "PNG")

                exported.append(ExportedSlide(
                    index=i - 1,
                    image_path=image_path,
                ))

                if progress_callback:
                    progress_callback(i, slide_count)

            return exported

        finally:
            self._cleanup()

    def _cleanup(self):
        """Clean up PowerPoint COM resources."""
        try:
            if self._presentation:
                self._presentation.Close()
                self._presentation = None
        except Exception:
            pass

        try:
            if self._powerpoint and self._we_started_powerpoint:
                self._powerpoint.Quit()
            self._powerpoint = None
        except Exception:
            pass

        try:
            import pythoncom
            pythoncom.CoUninitialize()
        except Exception:
            pass
