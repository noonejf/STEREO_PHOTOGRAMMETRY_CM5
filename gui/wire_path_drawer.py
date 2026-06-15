#!/usr/bin/env python3
"""
Wire Path Drawer — dibuja manualmente el camino del cable sobre la máscara.
Click izquierdo agrega puntos, click derecho deshace el último.
"""
import cv2
import numpy as np
from PyQt5.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel,
                              QPushButton, QScrollArea)
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QImage, QPixmap, QPainter, QPen, QColor, QCursor


class WirePathCanvas(QLabel):
    """Canvas interactivo para dibujar waypoints sobre la imagen."""
    path_changed = pyqtSignal(list)   # emite puntos en coords de imagen original

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        self.setCursor(QCursor(Qt.CrossCursor))
        self._base_pixmap = None
        self._scale = 1.0
        self._pts_display = []   # (x, y) en pantalla
        self._pts_image = []     # [x, y] en imagen original

    def set_background(self, img_bgr: np.ndarray, mask: np.ndarray = None,
                       max_dim: int = 900):
        """Fondo = imagen original con overlay verde de la máscara (opcional)."""
        if mask is not None:
            overlay = img_bgr.copy()
            overlay[mask > 0] = [0, 170, 0]
            bg = cv2.addWeighted(img_bgr, 0.65, overlay, 0.35, 0)
        else:
            bg = img_bgr.copy()

        h, w = bg.shape[:2]
        if max(h, w) > max_dim:
            self._scale = max_dim / max(h, w)
            bg = cv2.resize(bg, (int(w * self._scale), int(h * self._scale)),
                            interpolation=cv2.INTER_AREA)
        else:
            self._scale = 1.0

        rgb = cv2.cvtColor(bg, cv2.COLOR_BGR2RGB)
        qimg = QImage(bytes(rgb.data), rgb.shape[1], rgb.shape[0],
                      3 * rgb.shape[1], QImage.Format_RGB888)
        self._base_pixmap = QPixmap.fromImage(qimg)
        self.setFixedSize(self._base_pixmap.size())
        self.clear_path()

    def clear_path(self):
        self._pts_display.clear()
        self._pts_image.clear()
        self._redraw()
        self.path_changed.emit([])

    def undo_last(self):
        if self._pts_display:
            self._pts_display.pop()
            self._pts_image.pop()
            self._redraw()
            self.path_changed.emit(list(self._pts_image))

    def get_path(self):
        return list(self._pts_image)

    def set_path(self, image_pts: list):
        """Carga un path existente para editar."""
        self._pts_image = [[p[0], p[1]] for p in image_pts]
        self._pts_display = [
            (int(x * self._scale), int(y * self._scale))
            for x, y in self._pts_image
        ]
        self._redraw()

    # ------------------------------------------------------------------
    # Mouse
    # ------------------------------------------------------------------

    def mousePressEvent(self, event):
        if self._base_pixmap is None:
            return
        if event.button() == Qt.LeftButton:
            dx, dy = event.x(), event.y()
            self._pts_display.append((dx, dy))
            self._pts_image.append([int(dx / self._scale), int(dy / self._scale)])
            self._redraw()
            self.path_changed.emit(list(self._pts_image))
        elif event.button() == Qt.RightButton:
            self.undo_last()

    # ------------------------------------------------------------------
    # Render
    # ------------------------------------------------------------------

    def _redraw(self):
        if self._base_pixmap is None:
            return
        pix = self._base_pixmap.copy()
        if not self._pts_display:
            self.setPixmap(pix)
            return

        painter = QPainter(pix)
        painter.setRenderHint(QPainter.Antialiasing)

        # Línea naranja
        painter.setPen(QPen(QColor(255, 90, 0), 2))
        for i in range(1, len(self._pts_display)):
            x1, y1 = self._pts_display[i - 1]
            x2, y2 = self._pts_display[i]
            painter.drawLine(x1, y1, x2, y2)

        # Puntos: verde=inicio, rojo=fin, naranja=intermedios
        for i, (px, py) in enumerate(self._pts_display):
            is_first = i == 0
            is_last = i == len(self._pts_display) - 1
            color = QColor(0, 220, 0) if is_first else (QColor(220, 0, 0) if is_last else QColor(255, 140, 0))
            r = 6 if (is_first or is_last) else 4
            painter.setBrush(color)
            painter.setPen(QPen(color.darker(130), 1))
            painter.drawEllipse(px - r, py - r, 2 * r, 2 * r)
            if i % 5 == 0 and i > 0:
                painter.setPen(QPen(QColor(255, 255, 255), 1))
                painter.drawText(px + 7, py - 3, str(i))

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
        self.mask = mask
        self.result_path = []
        self.setWindowTitle(title)
        self.setMinimumSize(820, 660)
        self._setup_ui()
        if initial_path:
            self.canvas.set_path(initial_path)

    def _setup_ui(self):
        layout = QVBoxLayout(self)

        info = QLabel(
            "Click izquierdo: añadir punto  |  "
            "Click derecho / Backspace: deshacer último  |  "
            "C: limpiar todo  |  Enter: confirmar path"
        )
        info.setStyleSheet(
            "background:#2a2a2a; color:#ccc; padding:5px; border-radius:3px; font-size:10px;"
        )
        info.setWordWrap(True)
        layout.addWidget(info)

        self.stats_label = QLabel("Puntos: 0  —  añade al menos 2 para confirmar")
        self.stats_label.setStyleSheet("color:#555; padding:3px;")
        layout.addWidget(self.stats_label)

        scroll = QScrollArea()
        scroll.setWidgetResizable(False)
        self.canvas = WirePathCanvas()
        self.canvas.set_background(self.image, self.mask)
        self.canvas.path_changed.connect(self._on_path_changed)
        scroll.setWidget(self.canvas)
        layout.addWidget(scroll, stretch=1)

        btns = QHBoxLayout()

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
        if event.key() in (Qt.Key_Return, Qt.Key_Enter):
            if self.btn_ok.isEnabled():
                self._confirm()
        elif event.key() == Qt.Key_Backspace:
            self.canvas.undo_last()
        elif event.key() == Qt.Key_C:
            self.canvas.clear_path()
        else:
            super().keyPressEvent(event)

    def _on_path_changed(self, pts):
        n = len(pts)
        self.stats_label.setText(
            f"Puntos: {n}  —  {'listo para confirmar' if n >= 2 else 'añade al menos 2 puntos'}"
        )
        self.btn_ok.setEnabled(n >= 2)

    def _confirm(self):
        self.result_path = self.canvas.get_path()
        self.accept()

    def get_path(self):
        return self.result_path
