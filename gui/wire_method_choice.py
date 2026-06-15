#!/usr/bin/env python3
"""
Wire Method Choice Dialog — elige entre 3 métodos para trazar el camino del cable.

Opciones:
  1) SmartWireTracker   — algoritmo automático DFS + backtracking
  2) Dibujo manual      — el usuario dibuja el path punto a punto
  3) IA                 — deshabilitada hasta tener dataset entrenado

Después de obtener el resultado con la opción 1 ó 2, se puede guardar
imagen + máscara + path en el dataset de entrenamiento IA.
"""
import cv2
import numpy as np
from PyQt5.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel,
                              QPushButton, QGroupBox, QMessageBox, QFrame,
                              QSizePolicy)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QImage, QPixmap, QFont


# ── helpers ────────────────────────────────────────────────────────────────

def _to_pixmap(img_bgr: np.ndarray, max_dim: int = 480) -> QPixmap:
    h, w = img_bgr.shape[:2]
    if max(h, w) > max_dim:
        s = max_dim / max(h, w)
        img_bgr = cv2.resize(img_bgr, (int(w * s), int(h * s)))
    rgb = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)
    h, w = rgb.shape[:2]
    return QPixmap.fromImage(QImage(bytes(rgb.data), w, h, 3 * w, QImage.Format_RGB888))


