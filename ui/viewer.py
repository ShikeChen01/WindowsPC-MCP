"""Interactive viewer window — live feed of the agent's virtual display."""
from __future__ import annotations

import json
import logging
from pathlib import Path

from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QPixmap, QImage, QKeyEvent

logger = logging.getLogger(__name__)

STATUS_FILE = Path.home() / ".windowsmcp" / "status.json"

_VIEWER_STYLE = """
QWidget {
    background: #0d1117;
    color: #e6edf3;
}
QLabel#header_title {
    font-size: 14px;
    font-weight: bold;
    color: #e6edf3;
}
QLabel#live_badge {
    background: #22c55e;
    color: #fff;
    font-size: 10px;
    font-weight: bold;
    border-radius: 4px;
    padding: 2px 6px;
}
QPushButton#fullscreen_btn {
    background: #2d2d4e;
    color: #e6edf3;
    border: 1px solid #4a4a6e;
    border-radius: 5px;
    padding: 4px 12px;
    font-size: 11px;
}
QPushButton#fullscreen_btn:hover {
    background: #3d3d6e;
}
QLabel#display_area {
    background: #000;
}
"""


class ViewerWindow(QWidget):
    """Resizable window that streams the agent's virtual display at ~30 fps."""

    def __init__(self) -> None:
        super().__init__()
        self._fullscreen = False
        self._build_ui()
        self._start_capture_timer()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        self.setWindowTitle("Agent Screen Viewer")
        self.setMinimumSize(640, 360)
        self.setStyleSheet(_VIEWER_STYLE)

        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(6)

        # --- Header row ---
        header = QHBoxLayout()
        header.setSpacing(8)

        title = QLabel("Agent Screen Viewer")
        title.setObjectName("header_title")

        live = QLabel("LIVE")
        live.setObjectName("live_badge")

        self._fullscreen_btn = QPushButton("Fullscreen")
        self._fullscreen_btn.setObjectName("fullscreen_btn")
        self._fullscreen_btn.clicked.connect(self._toggle_fullscreen)

        header.addWidget(title)
        header.addWidget(live)
        header.addStretch()
        header.addWidget(self._fullscreen_btn)
        root.addLayout(header)

        # --- Display area ---
        self._display = QLabel()
        self._display.setObjectName("display_area")
        self._display.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._display.setMinimumSize(624, 320)
        root.addWidget(self._display, stretch=1)

    # ------------------------------------------------------------------
    # Capture
    # ------------------------------------------------------------------

    def _start_capture_timer(self) -> None:
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._capture_frame)
        self._timer.start(33)  # ~30 fps

    def _capture_frame(self) -> None:
        try:
            # Read status to find agent display bounds
            if not STATUS_FILE.exists():
                return
            status = json.loads(STATUS_FILE.read_text())
            disp = status.get("display", {})
            left = disp.get("left", 0)
            top = disp.get("top", 0)
            right = disp.get("right")
            bottom = disp.get("bottom")

            if right is None or bottom is None:
                # Try width/height fallback
                width = disp.get("width")
                height = disp.get("height")
                if width is None or height is None:
                    return
                right = left + width
                bottom = top + height

            # Capture the region using the project's capture module
            from windowsmcp_custom.display.capture import capture_region
            img = capture_region(left, top, right, bottom)

            # Convert PIL Image -> QPixmap
            img_rgb = img.convert("RGB")
            data = img_rgb.tobytes("raw", "RGB")
            qimg = QImage(data, img_rgb.width, img_rgb.height, img_rgb.width * 3, QImage.Format.Format_RGB888)
            pixmap = QPixmap.fromImage(qimg)

            # Scale to fit the display label while preserving aspect ratio
            scaled = pixmap.scaled(
                self._display.size(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            self._display.setPixmap(scaled)

        except Exception as exc:
            logger.debug("Frame capture failed: %s", exc)

    # ------------------------------------------------------------------
    # Fullscreen toggle
    # ------------------------------------------------------------------

    def _toggle_fullscreen(self) -> None:
        if self._fullscreen:
            self.showNormal()
            self._fullscreen_btn.setText("Fullscreen")
            self._fullscreen = False
        else:
            self.showFullScreen()
            self._fullscreen_btn.setText("Exit Fullscreen")
            self._fullscreen = True

    # ------------------------------------------------------------------
    # Key events
    # ------------------------------------------------------------------

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() == Qt.Key.Key_Escape and self._fullscreen:
            self._toggle_fullscreen()
        else:
            super().keyPressEvent(event)
