#!/usr/bin/env python3
import cv2
import numpy as np

from PyQt5.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel,
                              QPushButton, QListWidget, QListWidgetItem,
                              QMessageBox, QWidget, QLineEdit, QSplitter,
                              QTextEdit)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QImage, QPixmap, QFont


MAX_PREVIEW_DIM = 640   # px máximo en cualquier dimensión para el preview


def _to_qpixmap(img_bgr: np.ndarray) -> QPixmap:
    rgb = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)
    h, w = rgb.shape[:2]
    qimg = QImage(bytes(rgb.data), w, h, 3 * w, QImage.Format_RGB888)
    return QPixmap.fromImage(qimg)


def _scale_for_preview(img: np.ndarray) -> np.ndarray:
    h, w = img.shape[:2]
    max_d = max(h, w)
    if max_d > MAX_PREVIEW_DIM:
        scale = MAX_PREVIEW_DIM / max_d
        img = cv2.resize(img, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)
    return img


class DatasetViewerDialog(QDialog):
    """Visor interactivo del dataset de entrenamiento."""

    def __init__(self, dataset_manager, parent=None):
        super().__init__(parent)
        self.dm = dataset_manager
        self.setWindowTitle(f"Dataset Viewer — {self.dm.base_dir}")
        self.setMinimumSize(1000, 650)
        self._setup_ui()
        self._refresh_list()

    # ------------------------------------------------------------------
    # UI setup
    # ------------------------------------------------------------------

    def _setup_ui(self):
        root = QHBoxLayout(self)

        splitter = QSplitter(Qt.Horizontal)
        root.addWidget(splitter)

        # ── LEFT PANEL: lista + botones ──────────────────────────────
        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(4, 4, 4, 4)

        self.count_label = QLabel("0 samples")
        font = QFont()
        font.setBold(True)
        self.count_label.setFont(font)
        left_layout.addWidget(self.count_label)

        self.list_widget = QListWidget()
        self.list_widget.setMinimumWidth(200)
        self.list_widget.currentRowChanged.connect(self._on_select)
        left_layout.addWidget(self.list_widget)

        # Notes editor
        left_layout.addWidget(QLabel("Notes for selected:"))
        self.notes_edit = QLineEdit()
        self.notes_edit.setPlaceholderText("optional annotation...")
        self.notes_edit.returnPressed.connect(self._save_notes)
        left_layout.addWidget(self.notes_edit)

        btn_save_notes = QPushButton("💬 Save Notes")
        btn_save_notes.clicked.connect(self._save_notes)
        left_layout.addWidget(btn_save_notes)

        btn_delete = QPushButton("🗑️ Delete Selected")
        btn_delete.setStyleSheet("color: red;")
        btn_delete.clicked.connect(self._delete_selected)
        left_layout.addWidget(btn_delete)

        btn_summary = QPushButton("📋 Print Summary")
        btn_summary.clicked.connect(self._print_summary)
        left_layout.addWidget(btn_summary)

        btn_close = QPushButton("Close")
        btn_close.clicked.connect(self.accept)
        left_layout.addWidget(btn_close)

        splitter.addWidget(left)

        # ── RIGHT PANEL: previews ────────────────────────────────────
        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(4, 4, 4, 4)

        self.info_label = QLabel("Select a sample to preview")
        self.info_label.setAlignment(Qt.AlignCenter)
        right_layout.addWidget(self.info_label)

        previews = QHBoxLayout()

        img_col = QVBoxLayout()
        img_col.addWidget(QLabel("Original Image"))
        self.img_label = QLabel()
        self.img_label.setMinimumSize(400, 300)
        self.img_label.setAlignment(Qt.AlignCenter)
        self.img_label.setStyleSheet("background: #1a1a1a; border: 1px solid #444;")
        img_col.addWidget(self.img_label)
        previews.addLayout(img_col)

        mask_col = QVBoxLayout()
        mask_col.addWidget(QLabel("Mask overlay (green = cable)"))
        self.mask_label = QLabel()
        self.mask_label.setMinimumSize(400, 300)
        self.mask_label.setAlignment(Qt.AlignCenter)
        self.mask_label.setStyleSheet("background: #1a1a1a; border: 1px solid #444;")
        mask_col.addWidget(self.mask_label)
        previews.addLayout(mask_col)

        right_layout.addLayout(previews)
        splitter.addWidget(right)

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
            notes_hint = f"  [{s['notes']}]" if s['notes'] else ""
            item = QListWidgetItem(f"{ok}  #{s['id']:04d}  {s['date']}{notes_hint}")
            item.setData(Qt.UserRole, s['id'])
            self.list_widget.addItem(item)
        # Re-select same ID if still present
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

        img = cv2.imread(str(sample['image_path']))
        if img is not None:
            self.img_label.setPixmap(_to_qpixmap(_scale_for_preview(img)))
        else:
            self.img_label.setText("Image not found")

        if sample['has_mask'] and img is not None:
            mask = cv2.imread(str(sample['mask_path']), cv2.IMREAD_GRAYSCALE)
            if mask is not None:
                overlay = img.copy()
                overlay[mask > 0] = [0, 220, 0]
                blended = cv2.addWeighted(img, 0.6, overlay, 0.4, 0)
                self.mask_label.setPixmap(_to_qpixmap(_scale_for_preview(blended)))
            else:
                self.mask_label.setText("Mask not readable")
        else:
            self.mask_label.clear()
            self.mask_label.setText("No mask")

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def _save_notes(self):
        sid = self._current_id()
        if sid is None:
            return
        notes = self.notes_edit.text().strip()
        # Rewrite meta for this sample keeping existing date
        samples = self.dm.list_samples()
        sample = next((s for s in samples if s['id'] == sid), None)
        if sample:
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
            self.info_label.setText("Select a sample to preview")
            self._refresh_list()

    def _print_summary(self):
        summary = self.dm.export_summary()
        print(summary)
        dlg = QDialog(self)
        dlg.setWindowTitle("Dataset Summary")
        dlg.setMinimumSize(500, 300)
        layout = QVBoxLayout(dlg)
        text = QTextEdit()
        text.setReadOnly(True)
        text.setPlainText(summary)
        layout.addWidget(text)
        btn = QPushButton("Close")
        btn.clicked.connect(dlg.accept)
        layout.addWidget(btn)
        dlg.exec_()
