"""Qt6 GUI: pick a screen region, monitor for Claude Code permission dialogs,
and auto-click Yes."""

from __future__ import annotations

import os
import sys
import threading

from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QCloseEvent, QKeySequence, QShortcut, QTextCursor
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPlainTextEdit,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from src.clicker import _backend_name
from src.config_paths import REGION_FILE
from src.monitor import run_monitor
from src.region_picker import Region, RegionPicker, load_region, save_region

__version__ = "1.0.0"


# ── Cross-thread signal bridge ──────────────────────────────────────


class _MonitorSignals(QObject):
    """Lives in the main thread; forwards worker messages via Qt signals."""

    log_signal = Signal(str)
    finished = Signal()


# ── Main Window ─────────────────────────────────────────────────────


class MainWindow(QMainWindow):
    """Main application window."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(f"Claude Code Auto Yes v{__version__}")
        self.setMinimumSize(520, 480)
        self.resize(520, 560)

        self._region: Region | None = load_region()
        self._signals = _MonitorSignals()
        self._signals.log_signal.connect(self.log)
        self._signals.finished.connect(self._on_monitor_finished)
        self._stop_event = threading.Event()
        self._monitor_thread: threading.Thread | None = None
        self._picker: RegionPicker | None = None

        self._setup_ui()
        self._update_region_label()
        self._update_buttons()
        self._setup_shortcuts()

    # ── UI Setup ────────────────────────────────────────────────────

    def _setup_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setSpacing(10)
        layout.setContentsMargins(16, 16, 16, 16)

        # ── Header ──
        header = QLabel("Claude Code Auto Yes")
        header.setStyleSheet(
            "font-size: 16px; font-weight: bold; color: #1a73e8; padding-bottom: 2px;"
        )
        layout.addWidget(header)

        subtitle = QLabel(
            "Monitors a screen region for permission dialogs and auto-clicks Yes."
        )
        subtitle.setStyleSheet("color: #666; padding-bottom: 6px;")
        subtitle.setWordWrap(True)
        layout.addWidget(subtitle)

        # ── Region info ──
        self._region_label = QLabel()
        self._region_label.setStyleSheet("padding: 4px 0;")
        layout.addWidget(self._region_label)

        # ── Buttons ──
        btn_frame = QFrame()
        btn_layout = QHBoxLayout(btn_frame)
        btn_layout.setContentsMargins(0, 0, 0, 0)

        self._pick_btn = QPushButton("Pick Region")
        self._pick_btn.clicked.connect(self._on_pick_region)
        self._pick_btn.setMinimumHeight(32)
        btn_layout.addWidget(self._pick_btn)

        self._start_btn = QPushButton("Start")
        self._start_btn.clicked.connect(self._on_start)
        self._start_btn.setMinimumHeight(32)
        self._start_btn.setStyleSheet(
            "QPushButton { background-color: #1a73e8; color: white; "
            "border: none; border-radius: 4px; padding: 6px 20px; }"
            "QPushButton:hover { background-color: #1557b0; }"
            "QPushButton:disabled { background-color: #ccc; }"
        )
        btn_layout.addWidget(self._start_btn)

        self._stop_btn = QPushButton("Stop")
        self._stop_btn.clicked.connect(self._on_stop)
        self._stop_btn.setMinimumHeight(32)
        self._stop_btn.setEnabled(False)
        btn_layout.addWidget(self._stop_btn)

        layout.addWidget(btn_frame)

        # ── Options ──
        opt_group = QGroupBox("Options")
        opt_layout = QVBoxLayout(opt_group)

        self._dry_run_cb = QCheckBox("Dry run (detect only, no click)")
        self._dry_run_cb.setToolTip("Log detection results but do not actually click")
        opt_layout.addWidget(self._dry_run_cb)

        self._verbose_cb = QCheckBox("Verbose log (show OCR text)")
        opt_layout.addWidget(self._verbose_cb)

        self._keyboard_cb = QCheckBox("Keyboard only (press 1, no mouse move)")
        self._keyboard_cb.setToolTip(
            "Send key '1' to frontmost window instead of mouse click"
        )
        opt_layout.addWidget(self._keyboard_cb)

        self._restore_cb = QCheckBox("Restore cursor after click")
        self._restore_cb.setChecked(True)
        opt_layout.addWidget(self._restore_cb)

        layout.addWidget(opt_group)

        # ── Log ──
        log_label = QLabel("Log")
        log_label.setStyleSheet("font-weight: bold; padding-top: 4px;")
        layout.addWidget(log_label)

        self._log = QPlainTextEdit()
        self._log.setReadOnly(True)
        self._log.setMaximumBlockCount(500)
        self._log.setStyleSheet(
            "QPlainTextEdit { font-family: 'Terminal', 'Liberation Mono', "
            "'Courier New', monospace; font-size: 12px; "
            "background: #1e1e1e; color: #d4d4d4; }"
        )
        self._log.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        layout.addWidget(self._log, stretch=1)

        # ── Status bar ──
        self._status_label = QLabel(f"Backend: {_backend_name()}")
        self.statusBar().addPermanentWidget(self._status_label)

    # ── Keyboard Shortcuts ──────────────────────────────────────────

    def _setup_shortcuts(self) -> None:
        QShortcut(QKeySequence("Ctrl+R"), self, self._on_pick_region)
        QShortcut(QKeySequence("Ctrl+S"), self, self._on_start)
        QShortcut(QKeySequence("Ctrl+Shift+S"), self, self._on_stop)

    # ── Region ──────────────────────────────────────────────────────

    def _update_region_label(self) -> None:
        if self._region is None:
            self._region_label.setText(
                '<span style="color: #c0392b;">Region: not set</span>'
            )
        else:
            r = self._region
            self._region_label.setText(
                f'<span style="color: #1a7f37;">Region: x={r.x} y={r.y} '
                f"{r.width}&times;{r.height}</span>"
            )

    def _on_pick_region(self) -> None:
        if self._monitor_thread and self._monitor_thread.is_alive():
            self.log("Stop monitoring before re-picking region")
            return

        picker = RegionPicker()
        picker.region_selected.connect(self._on_region_selected)
        picker.destroyed.connect(lambda: setattr(self, "_picker", None))
        self._picker = picker
        picker.show()
        picker.raise_()
        picker.activateWindow()

    def _on_region_selected(self, x: int, y: int, w: int, h: int) -> None:
        region = Region(x, y, w, h)
        save_region(region)
        self._region = region
        self._update_region_label()
        self.log(f"Region saved: ({x},{y}) {w}x{h}")

    # ── Monitor control ─────────────────────────────────────────────

    def _update_buttons(self) -> None:
        running = self._monitor_thread is not None and self._monitor_thread.is_alive()
        self._pick_btn.setEnabled(not running)
        self._start_btn.setEnabled(not running)
        self._stop_btn.setEnabled(running)
        self._dry_run_cb.setEnabled(not running)
        self._verbose_cb.setEnabled(not running)
        self._keyboard_cb.setEnabled(not running)
        self._restore_cb.setEnabled(not running)

    def _on_start(self) -> None:
        if self._monitor_thread and self._monitor_thread.is_alive():
            return
        if self._region is None:
            self.log("Pick a region first")
            return

        dry_run = self._dry_run_cb.isChecked()
        verbose = self._verbose_cb.isChecked()
        keyboard_only = self._keyboard_cb.isChecked()
        restore_cursor = self._restore_cb.isChecked()
        region = self._region
        stop_event = self._stop_event
        signals = self._signals

        tags = []
        if dry_run:
            tags.append("dry-run")
        if keyboard_only:
            tags.append("keyboard")
        tag = f" [{', '.join(tags)}]" if tags else ""
        self.log(
            f"Monitoring {region.width}x{region.height}"
            f" on {REGION_FILE.name}{tag}"
        )

        def worker() -> None:
            try:
                run_monitor(
                    region,
                    interval=5.0,
                    dry_run=dry_run,
                    verbose=verbose,
                    stop_event=stop_event,
                    on_message=signals.log_signal.emit,
                    keyboard_only=keyboard_only,
                    restore_cursor=restore_cursor,
                )
            except Exception as exc:
                signals.log_signal.emit(f"ERROR: {exc}")
            finally:
                signals.finished.emit()

        self._stop_event.clear()
        self._monitor_thread = threading.Thread(target=worker, daemon=True)
        self._monitor_thread.start()
        self._update_buttons()

    def _on_stop(self) -> None:
        self.log("Stopping...")
        self._stop_event.set()

    def _on_monitor_finished(self) -> None:
        self._monitor_thread = None
        self._update_buttons()
        self.log("Stopped")

    # ── Logging ─────────────────────────────────────────────────────

    def log(self, msg: str) -> None:
        print(msg, file=sys.stderr)  # fallback: always visible in terminal
        self._log.appendPlainText(msg)
        cursor = self._log.textCursor()
        cursor.movePosition(QTextCursor.End)
        self._log.setTextCursor(cursor)

    # ── Window close ────────────────────────────────────────────────

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802
        self.log("Shutting down...")
        self._stop_event.set()
        event.accept()
        # Force exit to kill background thread immediately
        os._exit(0)


# ── Entry point ─────────────────────────────────────────────────────


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("Claude Code Auto Yes")
    app.setApplicationVersion(__version__)
    app.setOrganizationName("claude-code-auto-yes")

    window = MainWindow()
    window.show()

    if window._region is None:
        window.log("First run: click [Pick Region] to select the permission dialog area")
    else:
        window.log("Region loaded from config. Click [Start] or Ctrl+S to begin monitoring.")

    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
