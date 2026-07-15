#!/usr/bin/env python3
"""
Wire Path Drawer — dibuja manualmente el camino del cable sobre la máscara.
Ctrl+Rueda: zoom  |  Click izq: añadir punto  |  Click der / BS: deshacer
"""
import cv2
import numpy as np
from PyQt5.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel,
                              QPushButton, QScrollArea)
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QImage, QPixmap, QPainter, QPen, QColor, QCursor


class WirePathCanvas(QLabel):
    """Canvas interactivo con soporte de zoom (Ctrl+Rueda)."""

    path_changed = pyqtSignal(list)   # [x, y] en coords imagen original
    zoom_changed  = pyqtSignal(float)

    MIN_ZOOM = 0.25
    MAX_ZOOM = 8.0

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        self.setCursor(QCursor(Qt.CrossCursor))
        self._fit_pixmap = None   # QPixmap a escala fit (sin zoom extra)
        self._fit_scale  = 1.0   # factor imagen→fit
        self._zoom       = 1.0   # factor zoom del usuario
        self._pts_image  = []    # [[x, y], ...] en coords imagen original

    @property
    def _eff(self) -> float:
        """Escala efectiva total: imagen → pantalla."""
        return self._fit_scale * self._zoom

    # ------------------------------------------------------------------
    # Setup
    # ------------------------------------------------------------------

    def set_background(self, img_bgr: np.ndarray, mask: np.ndarray = None,
                       max_dim: int = 850):
        """Prepara el fondo con overlay de máscara y escala al tamaño máximo."""
        if mask is not None:
            overlay = img_bgr.copy()
            overlay[mask > 0] = [0, 170, 0]
            bg = cv2.addWeighted(img_bgr, 0.65, overlay, 0.35, 0)
        else:
            bg = img_bgr.copy()

        h, w = bg.shape[:2]
        if max(h, w) > max_dim:
            self._fit_scale = max_dim / max(h, w)
            bg = cv2.resize(bg,
                            (int(w * self._fit_scale), int(h * self._fit_scale)),
                            interpolation=cv2.INTER_AREA)
        else:
            self._fit_scale = 1.0

        rgb  = cv2.cvtColor(bg, cv2.COLOR_BGR2RGB)
        qimg = QImage(bytes(rgb.data), rgb.shape[1], rgb.shape[0],
                      3 * rgb.shape[1], QImage.Format_RGB888)
        self._fit_pixmap = QPixmap.fromImage(qimg)
        self._zoom = 1.0
        self.clear_path()

    # ------------------------------------------------------------------
    # Path operations
    # ------------------------------------------------------------------

    def clear_path(self):
        self._pts_image.clear()
        self._redraw()
        self.path_changed.emit([])

    def undo_last(self):
        if self._pts_image:
            self._pts_image.pop()
            self._redraw()
            self.path_changed.emit(list(self._pts_image))

    def get_path(self) -> list:
        return list(self._pts_image)

    def set_path(self, pts: list):
        self._pts_image = [[int(p[0]), int(p[1])] for p in pts]
        self._redraw()

    # ------------------------------------------------------------------
    # Zoom
    # ------------------------------------------------------------------

    def zoom_by(self, factor: float):
        new_zoom = max(self.MIN_ZOOM, min(self.MAX_ZOOM, self._zoom * factor))
        if abs(new_zoom - self._zoom) > 1e-6:
            self._zoom = new_zoom
            self._redraw()
            self.zoom_changed.emit(self._zoom)

    def reset_zoom(self):
        self._zoom = 1.0
        self._redraw()
        self.zoom_changed.emit(self._zoom)

    # ------------------------------------------------------------------
    # Events
    # ------------------------------------------------------------------

    def mousePressEvent(self, event):
        if self._fit_pixmap is None:
            return
        eff = self._eff
        if event.button() == Qt.LeftButton:
            self._pts_image.append([int(event.x() / eff), int(event.y() / eff)])
            self._redraw()
            self.path_changed.emit(list(self._pts_image))
        elif event.button() == Qt.RightButton:
            self.undo_last()

    def wheelEvent(self, event):
        if event.modifiers() & Qt.ControlModifier:
            factor = 1.15 if event.angleDelta().y() > 0 else 1.0 / 1.15
            self.zoom_by(factor)
            event.accept()
        else:
            super().wheelEvent(event)

    # ------------------------------------------------------------------
    # Render
    # ------------------------------------------------------------------

    def _redraw(self):
        if self._fit_pixmap is None:
            return

        fw, fh = self._fit_pixmap.width(), self._fit_pixmap.height()
        dw = max(1, int(fw * self._zoom))
        dh = max(1, int(fh * self._zoom))

        pix = self._fit_pixmap.scaled(dw, dh, Qt.IgnoreAspectRatio,
                                      Qt.SmoothTransformation)
        self.setFixedSize(dw, dh)

        if not self._pts_image:
            self.setPixmap(pix)
            return

        eff  = self._eff
        dpts = [(int(x * eff), int(y * eff)) for x, y in self._pts_image]

        painter = QPainter(pix)
        painter.setRenderHint(QPainter.Antialiasing)

        lw = max(1, int(2 * self._zoom))
        painter.setPen(QPen(QColor(255, 90, 0), lw))
        for i in range(1, len(dpts)):
            painter.drawLine(dpts[i-1][0], dpts[i-1][1],
                             dpts[i][0],   dpts[i][1])

        rb = max(3, int(4 * self._zoom))
        for i, (px, py) in enumerate(dpts):
            first, last = (i == 0), (i == len(dpts) - 1)
            color = QColor(0, 220, 0) if first else (QColor(220, 0, 0) if last else QColor(255, 140, 0))
            r = int(rb * 1.5) if (first or last) else rb
            painter.setBrush(color)
            painter.setPen(QPen(color.darker(130), 1))
            painter.drawEllipse(px - r, py - r, 2 * r, 2 * r)
            if i % 5 == 0 and i > 0:
                painter.setPen(QPen(QColor(255, 255, 255), 1))
                painter.drawText(px + r + 2, py - 2, str(i))

        painter.end()
        self.setPixmap(pix)


