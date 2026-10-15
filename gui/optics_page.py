#!/usr/bin/env python3
"""
Optics page: depth of field, field of view and sub-pixel observability.

Wraps the standalone tool in ``calculate_cam/camera_dof_visualizer.py`` so it
lives inside the main application instead of being a separate program. It is
the tool that answers the questions the rest of the system depends on, and
keeping it outside meant those answers were computed somewhere the operator
could not reach while working:

  * how many pixels the tether occupies at a given distance,
  * where the depth of field starts and ends for a chosen focus distance,
  * at what range the target drops below one pixel and detection stops being
    a geometric problem.

The tool is embedded by taking the central widget out of its own window
rather than by rewriting it, so there is a single implementation of the
optics maths and no chance of the two drifting apart. The window object is
kept alive as an attribute because it owns the signal connections.
"""

from __future__ import annotations

from PyQt5.QtWidgets import QLabel, QVBoxLayout, QWidget

from utils.logger import get_logger

logger = get_logger(__name__)

BG_DEEP = "#0F172A"
TEXT_SECONDARY = "#94A3B8"
RED_OFF = "#EF4444"


class OpticsPage(QWidget):
    """Hosts the depth of field visualiser as one page of the application."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet(f"background-color: {BG_DEEP};")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self._tool = None

        try:
            from calculate_cam.camera_dof_visualizer import (
                DARK_STYLE, MainWindow as DoFWindow,
            )
            self._tool = DoFWindow()
            inner = self._tool.centralWidget()
            # Reparenting drops the stylesheet that lived on the window, so
            # it is applied here instead.
            inner.setParent(None)
            inner.setStyleSheet(DARK_STYLE)
            layout.addWidget(inner)
            logger.info("Optics page loaded")
        except Exception as exc:                          # noqa: BLE001
            # matplotlib is an optional dependency on the Pi. A missing
            # optics tool must not stop the application from starting.
            logger.warning("Optics page unavailable: %s", exc)
            msg = QLabel(
                "The optics tool could not be loaded.\n\n"
                f"{exc}\n\n"
                "It needs matplotlib. Install it with:\n"
                "    pip3 install matplotlib\n\n"
                "Everything else in the application works without it."
            )
            msg.setWordWrap(True)
            msg.setStyleSheet(
                f"color: {TEXT_SECONDARY}; font-size: 13px; padding: 40px;")
            layout.addWidget(msg)
            layout.addStretch()