def _make_preview(img_bgr, mask, start_pt=None, end_pt=None) -> np.ndarray:
    overlay = img_bgr.copy()
    overlay[mask > 0] = [0, 170, 0]
    preview = cv2.addWeighted(img_bgr, 0.65, overlay, 0.35, 0)
    h, w = preview.shape[:2]
    r = max(6, min(w, h) // 150)
    if start_pt:
        cv2.circle(preview, (int(start_pt[0]), int(start_pt[1])), r, (0, 255, 0), -1)
    if end_pt:
        cv2.circle(preview, (int(end_pt[0]), int(end_pt[1])), r, (0, 0, 255), -1)
    return preview


# ── dialog ─────────────────────────────────────────────────────────────────

class WireMethodChoiceDialog(QDialog):
    """
    Diálogo principal de elección de método.
    Reemplaza WireTrackingVisualizationDialog en el flujo de ProcessingDialog.
    """

    def __init__(self, left_img, right_img, mask_left, mask_right,
                 start_left, end_left, start_right, end_right, parent=None):
        super().__init__(parent)
        self.left_img = left_img
        self.right_img = right_img
        self.mask_left = mask_left
        self.mask_right = mask_right
        self.start_left = start_left
        self.end_left = end_left
        self.start_right = start_right
        self.end_right = end_right
        self._result = None           # dict compatible con wire_tracking_result

        from utils.dataset_manager import DatasetManager
        self._dm = DatasetManager()

        self.setWindowTitle("Método de Wire Tracking")
        self.setMinimumSize(960, 580)
        self._setup_ui()

    # ── UI ────────────────────────────────────────────────────────────

    def _setup_ui(self):
        root = QHBoxLayout(self)
        root.setSpacing(10)

        # ── Panel izquierdo: preview ──────────────────────────────────
        left = QVBoxLayout()

        lbl_title = QLabel("Vista previa — imagen izquierda + máscara")
        lbl_title.setFont(QFont("Arial", 10, QFont.Bold))
        left.addWidget(lbl_title)

        self.preview_label = QLabel()
        self.preview_label.setAlignment(Qt.AlignCenter)
        self.preview_label.setStyleSheet(
            "background:#1a1a1a; border:1px solid #444; border-radius:4px;"
        )
        self.preview_label.setMinimumSize(460, 340)
        self.preview_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        preview_img = _make_preview(self.left_img, self.mask_left,
                                    self.start_left, self.end_left)
        self.preview_label.setPixmap(_to_pixmap(preview_img, 460))
        left.addWidget(self.preview_label, stretch=1)

        self.status_label = QLabel("Sin método elegido")
        self.status_label.setAlignment(Qt.AlignCenter)
        self.status_label.setStyleSheet(
            "color:#888; font-style:italic; padding:4px; font-size:10px;"
        )
        left.addWidget(self.status_label)

        root.addLayout(left, stretch=2)

        # ── Panel derecho: opciones ───────────────────────────────────
        right = QVBoxLayout()
        right.setSpacing(8)

        # --- Opción 1 ---
        g1 = QGroupBox("Opción 1 — SmartWireTracker (automático)")
        l1 = QVBoxLayout()
        d1 = QLabel(
            "Trazado automático con DFS + backtracking.\n"
            "Funciona bien en casos sin enredos complejos."
        )
        d1.setWordWrap(True)
        d1.setStyleSheet("color:#555; font-size:10px;")
        l1.addWidget(d1)
        btn1 = QPushButton("▶ Ejecutar SmartWireTracker")
        btn1.setStyleSheet(
            "background:#2196F3; color:white; font-weight:bold; padding:8px; border-radius:4px;"
        )
        btn1.clicked.connect(self._run_tracker)
        l1.addWidget(btn1)
        g1.setLayout(l1)
        right.addWidget(g1)

        # --- Opción 2 ---
        g2 = QGroupBox("Opción 2 — Dibujo manual")
        l2 = QVBoxLayout()
        d2 = QLabel(
            "Tú dibujas el camino correcto haciendo click en la imagen.\n"
            "Ideal para casos complejos o para etiquetar el dataset IA."
        )
        d2.setWordWrap(True)
        d2.setStyleSheet("color:#555; font-size:10px;")
        l2.addWidget(d2)
        btn2 = QPushButton("✏️ Dibujar manualmente")
        btn2.setStyleSheet(
            "background:#FF9800; color:white; font-weight:bold; padding:8px; border-radius:4px;"
        )
        btn2.clicked.connect(self._run_manual)
        l2.addWidget(btn2)
        g2.setLayout(l2)
        right.addWidget(g2)

        # --- Opción 3 ---
        g3 = QGroupBox("Opción 3 — IA Wire Tracker (no disponible aún)")
        l3 = QVBoxLayout()
        count = self._dm.count()
        d3 = QLabel(
            f"Modelo de IA que aprende de tu dataset.\n"
            f"Dataset actual: {count} muestras — necesita ~100 para entrenar."
        )
        d3.setWordWrap(True)
        d3.setStyleSheet("color:#aaa; font-size:10px;")
        l3.addWidget(d3)
        self.btn_ai = QPushButton("🤖 IA Wire Tracker (próximamente)")
        self.btn_ai.setEnabled(False)
        self.btn_ai.setStyleSheet("padding:8px; border-radius:4px;")
        l3.addWidget(self.btn_ai)
        g3.setLayout(l3)
        right.addWidget(g3)

        # --- Separador ---
        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet("color:#ccc; margin:4px 0;")
        right.addWidget(sep)

        # --- Dataset ---
        gds = QGroupBox("Dataset IA")
        lds = QVBoxLayout()
        self.ds_count_label = QLabel(f"Muestras guardadas: {count}")
        self.ds_count_label.setStyleSheet("font-size:10px;")
        lds.addWidget(self.ds_count_label)
        self.btn_ds = QPushButton("💾 Guardar en Dataset")
        self.btn_ds.setEnabled(False)
        self.btn_ds.setStyleSheet(
            "background:#607D8B; color:white; font-weight:bold; padding:8px; border-radius:4px;"
        )
        self.btn_ds.clicked.connect(self._save_to_dataset)
        lds.addWidget(self.btn_ds)
        gds.setLayout(lds)
        right.addWidget(gds)

        right.addStretch()

        # --- Botones finales ---
        final = QHBoxLayout()
        btn_cancel = QPushButton("Cancelar")
        btn_cancel.clicked.connect(self.reject)
        final.addWidget(btn_cancel)

        self.btn_use = QPushButton("✓ Usar este path →")
        self.btn_use.setEnabled(False)
        self.btn_use.setStyleSheet(
            "background:#4CAF50; color:white; font-weight:bold; padding:8px; border-radius:4px;"
        )
        self.btn_use.clicked.connect(self.accept)
        final.addWidget(self.btn_use)
        right.addLayout(final)

        root.addLayout(right, stretch=1)

    # ── métodos ────────────────────────────────────────────────────────

    def _run_tracker(self):
        """Opción 1: ejecuta SmartWireTracker con animación."""
        from gui.processing_dialog import WireTrackingVisualizationDialog
        dlg = WireTrackingVisualizationDialog(
            self.left_img, self.right_img,
            self.mask_left, self.mask_right,
            self.start_left, self.end_left,
            self.start_right, self.end_right,
            self
        )
        dlg.exec_()
        res = dlg.get_results()
        if res and res.get('success'):
            self._result = res
            self._on_result("SmartWireTracker")
        else:
            QMessageBox.warning(self, "Incompleto",
                "El tracker no completó el path correctamente.\n"
                "Puedes intentar con Dibujo manual.")

    def _run_manual(self):
        """Opción 2: dibujador manual, primero izquierda luego derecha."""
        from gui.wire_path_drawer import WirePathDrawerDialog

        dlg_l = WirePathDrawerDialog(
            self.left_img, self.mask_left,
            title="Dibujar camino — IMAGEN IZQUIERDA",
            parent=self
        )
        if dlg_l.exec_() != QDialog.Accepted:
            return
        path_left = dlg_l.get_path()

        dlg_r = WirePathDrawerDialog(
            self.right_img, self.mask_right,
            title="Dibujar camino — IMAGEN DERECHA",
            parent=self
        )
        if dlg_r.exec_() != QDialog.Accepted:
            return
        path_right = dlg_r.get_path()

        self._result = {
            'success': True,
            'left': {
                'path': path_left, 'coverage': 1.0,
                'dt_profile': None, 'decision_points_2d': [],
            },
            'right': {
                'path': path_right, 'coverage': 1.0,
                'dt_profile': None, 'decision_points_2d': [],
            },
        }
        self._on_result("Dibujo manual")

    def _on_result(self, method: str):
        """Actualiza UI cuando hay un resultado listo."""
        if not self._result:
            return
        n_l = len(self._result['left']['path'])
        n_r = len(self._result['right']['path'])
        self.status_label.setText(
            f"✓ {method} — izq: {n_l} pts  |  der: {n_r} pts"
        )
        self.status_label.setStyleSheet(
            "color:#2E7D32; font-weight:bold; padding:4px; font-size:10px;"
        )
        self.btn_ds.setEnabled(True)
        self.btn_ds.setStyleSheet(
            "background:#FF9800; color:white; font-weight:bold; padding:8px; border-radius:4px;"
        )
        self.btn_use.setEnabled(True)

    def _save_to_dataset(self):
        """Guarda imagen izq + máscara izq + paths en el dataset."""
        is_dup, existing_id = self._dm.is_duplicate(self.left_img)
        if is_dup:
            reply = QMessageBox.question(
                self, "Imagen duplicada",
                f"Esta imagen ya existe en el dataset como muestra #{existing_id:04d}.\n"
                "¿Guardar de todas formas como nueva muestra?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No
            )
            if reply != QMessageBox.Yes:
                return

        wire_paths_json = None
        if self._result:
            wire_paths_json = {
                'left': self._result['left']['path'],
                'right': self._result['right']['path'],
            }

        sample_id = self._dm.save_sample(
            self.left_img, self.mask_left,
            wire_paths=wire_paths_json
        )
        count = self._dm.count()
        self.ds_count_label.setText(f"Muestras guardadas: {count}")
        # Actualizar tooltip del botón IA con nuevo conteo
        self.btn_ai.setToolTip(
            f"Dataset actual: {count} muestras — necesita ~100 para entrenar."
        )
        self.btn_ds.setEnabled(False)   # evitar guardado doble

        print(f"✓ Dataset: muestra #{sample_id:04d} guardada "
              f"(imagen + máscara + {'path' if wire_paths_json else 'sin path'})")

        QMessageBox.information(
            self, "Guardado en dataset",
            f"Muestra #{sample_id:04d} guardada correctamente.\n"
            f"Total en dataset: {count} muestras."
        )

    def get_results(self):
        return self._result
