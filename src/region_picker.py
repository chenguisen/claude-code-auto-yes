"""Qt6 fullscreen overlay for selecting a screen region."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

from PySide6.QtCore import QPoint, QRect, Qt, Signal
from PySide6.QtGui import QColor, QGuiApplication, QPainter, QPen
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from src.config_paths import CONFIG_DIR, REGION_FILE


@dataclass
class Region:
    x: int
    y: int
    width: int
    height: int

    def to_mss_monitor(self) -> dict[str, int]:
        return {
            "left": self.x,
            "top": self.y,
            "width": self.width,
            "height": self.height,
        }


def load_region(path: Path | None = None) -> Region | None:
    path = path or REGION_FILE
    if not path.exists():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    return Region(
        x=int(data["x"]),
        y=int(data["y"]),
        width=int(data["width"]),
        height=int(data["height"]),
    )


def save_region(region: Region, path: Path | None = None) -> None:
    path = path or REGION_FILE
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(asdict(region), indent=2) + "\n",
        encoding="utf-8",
    )


def parse_region_arg(value: str) -> Region:
    """Parse 'x,y,width,height' from CLI."""
    parts = [p.strip() for p in value.split(",")]
    if len(parts) != 4:
        raise ValueError("format must be x,y,width,height")
    x, y, w, h = (int(p) for p in parts)
    if w < 10 or h < 10:
        raise ValueError("width and height must be >= 10")
    return Region(x=x, y=y, width=w, height=h)


class RegionPicker(QWidget):
    """Fullscreen overlay: drag to select a screen region, Enter to confirm."""

    region_selected = Signal(int, int, int, int)  # x, y, w, h

    def __init__(self) -> None:
        super().__init__()
        self._start_pos: QPoint | None = None
        self._current_pos: QPoint | None = None
        self._selection: QRect | None = None

        self._setup_window()

        self.setMouseTracking(True)
        self.setCursor(Qt.CrossCursor)
        self.setFocus()

    def _setup_window(self) -> None:
        # Use fewer flags on X11/XWayland to ensure the overlay receives input
        flags = Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool
        self.setWindowFlags(flags)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setStyleSheet("background: transparent;")

        # Cover the full virtual desktop across all monitors
        desk = QGuiApplication.primaryScreen().virtualGeometry()
        self.setGeometry(desk)

    # --- drawing ---

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        # Dim the whole screen
        painter.fillRect(self.rect(), QColor(0, 0, 0, 140))

        if self._selection:
            self._draw_selection(painter, self._selection, active=True)
        elif self._start_pos and self._current_pos:
            rect = QRect(self._start_pos, self._current_pos).normalized()
            self._draw_selection(painter, rect, active=False)

    def _draw_selection(self, painter: QPainter, rect: QRect, *, active: bool) -> None:
        # Clear dim in selected area
        painter.setCompositionMode(QPainter.CompositionMode_Clear)
        painter.fillRect(rect, QColor(0, 0, 0, 0))
        painter.setCompositionMode(QPainter.CompositionMode_SourceOver)

        # Border
        color = QColor(0, 200, 255) if active else QColor(0, 150, 220)
        painter.setPen(QPen(color, 3))
        painter.drawRect(rect)

        # Hint text
        text = f"{rect.width()} x {rect.height()}  "
        text += "Enter=confirm  Esc=cancel" if active else "Drag to select region"
        painter.setPen(Qt.white)
        font = painter.font()
        font.setPointSize(14)
        painter.setFont(font)

        label_rect = QRect(rect.x(), rect.y() - 32, rect.width(), 28)
        if label_rect.y() < 10:
            label_rect.moveTop(rect.y() + rect.height() + 8)
        painter.drawText(label_rect, Qt.AlignCenter, text)

    # --- mouse ---

    def mousePressEvent(self, event) -> None:  # noqa: N802
        self._start_pos = event.globalPosition().toPoint()
        self._current_pos = self._start_pos
        self._selection = None
        self.update()

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        if self._start_pos:
            self._current_pos = event.globalPosition().toPoint()
            self._selection = None
            self.update()

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        if self._start_pos:
            end = event.globalPosition().toPoint()
            self._selection = QRect(self._start_pos, end).normalized()
            self._start_pos = None
            self._current_pos = None
            self.update()

    # --- keyboard ---

    def keyPressEvent(self, event) -> None:  # noqa: N802
        if event.key() in (Qt.Key_Return, Qt.Key_Enter) and self._selection:
            r = self._selection
            self.region_selected.emit(r.x(), r.y(), r.width(), r.height())
            self.close()
        elif event.key() == Qt.Key_Escape:
            self.close()

    def closeEvent(self, event) -> None:  # noqa: N802
        super().closeEvent(event)


def pick_region() -> Region | None:
    """Show picker synchronously, return selected Region or None."""
    result: list[Region | None] = [None]

    def on_selected(x: int, y: int, w: int, h: int) -> None:
        if w >= 10 and h >= 10:
            result[0] = Region(x, y, w, h)

    app = QGuiApplication.instance() or QGuiApplication()
    picker = RegionPicker()
    picker.region_selected.connect(on_selected)
    picker.show()
    # On Wayland the event loop may already be running; if so just show
    if app is QGuiApplication.instance():
        picker.show()
        picker.raise_()
        picker.activateWindow()
    app.exec()
    return result[0]


def pick_and_save_region() -> Region | None:
    region = pick_region()
    if region is not None:
        save_region(region)
        print(f"Region saved: x={region.x}, y={region.y}  {region.width}x{region.height}")
    else:
        print("Region pick cancelled")
    return region
