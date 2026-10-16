#!/usr/bin/env python3
"""
Application-wide palette and stylesheet.

Lives apart from the main window because some dialogs appear before the
window exists: the startup checks in ``main.py`` can raise a message box
while the camera configuration is still loading. Those boxes used the
platform default, which on Windows is a white panel with a blue system
icon, so the first thing the application showed looked nothing like the
application.

Apply once on the QApplication and every dialog inherits it:

    from gui.theme import APP_QSS
    app.setStyleSheet(APP_QSS)
"""

from __future__ import annotations

# Palette, matching the one the pages use
BG_DEEP = "#0F172A"
BG_PANEL = "#1E293B"
BG_CARD = "#273548"
BG_SIDEBAR = "#0B1120"
ACCENT_CYAN = "#22D3EE"
ACCENT_BLUE = "#3B82F6"
TEXT_PRIMARY = "#E2E8F0"
TEXT_SECONDARY = "#94A3B8"
TEXT_DIM = "#64748B"
BORDER_SUBTLE = "#334155"

APP_QSS = f"""
QMessageBox, QInputDialog, QFileDialog {{
    background-color: {BG_PANEL};
    color: {TEXT_PRIMARY};
}}
QMessageBox QLabel, QInputDialog QLabel {{
    color: {TEXT_PRIMARY};
    font-size: 13px;
    background: transparent;
}}
QMessageBox QPushButton, QInputDialog QPushButton, QFileDialog QPushButton {{
    background-color: {BG_CARD};
    color: {TEXT_PRIMARY};
    border: 1px solid {BORDER_SUBTLE};
    border-radius: 5px;
    padding: 6px 18px;
    min-width: 76px;
    font-size: 12px;
}}
QMessageBox QPushButton:hover, QInputDialog QPushButton:hover {{
    background-color: #3B4B60;
}}
QMessageBox QPushButton:default, QInputDialog QPushButton:default {{
    background-color: {ACCENT_BLUE};
    border-color: {ACCENT_BLUE};
    color: white;
    font-weight: bold;
}}
QMessageBox QPushButton:default:hover {{
    background-color: #60A5FA;
}}
QToolTip {{
    background-color: {BG_SIDEBAR};
    color: {TEXT_PRIMARY};
    border: 1px solid {BORDER_SUBTLE};
    padding: 5px 7px;
    font-size: 12px;
}}
"""
