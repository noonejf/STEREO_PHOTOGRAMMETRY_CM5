#!/usr/bin/env python3
import cv2
import numpy as np

from PyQt5.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel,
                              QPushButton, QListWidget, QListWidgetItem,
                              QMessageBox, QWidget, QLineEdit, QSplitter,
                              QTextEdit, QScrollArea, QFrame)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QImage, QPixmap

_DARK_QSS = """
QDialog, QWidget {
    background-color: #0F172A;
    color: #E2E8F0;
    font-family: "Segoe UI", "Roboto", sans-serif;
    font-size: 13px;
}
QGroupBox {
    background-color: #1E293B;
    border: 1px solid #334155;
    border-radius: 8px;
    margin-top: 14px;
    padding: 14px 10px 10px 10px;
}
QGroupBox::title {
    subcontrol-origin: margin;
    subcontrol-position: top left;
    padding: 2px 12px;
    color: #22D3EE;
    font-weight: bold;
}
QLabel { color: #E2E8F0; background-color: transparent; }
QPushButton {
    background-color: #3B82F6;
    color: white;
    border: none;
    border-radius: 6px;
    padding: 8px 16px;
    font-weight: 600;
}
QPushButton:hover   { background-color: #60A5FA; }
QPushButton:pressed { background-color: #2563EB; }
QListWidget {
    background-color: #0F172A;
    color: #E2E8F0;
    border: 1px solid #334155;
    border-radius: 4px;
}
QListWidget::item:selected { background-color: #3B82F6; }
QLineEdit {
    background-color: #273548;
    color: #E2E8F0;
    border: 1px solid #334155;
    border-radius: 6px;
    padding: 5px 10px;
}
QScrollBar:vertical {
    background: #0F172A; width: 8px; border-radius: 4px;
}
QScrollBar::handle:vertical {
    background: #334155; border-radius: 4px; min-height: 30px;
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0px; }
QScrollArea { border: none; background: transparent; }
QTextEdit {
    background-color: #0F172A;
    color: #A5F3FC;
    border: 1px solid #334155;
    border-radius: 6px;
    padding: 8px;
    font-family: "Consolas", monospace;
    font-size: 12px;
}
QSplitter::handle { background-color: #334155; }
"""

PREVIEW_W = 480   # ancho fijo del thumbnail
PREVIEW_H = 360   # alto máximo (se respeta proporción)


def _to_qpixmap(img_bgr: np.ndarray) -> QPixmap:
    rgb = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)
    h, w = rgb.shape[:2]
    qimg = QImage(bytes(rgb.data), w, h, 3 * w, QImage.Format_RGB888)
    return QPixmap.fromImage(qimg)


def _fit_pixmap(img_bgr: np.ndarray) -> QPixmap:
    """Convierte a QPixmap escalado para que quepa en PREVIEW_W × PREVIEW_H con proporción."""
    return _to_qpixmap(img_bgr).scaled(
        PREVIEW_W, PREVIEW_H, Qt.KeepAspectRatio, Qt.SmoothTransformation
    )


def _make_overlay(img_bgr: np.ndarray, mask_gray: np.ndarray) -> np.ndarray:
    overlay = img_bgr.copy()
    overlay[mask_gray > 0] = [0, 220, 0]
    return cv2.addWeighted(img_bgr, 0.6, overlay, 0.4, 0)


