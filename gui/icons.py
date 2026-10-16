#!/usr/bin/env python3
"""
Vector icons for the interface.

The application used Unicode glyphs for navigation and buttons. Several of
them have no coverage in the fonts shipped with Raspberry Pi OS, so on the
target machine they rendered as empty boxes. The replacements here are drawn
as SVG paths inside the file, which means they look the same on every system
and need no font, no icon pack and no network.

All of them share one grammar: a 24 by 24 box, strokes only, 2 px wide, round
caps and joins, and the colour injected at build time. They stay legible at
the 16 px used on buttons and at the 22 px used in the sidebar.

Usage:
    from gui.icons import get_icon
    button.setIcon(get_icon("play", "#E2E8F0"))
"""

from __future__ import annotations

from typing import Dict

from PyQt5.QtCore import QByteArray, QSize, Qt
from PyQt5.QtGui import QIcon, QPainter, QPixmap
from PyQt5.QtSvg import QSvgRenderer

#: Icon bodies. Everything inside a 24x24 viewBox. ``{c}`` is the stroke
#: colour, substituted when the icon is built.
_BODIES: Dict[str, str] = {
    # Navigation
    "dashboard": (
        '<rect x="3" y="3" width="7.5" height="7.5" rx="1.5"/>'
        '<rect x="13.5" y="3" width="7.5" height="7.5" rx="1.5"/>'
        '<rect x="3" y="13.5" width="7.5" height="7.5" rx="1.5"/>'
        '<rect x="13.5" y="13.5" width="7.5" height="7.5" rx="1.5"/>'
    ),
    # Crosshair on a target: calibration is about where the optical axis sits
    "calibration": (
        '<circle cx="12" cy="12" r="8"/>'
        '<circle cx="12" cy="12" r="3"/>'
        '<path d="M12 1.5v4M12 18.5v4M1.5 12h4M18.5 12h4"/>'
    ),
    # Stacked planes: a pair of images becoming a reconstruction
    "processing": (
        '<path d="M12 2.5 21 7l-9 4.5L3 7z"/>'
        '<path d="M3 12l9 4.5L21 12"/>'
        '<path d="M3 17l9 4.5L21 17"/>'
    ),
    # Chip
    "ai": (
        '<rect x="7" y="7" width="10" height="10" rx="2"/>'
        '<path d="M10 2.5v4M14 2.5v4M10 17.5v4M14 17.5v4'
        'M2.5 10h4M2.5 14h4M17.5 10h4M17.5 14h4"/>'
    ),
    # Lens aperture: the optics calculator
    "optics": (
        '<circle cx="12" cy="12" r="9"/>'
        '<path d="M12 3v9l7.8 4.5M12 12L4.2 16.5M12 12l7.8-4.5"/>'
    ),
    # Actions
    "play": '<path d="M7 4.5l12 7.5-12 7.5z" fill="{c}" stroke-linejoin="round"/>',
    "stop": '<rect x="5.5" y="5.5" width="13" height="13" rx="2" fill="{c}"/>',
    "check": '<path d="M4.5 12.5l5 5 10-11"/>',
    "cross": '<path d="M5.5 5.5l13 13M18.5 5.5l-13 13"/>',
    "folder": (
        '<path d="M3 6.5a1.5 1.5 0 0 1 1.5-1.5h4.3l2 2.5h7.7A1.5 1.5 0 0 1 20 9'
        'v9a1.5 1.5 0 0 1-1.5 1.5h-14A1.5 1.5 0 0 1 3 18z"/>'
    ),
    "camera": (
        '<path d="M3 8.5A1.5 1.5 0 0 1 4.5 7h3L9 4.5h6L16.5 7h3A1.5 1.5 0 0 1 21 8.5'
        'v10A1.5 1.5 0 0 1 19.5 20h-15A1.5 1.5 0 0 1 3 18.5z"/>'
        '<circle cx="12" cy="13" r="3.5"/>'
    ),
    # Arrows pointing out: take over the whole window
    "expand": (
        '<path d="M9.5 3.5h-6v6M14.5 3.5h6v6M9.5 20.5h-6v-6M14.5 20.5h6v-6"/>'
        '<path d="M3.5 3.5l6 6M20.5 3.5l-6 6M3.5 20.5l6-6M20.5 20.5l-6-6"/>'
    ),
    "collapse": (
        '<path d="M3.5 9.5h6v-6M20.5 9.5h-6v-6M3.5 14.5h6v6M20.5 14.5h-6v6"/>'
    ),
    "back": '<path d="M19 12H5M11 6l-6 6 6 6"/>',
    "warning": (
        '<path d="M12 3.5 22 20.5H2z"/>'
        '<path d="M12 9.5v5"/><circle cx="12" cy="17.6" r="0.3" fill="{c}"/>'
    ),
    "clock": '<circle cx="12" cy="12" r="8.5"/><path d="M12 7v5.3l3.4 2"/>',
    # Panel con una barra lateral: el conmutador de la columna
    "panel": (
        '<rect x="3" y="4" width="18" height="16" rx="2"/>'
        '<path d="M9.5 4v16"/>'
    ),
    "board": (
        '<rect x="3.5" y="3.5" width="17" height="17" rx="1.5"/>'
        '<path d="M9.17 3.5v17M14.83 3.5v17M3.5 9.17h17M3.5 14.83h17"/>'
    ),
}

_TEMPLATE = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" '
    'fill="none" stroke="{c}" stroke-width="2" '
    'stroke-linecap="round" stroke-linejoin="round">{body}</svg>'
)

_cache: Dict[tuple, QIcon] = {}


def icon_pixmap(name: str, color: str = "#E2E8F0", size: int = 20) -> QPixmap:
    """Render one icon to a pixmap at the requested size and colour."""
    body = _BODIES.get(name)
    if body is None:
        return QPixmap()
    svg = _TEMPLATE.format(c=color, body=body.replace("{c}", color))

    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    renderer = QSvgRenderer(QByteArray(svg.encode("utf-8")))
    painter = QPainter(pm)
    painter.setRenderHint(QPainter.Antialiasing, True)
    renderer.render(painter)
    painter.end()
    return pm


def get_icon(name: str, color: str = "#E2E8F0", size: int = 20) -> QIcon:
    """Return a cached QIcon. Unknown names give an empty icon, never raise."""
    key = (name, color, size)
    if key not in _cache:
        pm = icon_pixmap(name, color, size)
        _cache[key] = QIcon(pm) if not pm.isNull() else QIcon()
    return _cache[key]


def available() -> tuple:
    """Names that can be requested. Handy for a smoke test."""
    return tuple(sorted(_BODIES))
