"""Floating toolbar widget — compact always-on-top status bar."""
from __future__ import annotations

from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton
from PyQt6.QtCore import Qt, QPoint
from PyQt6.QtGui import QColor


_DARK_STYLE = """
QWidget#toolbar {
    background: #1a1a2e;
    border-radius: 10px;
    border: 1px solid #2d2d4e;
}
QLabel#title {
    color: #e6edf3;
    font-size: 13px;
    font-weight: bold;
}
QLabel#state, QLabel#screen {
    color: #9ca3af;
    font-size: 11px;
}
QPushButton#open_viewer {
    background: #2d2d4e;
    color: #e6edf3;
    border: 1px solid #4a4a6e;
    border-radius: 5px;
    padding: 4px 10px;
    font-size: 11px;
}
QPushButton#open_viewer:hover {
    background: #3d3d6e;
}
"""

_DOT_COLORS = {
    "ready": "#22c55e",     # green
    "degraded": "#f59e0b",  # amber
}
_DOT_DEFAULT = "#6b7280"  # gray


class ToolbarWindow(QWidget):
    """Compact draggable always-on-top frameless status toolbar."""

    def __init__(self) -> None:
        super().__init__()
        self._drag_pos: QPoint | None = None
        self._viewer: "ViewerWindow | None" = None  # noqa: F821
        self._build_ui()

    def _build_ui(self) -> None:
        self.setObjectName("toolbar")
        self.setWindowFlags(
            Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedWidth(240)
        self.setStyleSheet(_DARK_STYLE)

        root = QVBoxLayout(self)
        root.setContentsMargins(12, 10, 12, 10)
        root.setSpacing(4)

        # --- Top row: dot + title ---
        top = QHBoxLayout()
        top.setSpacing(6)

        self._dot = QLabel("●")
        self._dot.setFixedWidth(14)
        self._set_dot("gray")

        title = QLabel("WindowsMCP")
        title.setObjectName("title")

        top.addWidget(self._dot)
        top.addWidget(title)
        top.addStretch()
        root.addLayout(top)

        # --- State label ---
        self._state_label = QLabel("State: —")
        self._state_label.setObjectName("state")
        root.addWidget(self._state_label)

        # --- Screen label ---
        self._screen_label = QLabel("Screen: —")
        self._screen_label.setObjectName("screen")
        root.addWidget(self._screen_label)

        # --- Open Viewer button ---
        btn = QPushButton("Open Viewer")
        btn.setObjectName("open_viewer")
        btn.clicked.connect(self._open_viewer)
        root.addWidget(btn)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def update_status(self, status: dict) -> None:
        """Refresh toolbar labels from a status dict."""
        state = status.get("state", "unknown")
        screen = status.get("display", {}).get("name", "—")

        dot_key = state if state in _DOT_COLORS else "other"
        self._set_dot(dot_key)
        self._state_label.setText(f"State: {state}")
        self._screen_label.setText(f"Screen: {screen}")

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _set_dot(self, key: str) -> None:
        color = _DOT_COLORS.get(key, _DOT_DEFAULT)
        self._dot.setStyleSheet(f"color: {color}; font-size: 14px;")

    def _open_viewer(self) -> None:
        from ui.viewer import ViewerWindow  # lazy import to avoid circular deps

        if self._viewer is None or not self._viewer.isVisible():
            self._viewer = ViewerWindow()
        self._viewer.show()
        self._viewer.raise_()
        self._viewer.activateWindow()

    # ------------------------------------------------------------------
    # Drag support
    # ------------------------------------------------------------------

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = event.globalPosition().toPoint()

    def mouseMoveEvent(self, event) -> None:
        if self._drag_pos is not None and event.buttons() & Qt.MouseButton.LeftButton:
            delta = event.globalPosition().toPoint() - self._drag_pos
            self.move(self.pos() + delta)
            self._drag_pos = event.globalPosition().toPoint()

    def mouseReleaseEvent(self, event) -> None:
        self._drag_pos = None