def _draw_path(img_bgr: np.ndarray, path_points: list) -> np.ndarray:
    """Dibuja el camino del cable sobre la imagen: línea amarilla + inicio verde + fin rojo."""
    if not path_points or len(path_points) < 2:
        return img_bgr.copy()
    result = img_bgr.copy()
    pts = [(int(x), int(y)) for x, y in path_points]
    r = max(8, min(img_bgr.shape[:2]) // 60)
    for i in range(len(pts) - 1):
        cv2.line(result, pts[i], pts[i + 1], (0, 200, 255), 2, cv2.LINE_AA)
    cv2.circle(result, pts[0],  r, (0, 255, 0), -1)
    cv2.circle(result, pts[-1], r, (0, 0, 255), -1)
    font, scale, thick = cv2.FONT_HERSHEY_SIMPLEX, 0.45, 1
    cv2.putText(result, "START", (pts[0][0] + r + 2,  pts[0][1] + 5),  font, scale, (0, 255, 0), thick)
    cv2.putText(result, "END",   (pts[-1][0] + r + 2, pts[-1][1] + 5), font, scale, (0, 0, 255), thick)
    return result


def _preview_label() -> QLabel:
    lbl = QLabel()
    lbl.setFixedSize(PREVIEW_W, PREVIEW_H)
    lbl.setAlignment(Qt.AlignCenter)
    lbl.setStyleSheet(
        "background: #1E293B; border: 1px solid #334155; border-radius: 6px;"
    )
    return lbl


def _section_title(text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setStyleSheet("color: #22D3EE; font-weight: bold; font-size: 12px;")
    return lbl


class DatasetViewerDialog(QDialog):
    """Visor interactivo del dataset de entrenamiento."""

    def __init__(self, dataset_manager, parent=None):
        super().__init__(parent)
        self.dm = dataset_manager
        self.setWindowTitle(f"Dataset Viewer — {self.dm.base_dir}")
        self.setMinimumSize(1200, 750)
        self.setStyleSheet(_DARK_QSS)
        self.showMaximized()
        self._setup_ui()
        self._refresh_list()

    # ------------------------------------------------------------------
    # UI setup
    # ------------------------------------------------------------------

    def _setup_ui(self):
        root = QHBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(6)

        splitter = QSplitter(Qt.Horizontal)
        root.addWidget(splitter)

        # ── LEFT PANEL: lista + botones ──────────────────────────────
        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(4, 4, 4, 4)
        left_layout.setSpacing(6)

        self.count_label = QLabel("0 samples")
        self.count_label.setStyleSheet("color: #E2E8F0; font-weight: bold; font-size: 14px;")
        left_layout.addWidget(self.count_label)

        self.list_widget = QListWidget()
        self.list_widget.setMinimumWidth(220)
        self.list_widget.currentRowChanged.connect(self._on_select)
        left_layout.addWidget(self.list_widget)

        left_layout.addWidget(QLabel("Notes for selected:"))
        self.notes_edit = QLineEdit()
        self.notes_edit.setPlaceholderText("optional annotation...")
        self.notes_edit.returnPressed.connect(self._save_notes)
        left_layout.addWidget(self.notes_edit)

        btn_save_notes = QPushButton("💬 Save Notes")
        btn_save_notes.clicked.connect(self._save_notes)
        left_layout.addWidget(btn_save_notes)

        btn_delete = QPushButton("🗑️ Delete Selected")
        btn_delete.setStyleSheet(
            "background-color: #7F1D1D; color: #FCA5A5; font-weight: bold;"
            " border-radius: 6px; padding: 8px;"
        )
        btn_delete.clicked.connect(self._delete_selected)
        left_layout.addWidget(btn_delete)

        btn_summary = QPushButton("📋 Print Summary")
        btn_summary.setStyleSheet(
            "background-color: #273548; color: #E2E8F0; border-radius: 6px; padding: 8px;"
        )
        btn_summary.clicked.connect(self._print_summary)
        left_layout.addWidget(btn_summary)

        btn_close = QPushButton("Close")
        btn_close.setStyleSheet(
            "background-color: #273548; color: #E2E8F0; border-radius: 6px; padding: 8px;"
        )
        btn_close.clicked.connect(self.accept)
        left_layout.addWidget(btn_close)

        splitter.addWidget(left)

        # ── RIGHT PANEL: info + previews (scroll) ────────────────────
        right_scroll = QScrollArea()
        right_scroll.setWidgetResizable(True)
        right_scroll.setFrameShape(QFrame.NoFrame)
        right_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        right_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)

        right = QWidget()
        self.right_layout = QVBoxLayout(right)
        self.right_layout.setContentsMargins(4, 4, 4, 4)
        self.right_layout.setSpacing(10)

        self.info_label = QLabel("Select a sample to preview")
        self.info_label.setAlignment(Qt.AlignCenter)
        self.info_label.setStyleSheet(
            "color: #94A3B8; font-size: 13px; padding: 6px;"
        )
        self.right_layout.addWidget(self.info_label)

        # ── Row 1: left camera ────────────────────────────────────────
        left_row_title = _section_title("LEFT Camera")
        self.right_layout.addWidget(left_row_title)

        left_row = QHBoxLayout()
        left_row.setSpacing(8)

        left_img_col = QVBoxLayout()
        left_img_col.addWidget(QLabel("Original Image"))
        self.img_label = _preview_label()
        left_img_col.addWidget(self.img_label)
        left_row.addLayout(left_img_col)

        left_mask_col = QVBoxLayout()
        self.left_overlay_title = QLabel("Mask overlay (green = cable)")
        self.left_overlay_title.setStyleSheet("color:#94A3B8; font-size:12px;")
        left_mask_col.addWidget(self.left_overlay_title)
        self.mask_label = _preview_label()
        left_mask_col.addWidget(self.mask_label)
        left_row.addLayout(left_mask_col)

        self.right_layout.addLayout(left_row)

        # ── Divider ───────────────────────────────────────────────────
        self.stereo_divider = QFrame()
        self.stereo_divider.setFrameShape(QFrame.HLine)
        self.stereo_divider.setStyleSheet("color: #334155; margin: 4px 0;")
        self.right_layout.addWidget(self.stereo_divider)
        self.stereo_divider.hide()

        # ── Row 2: right camera (shown only for stereo samples) ───────
        self.right_row_title = _section_title("RIGHT Camera")
        self.right_layout.addWidget(self.right_row_title)
        self.right_row_title.hide()

        right_row = QHBoxLayout()
        right_row.setSpacing(8)

        right_img_col = QVBoxLayout()
        right_img_col.addWidget(QLabel("Original Image"))
        self.right_img_label = _preview_label()
        right_img_col.addWidget(self.right_img_label)
        right_row.addLayout(right_img_col)

        right_mask_col = QVBoxLayout()
        self.right_overlay_title = QLabel("Mask overlay (green = cable)")
        self.right_overlay_title.setStyleSheet("color:#94A3B8; font-size:12px;")
        right_mask_col.addWidget(self.right_overlay_title)
        self.right_mask_label = _preview_label()
        right_mask_col.addWidget(self.right_mask_label)
        right_row.addLayout(right_mask_col)

        self.right_row_widget = QWidget()
        self.right_row_widget.setLayout(right_row)
        self.right_layout.addWidget(self.right_row_widget)
        self.right_row_widget.hide()

        self.right_layout.addStretch()
        right_scroll.setWidget(right)
        splitter.addWidget(right_scroll)

        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 3)

    # ------------------------------------------------------------------
    # List management
    # ------------------------------------------------------------------

    def _refresh_list(self):
        current_id = self._current_id()
        self.list_widget.clear()
        samples = self.dm.list_samples()
        self.count_label.setText(f"{len(samples)} samples  —  {self.dm.base_dir}")
        for s in samples:
            ok = "✓" if s['has_mask'] else "✗"
            stereo = " [S]" if s.get('is_stereo') else ""
            notes_hint = f"  [{s['notes']}]" if s['notes'] else ""
            item = QListWidgetItem(f"{ok}  #{s['id']:04d}  {s['date']}{stereo}{notes_hint}")
            item.setData(Qt.UserRole, s['id'])
            self.list_widget.addItem(item)
        if current_id is not None:
            for i in range(self.list_widget.count()):
                if self.list_widget.item(i).data(Qt.UserRole) == current_id:
                    self.list_widget.setCurrentRow(i)
                    break

    def _current_id(self):
        item = self.list_widget.currentItem()
        return item.data(Qt.UserRole) if item else None

    # ------------------------------------------------------------------
    # Preview
    # ------------------------------------------------------------------

    def _on_select(self, row):
        if row < 0:
            return
        item = self.list_widget.item(row)
        if not item:
            return
        sid = item.data(Qt.UserRole)
        samples = self.dm.list_samples()
        sample = next((s for s in samples if s['id'] == sid), None)
        if not sample:
            return

        self.notes_edit.setText(sample.get('notes', ''))
        self.info_label.setText(
            f"Sample #{sid:04d}  —  {sample['date']}  —  {sample['image_path'].name}"
        )

        # Cargar paths si existen
        _, _, paths = self.dm.get_sample(sid)
        has_paths = paths is not None

        # ── Left image ───────────────────────────────────────────────
        left_img = cv2.imread(str(sample['image_path']))
        if left_img is not None:
            self.img_label.setPixmap(_fit_pixmap(left_img))
        else:
            self.img_label.setText("Image not found")

        if has_paths and left_img is not None:
            self.left_overlay_title.setText(
                f"Wire Path  (verde=inicio · rojo=fin · {len(paths.get('left', []))} pts)"
            )
            self.mask_label.setPixmap(_fit_pixmap(_draw_path(left_img, paths.get('left', []))))
        elif sample['has_mask'] and left_img is not None:
            self.left_overlay_title.setText("Mask overlay (green = cable)")
            mask = cv2.imread(str(sample['mask_path']), cv2.IMREAD_GRAYSCALE)
            if mask is not None:
                self.mask_label.setPixmap(_fit_pixmap(_make_overlay(left_img, mask)))
            else:
                self.mask_label.setText("Mask not readable")
        else:
            self.left_overlay_title.setText("No data")
            self.mask_label.clear()
            self.mask_label.setText("—")

        # ── Right image (stereo) ──────────────────────────────────────
        has_right = sample.get('right_image_path') is not None
        self.stereo_divider.setVisible(has_right)
        self.right_row_title.setVisible(has_right)
        self.right_row_widget.setVisible(has_right)

        if has_right:
            right_img = cv2.imread(str(sample['right_image_path']))
            if right_img is not None:
                self.right_img_label.setPixmap(_fit_pixmap(right_img))
            else:
                self.right_img_label.setText("Right image not found")

            if has_paths and right_img is not None:
                self.right_overlay_title.setText(
                    f"Wire Path  (verde=inicio · rojo=fin · {len(paths.get('right', []))} pts)"
                )
                self.right_mask_label.setPixmap(
                    _fit_pixmap(_draw_path(right_img, paths.get('right', [])))
                )
            else:
                right_mask_path = sample.get('right_mask_path')
                if right_mask_path and right_img is not None:
                    self.right_overlay_title.setText("Mask overlay (green = cable)")
                    rmask = cv2.imread(str(right_mask_path), cv2.IMREAD_GRAYSCALE)
                    if rmask is not None:
                        self.right_mask_label.setPixmap(
                            _fit_pixmap(_make_overlay(right_img, rmask))
                        )
                    else:
                        self.right_mask_label.setText("Right mask not readable")
                else:
                    self.right_overlay_title.setText("No data")
                    self.right_mask_label.clear()
                    self.right_mask_label.setText("—")

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def _save_notes(self):
        sid = self._current_id()
        if sid is None:
            return
        notes = self.notes_edit.text().strip()
        meta = self.dm._read_meta()
        entry = meta.get(str(sid), {})
        entry['notes'] = notes
        meta[str(sid)] = entry
        import json
        with open(self.dm.meta_path, 'w') as f:
            json.dump(meta, f, indent=2)
        self._refresh_list()

    def _delete_selected(self):
        sid = self._current_id()
        if sid is None:
            return
        reply = QMessageBox.question(
            self, "Delete sample",
            f"Delete sample #{sid:04d}? This cannot be undone.",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            self.dm.delete_sample(sid)
            self.img_label.clear()
            self.mask_label.clear()
            self.right_img_label.clear()
            self.right_mask_label.clear()
            self.info_label.setText("Select a sample to preview")
            self._refresh_list()

    def _print_summary(self):
        summary = self.dm.export_summary()
        print(summary)
        dlg = QDialog(self)
        dlg.setWindowTitle("Dataset Summary")
        dlg.setMinimumSize(500, 300)
        dlg.setStyleSheet(_DARK_QSS)
        layout = QVBoxLayout(dlg)
        text = QTextEdit()
        text.setReadOnly(True)
        text.setPlainText(summary)
        layout.addWidget(text)
        btn = QPushButton("Close")
        btn.clicked.connect(dlg.accept)
        layout.addWidget(btn)
        dlg.exec_()