class WirePathDrawerDialog(QDialog):
    """
    Diálogo para dibujar el camino del cable manualmente.
    Retorna lista de [x, y] en coordenadas de la imagen original.
    """

    def __init__(self, image: np.ndarray, mask: np.ndarray = None,
                 title: str = "Dibujador de cable",
                 initial_path: list = None, parent=None):
        super().__init__(parent)
        self.image = image
        self.mask  = mask
        self.result_path = []
        self.setWindowTitle(title)
        self.setMinimumSize(860, 680)
        self._setup_ui()
        if initial_path:
            self.canvas.set_path(initial_path)

    def _setup_ui(self):
        layout = QVBoxLayout(self)

        info = QLabel(
            "Click izquierdo: añadir punto  |  "
            "Click derecho / Backspace: deshacer  |  "
            "Ctrl+Rueda / botones 🔍: zoom  |  "
            "C: limpiar  |  0: reset zoom  |  Enter: confirmar"
        )
        info.setStyleSheet(
            "background:#2a2a2a; color:#ccc; padding:5px; border-radius:3px; font-size:10px;"
        )
        info.setWordWrap(True)
        layout.addWidget(info)

        self.stats_label = QLabel("Puntos: 0  |  Zoom: 100%")
        self.stats_label.setStyleSheet("color:#444; padding:3px; font-size:10px;")
        layout.addWidget(self.stats_label)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(False)
        self.canvas = WirePathCanvas()
        self.canvas.set_background(self.image, self.mask)
        self.canvas.path_changed.connect(self._update_stats)
        self.canvas.zoom_changed.connect(lambda _: self._update_stats(self.canvas.get_path()))
        self.scroll.setWidget(self.canvas)
        layout.addWidget(self.scroll, stretch=1)

        btns = QHBoxLayout()

        btn_zin = QPushButton("🔍+")
        btn_zin.setFixedWidth(48)
        btn_zin.setToolTip("Zoom in (Ctrl+Rueda ↑ o tecla +)")
        btn_zin.clicked.connect(lambda: self.canvas.zoom_by(1.3))
        btns.addWidget(btn_zin)

        btn_zout = QPushButton("🔍-")
        btn_zout.setFixedWidth(48)
        btn_zout.setToolTip("Zoom out (Ctrl+Rueda ↓ o tecla -)")
        btn_zout.clicked.connect(lambda: self.canvas.zoom_by(1 / 1.3))
        btns.addWidget(btn_zout)

        btn_zreset = QPushButton("1:1")
        btn_zreset.setFixedWidth(38)
        btn_zreset.setToolTip("Reset zoom (tecla 0)")
        btn_zreset.clicked.connect(self.canvas.reset_zoom)
        btns.addWidget(btn_zreset)

        btns.addSpacing(12)

        btn_undo = QPushButton("↩ Deshacer (BS)")
        btn_undo.clicked.connect(self.canvas.undo_last)
        btns.addWidget(btn_undo)

        btn_clear = QPushButton("🗑 Limpiar (C)")
        btn_clear.clicked.connect(self.canvas.clear_path)
        btns.addWidget(btn_clear)

        btns.addStretch()

        btn_cancel = QPushButton("Cancelar")
        btn_cancel.clicked.connect(self.reject)
        btns.addWidget(btn_cancel)

        self.btn_ok = QPushButton("✓ Confirmar path")
        self.btn_ok.setEnabled(False)
        self.btn_ok.setStyleSheet(
            "background-color:#4CAF50; color:white; font-weight:bold; padding:8px;"
        )
        self.btn_ok.clicked.connect(self._confirm)
        btns.addWidget(self.btn_ok)

        layout.addLayout(btns)

    def keyPressEvent(self, event):
        k = event.key()
        if k in (Qt.Key_Return, Qt.Key_Enter):
            if self.btn_ok.isEnabled():
                self._confirm()
        elif k == Qt.Key_Backspace:
            self.canvas.undo_last()
        elif k == Qt.Key_C:
            self.canvas.clear_path()
        elif k == Qt.Key_0:
            self.canvas.reset_zoom()
        elif k in (Qt.Key_Plus, Qt.Key_Equal):
            self.canvas.zoom_by(1.3)
        elif k == Qt.Key_Minus:
            self.canvas.zoom_by(1 / 1.3)
        else:
            super().keyPressEvent(event)

    def _update_stats(self, pts):
        n = len(pts)
        zoom_pct = int(self.canvas._zoom * 100)
        ready = n >= 2
        self.stats_label.setText(
            f"Puntos: {n}  —  {'listo ✓' if ready else 'añade al menos 2 puntos'}"
            f"  |  Zoom: {zoom_pct}%"
        )
        self.btn_ok.setEnabled(ready)

    def _confirm(self):
        self.result_path = self.canvas.get_path()
        self.accept()

    def get_path(self) -> list:
        return self.result_path
