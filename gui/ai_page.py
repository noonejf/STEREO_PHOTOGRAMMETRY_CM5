#!/usr/bin/env python3
"""
AI Page — entrenamiento y gestión de modelos de IA.

Modelos:
  1) Segmentación de cable (Random Forest pixel-level)  → mask_dataset
  2) Wire Path Tracker (próximamente)                   → path_dataset
"""
from __future__ import annotations

import pickle
from datetime import datetime
from pathlib import Path

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QGroupBox, QTextEdit, QFrame,
    QProgressBar, QSplitter, QMessageBox,
)
from PyQt5.QtCore import QThread, pyqtSignal, Qt, QTimer
from PyQt5.QtGui import QFont

from utils.dataset_manager import DatasetManager
from utils.logger import get_logger

logger = get_logger(__name__)

# ── paths ─────────────────────────────────────────────────────────────────────
MODELS_DIR       = Path("data/models")
MASK_MODEL_PATH  = MODELS_DIR / "mask_model.pkl"
PATH_MODEL_PATH  = MODELS_DIR / "path_model.pkl"

MASK_DS_DIR = "data/ai_dataset/mask_dataset"
PATH_DS_DIR = "data/ai_dataset/path_dataset"

# ── colors (same palette as main window) ──────────────────────────────────────
BG_DEEP       = "#0F172A"
BG_PANEL      = "#1E293B"
BG_CARD       = "#273548"
ACCENT_CYAN   = "#22D3EE"
ACCENT_BLUE   = "#3B82F6"
ACCENT_GREEN  = "#16A34A"
ACCENT_ORANGE = "#F59E0B"
TEXT_PRIMARY  = "#E2E8F0"
TEXT_DIM      = "#64748B"
TEXT_SEC      = "#94A3B8"
BORDER        = "#334155"
GREEN_ON      = "#22C55E"
RED_OFF       = "#EF4444"
YELLOW_WARN   = "#EAB308"


# ── Training thread ────────────────────────────────────────────────────────────

class MaskTrainingThread(QThread):
    log_sig      = pyqtSignal(str, str)   # (message, level)
    progress_sig = pyqtSignal(int)
    done_sig     = pyqtSignal(bool, str)  # (success, summary)

    TARGET_W, TARGET_H = 256, 192

    def __init__(self, dataset_manager: DatasetManager):
        super().__init__()
        self.dm = dataset_manager

    # ── feature extraction ────────────────────────────────────────────
    def _features(self, img_bgr):
        import cv2
        import numpy as np
        hsv  = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2HSV)
        gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY).astype(np.float32)
        b3   = cv2.GaussianBlur(gray, (3, 3), 0)
        b9   = cv2.GaussianBlur(gray, (9, 9), 0)
        lc   = (gray - b9).clip(-127, 127) + 127   # local contrast
        return (np.stack([
            img_bgr[:, :, 0].ravel(),
            img_bgr[:, :, 1].ravel(),
            img_bgr[:, :, 2].ravel(),
            hsv[:, :, 0].ravel(),
            hsv[:, :, 1].ravel(),
            hsv[:, :, 2].ravel(),
            b3.ravel(),
            b9.ravel(),
            lc.ravel(),
        ], axis=1).astype("float32") / 255.0)

    def run(self):
        try:
            import cv2
            import numpy as np
            from sklearn.ensemble import RandomForestClassifier
            from sklearn.metrics import f1_score, precision_score, recall_score

            TW, TH = self.TARGET_W, self.TARGET_H

            # ── 1. load ──────────────────────────────────────────────
            self.log_sig.emit("Cargando imágenes del dataset...", "INFO")
            samples = self.dm.list_samples()
            pairs = []
            for s in samples:
                img  = cv2.imread(str(s['image_path']))
                mask = (cv2.imread(str(s['mask_path']), cv2.IMREAD_GRAYSCALE)
                        if s['has_mask'] else None)
                if img is not None and mask is not None:
                    pairs.append((img, mask))
                if s.get('right_image_path') and s.get('right_mask_path'):
                    ri = cv2.imread(str(s['right_image_path']))
                    rm = cv2.imread(str(s['right_mask_path']), cv2.IMREAD_GRAYSCALE)
                    if ri is not None and rm is not None:
                        pairs.append((ri, rm))

            if not pairs:
                self.done_sig.emit(False, "No se encontraron pares imagen/máscara válidos.")
                return

            self.log_sig.emit(f"{len(pairs)} imágenes cargadas (izq + der)", "INFO")
            self.progress_sig.emit(10)

            # ── 2. augmentation ───────────────────────────────────────
            self.log_sig.emit("Augmentando datos (flip H/V + brillo)...", "INFO")
            augmented = []
            for img, mask in pairs:
                augmented.append((img, mask))
                augmented.append((cv2.flip(img, 1), cv2.flip(mask, 1)))
                augmented.append((cv2.flip(img, 0), cv2.flip(mask, 0)))
                bright = np.clip(img.astype("int16") + 35, 0, 255).astype("uint8")
                dark   = np.clip(img.astype("int16") - 35, 0, 255).astype("uint8")
                augmented.append((bright, mask))
                augmented.append((dark,   mask))

            self.log_sig.emit(f"{len(augmented)} imágenes tras augmentación", "INFO")
            self.progress_sig.emit(20)

            # ── 3. extract features ───────────────────────────────────
            self.log_sig.emit("Extrayendo features de píxeles...", "INFO")
            Xs, ys = [], []
            for i, (img, mask) in enumerate(augmented):
                img_r  = cv2.resize(img,  (TW, TH))
                mask_r = cv2.resize(mask, (TW, TH), interpolation=cv2.INTER_NEAREST)
                Xs.append(self._features(img_r))
                ys.append((mask_r > 0).astype("uint8").ravel())
                if i % 5 == 0:
                    self.progress_sig.emit(20 + int(20 * i / len(augmented)))

            X = np.vstack(Xs)
            y = np.concatenate(ys)
            self.log_sig.emit(
                f"Features: {X.shape[0]:,} píxeles  |  positivos: {np.sum(y):,} ({100*np.mean(y):.1f}%)",
                "INFO"
            )
            self.progress_sig.emit(42)

            # ── 4. balance & subsample ────────────────────────────────
            pos_idx = np.where(y == 1)[0]
            neg_idx = np.where(y == 0)[0]
            n_pos = min(len(pos_idx), 40_000)
            n_neg = min(len(neg_idx), n_pos * 4)

            rng = np.random.default_rng(42)
            sel = np.concatenate([
                rng.choice(pos_idx, n_pos, replace=len(pos_idx) < n_pos),
                rng.choice(neg_idx, n_neg, replace=False),
            ])
            rng.shuffle(sel)
            X_tr, y_tr = X[sel], y[sel]
            self.log_sig.emit(
                f"Dataset balanceado: {len(X_tr):,} píxeles  ({n_pos:,} pos / {n_neg:,} neg)",
                "INFO"
            )
            self.progress_sig.emit(50)

            # ── 5. train ──────────────────────────────────────────────
            self.log_sig.emit("Entrenando Random Forest (100 árboles, max_depth=12)...", "INFO")
            clf = RandomForestClassifier(
                n_estimators=100,
                max_depth=12,
                min_samples_leaf=3,
                n_jobs=-1,
                random_state=42,
                class_weight="balanced",
            )
            clf.fit(X_tr, y_tr)
            self.progress_sig.emit(85)

            # ── 6. evaluate ───────────────────────────────────────────
            self.log_sig.emit("Evaluando en dataset de entrenamiento...", "INFO")
            y_pred = clf.predict(X_tr)
            f1   = f1_score(y_tr, y_pred, zero_division=0)
            prec = precision_score(y_tr, y_pred, zero_division=0)
            rec  = recall_score(y_tr, y_pred, zero_division=0)
            self.log_sig.emit(
                f"F1={f1:.3f}   Precision={prec:.3f}   Recall={rec:.3f}", "INFO"
            )
            self.progress_sig.emit(92)

            # ── 7. save ───────────────────────────────────────────────
            MODELS_DIR.mkdir(parents=True, exist_ok=True)
            model_data = {
                "model":       clf,
                "date":        datetime.now().strftime("%Y-%m-%d %H:%M"),
                "n_pairs":     len(pairs),
                "n_augmented": len(augmented),
                "f1_train":    f1,
                "precision":   prec,
                "recall":      rec,
                "target_size": (TW, TH),
            }
            with open(MASK_MODEL_PATH, "wb") as fh:
                pickle.dump(model_data, fh)

            self.progress_sig.emit(100)
            self.log_sig.emit(f"✓ Modelo guardado → {MASK_MODEL_PATH}", "SUCCESS")
            self.done_sig.emit(
                True,
                f"Entrenamiento completado  |  F1={f1:.3f}  Precision={prec:.3f}  Recall={rec:.3f}"
            )

        except ImportError as e:
            self.done_sig.emit(False, f"Librería no instalada: {e}")
        except Exception as e:
            logger.error(f"Training error: {e}", exc_info=True)
            self.done_sig.emit(False, str(e))


# ── AI Page widget ─────────────────────────────────────────────────────────────

class AIPage(QWidget):
    """Página de IA: datasets + entrenamiento de modelos."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._mask_dm = DatasetManager(MASK_DS_DIR)
        self._path_dm = DatasetManager(PATH_DS_DIR)
        self._train_thread: MaskTrainingThread | None = None
        self._setup_ui()
        self._refresh_status()

    # ── UI ─────────────────────────────────────────────────────────────────────

    def _setup_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(10, 6, 10, 6)
        root.setSpacing(8)

        # Back bar
        back_bar = QFrame()
        back_bar.setFixedHeight(38)
        back_bar.setStyleSheet(
            f"QFrame {{ background-color: {BG_PANEL}; border-radius: 6px; }}"
        )
        bb = QHBoxLayout(back_bar)
        bb.setContentsMargins(8, 0, 8, 0)
        btn_back = QPushButton("← Dashboard")
        btn_back.setStyleSheet(
            f"background:transparent; color:{ACCENT_CYAN}; font-weight:bold;"
            f" border:none; font-size:13px;"
        )
        btn_back.clicked.connect(
            lambda: self.window().navigate_to(0)
            if hasattr(self.window(), "navigate_to") else None
        )
        bb.addWidget(btn_back)
        bb.addStretch()
        page_title = QLabel("Inteligencia Artificial — Entrenamiento de Modelos")
        page_title.setStyleSheet(
            f"color:{TEXT_SEC}; font-size:12px; background:transparent;"
        )
        bb.addWidget(page_title)
        root.addWidget(back_bar)

        # ── Two model cards side by side ──────────────────────────────
        cards_row = QHBoxLayout()
        cards_row.setSpacing(10)
        cards_row.addWidget(self._build_mask_card())
        cards_row.addWidget(self._build_path_card())
        root.addLayout(cards_row)

        # ── Training log ──────────────────────────────────────────────
        log_group = QGroupBox("Log de Entrenamiento")
        log_group.setStyleSheet(
            f"QGroupBox {{ background:{BG_PANEL}; border:1px solid {BORDER};"
            f" border-radius:8px; margin-top:14px; padding:14px 10px 10px; }}"
            f"QGroupBox::title {{ color:{ACCENT_CYAN}; font-weight:bold;"
            f" subcontrol-origin:margin; padding:2px 12px; }}"
        )
        lv = QVBoxLayout(log_group)

        self._progress = QProgressBar()
        self._progress.setRange(0, 100)
        self._progress.setValue(0)
        self._progress.setVisible(False)
        self._progress.setStyleSheet(
            f"QProgressBar {{ background:{BG_DEEP}; border:1px solid {BORDER};"
            f" border-radius:4px; color:{TEXT_PRIMARY}; height:16px; }}"
            f"QProgressBar::chunk {{ background:{ACCENT_BLUE}; border-radius:3px; }}"
        )
        lv.addWidget(self._progress)

        self._log = QTextEdit()
        self._log.setReadOnly(True)
        self._log.setMinimumHeight(180)
        self._log.setStyleSheet(
            f"background:{BG_DEEP}; color:#A5F3FC; border:1px solid {BORDER};"
            f" border-radius:6px; padding:8px;"
            f" font-family:'Consolas','Courier New',monospace; font-size:12px;"
        )
        lv.addWidget(self._log)
        root.addWidget(log_group, 1)

    def _card_style(self):
        return (
            f"QGroupBox {{ background:{BG_PANEL}; border:1px solid {BORDER};"
            f" border-radius:8px; margin-top:14px; padding:14px 10px 10px; }}"
            f"QGroupBox::title {{ color:{ACCENT_CYAN}; font-weight:bold;"
            f" subcontrol-origin:margin; padding:2px 12px; font-size:13px; }}"
        )

    def _build_mask_card(self) -> QGroupBox:
        g = QGroupBox("🎭  Modelo: Segmentación de Cable (Máscaras)")
        g.setStyleSheet(self._card_style())
        v = QVBoxLayout(g)
        v.setSpacing(8)

        # Dataset info row
        ds_row = QHBoxLayout()
        self._mask_ds_label = QLabel("Dataset: — muestras")
        self._mask_ds_label.setStyleSheet(f"color:{TEXT_SEC}; font-size:12px;")
        ds_row.addWidget(self._mask_ds_label)
        ds_row.addStretch()
        btn_view = QPushButton("📊 Ver Dataset")
        btn_view.setFixedHeight(28)
        btn_view.setStyleSheet(
            f"background:{BG_CARD}; color:{TEXT_PRIMARY}; border-radius:5px;"
            f" font-size:11px; padding:2px 10px;"
        )
        btn_view.clicked.connect(self._view_mask_dataset)
        ds_row.addWidget(btn_view)
        v.addLayout(ds_row)

        # Status
        self._mask_status_label = QLabel("Estado: ✗ No entrenado")
        self._mask_status_label.setStyleSheet(f"color:{RED_OFF}; font-size:12px;")
        v.addWidget(self._mask_status_label)

        self._mask_meta_label = QLabel("")
        self._mask_meta_label.setStyleSheet(f"color:{TEXT_DIM}; font-size:11px;")
        v.addWidget(self._mask_meta_label)

        # Description
        desc = QLabel(
            "Random Forest pixel-level · Features: BGR + HSV + contraste local\n"
            "Augmentación automática (flip H/V + brillo) · CPU-only · Funciona en RPi"
        )
        desc.setWordWrap(True)
        desc.setStyleSheet(f"color:{TEXT_DIM}; font-size:11px;")
        v.addWidget(desc)

        # Train button
        self._btn_train_mask = QPushButton("▶  Entrenar Modelo de Máscaras")
        self._btn_train_mask.setFixedHeight(38)
        self._btn_train_mask.setStyleSheet(
            f"QPushButton {{ background:{ACCENT_GREEN}; color:white;"
            f" font-weight:bold; border-radius:6px; font-size:13px; }}"
            f"QPushButton:hover {{ background:#15803D; }}"
            f"QPushButton:disabled {{ background:{BG_CARD}; color:{TEXT_DIM}; }}"
        )
        self._btn_train_mask.clicked.connect(self._train_mask_model)
        v.addWidget(self._btn_train_mask)

        return g

    def _build_path_card(self) -> QGroupBox:
        g = QGroupBox("🔀  Modelo: Wire Path Tracker (Caminos)")
        g.setStyleSheet(self._card_style())
        v = QVBoxLayout(g)
        v.setSpacing(8)

        # Dataset info row
        ds_row = QHBoxLayout()
        self._path_ds_label = QLabel("Dataset: — muestras")
        self._path_ds_label.setStyleSheet(f"color:{TEXT_SEC}; font-size:12px;")
        ds_row.addWidget(self._path_ds_label)
        ds_row.addStretch()
        btn_view = QPushButton("📊 Ver Dataset")
        btn_view.setFixedHeight(28)
        btn_view.setStyleSheet(
            f"background:{BG_CARD}; color:{TEXT_PRIMARY}; border-radius:5px;"
            f" font-size:11px; padding:2px 10px;"
        )
        btn_view.clicked.connect(self._view_path_dataset)
        ds_row.addWidget(btn_view)
        v.addLayout(ds_row)

        self._path_status_label = QLabel("Estado: ✗ No entrenado")
        self._path_status_label.setStyleSheet(f"color:{RED_OFF}; font-size:12px;")
        v.addWidget(self._path_status_label)

        self._path_meta_label = QLabel("")
        self._path_meta_label.setStyleSheet(f"color:{TEXT_DIM}; font-size:11px;")
        v.addWidget(self._path_meta_label)

        desc = QLabel(
            "Modelo de secuencia que aprende a trazar el camino del cable\n"
            "desde inicio hasta fin sobre la máscara predicha.\n"
            "Necesita ≥ 30 muestras para entrenar de forma fiable."
        )
        desc.setWordWrap(True)
        desc.setStyleSheet(f"color:{TEXT_DIM}; font-size:11px;")
        v.addWidget(desc)

        self._btn_train_path = QPushButton("▶  Entrenar Modelo de Paths")
        self._btn_train_path.setFixedHeight(38)
        self._btn_train_path.setStyleSheet(
            f"QPushButton {{ background:{ACCENT_ORANGE}; color:white;"
            f" font-weight:bold; border-radius:6px; font-size:13px; }}"
            f"QPushButton:hover {{ background:#D97706; }}"
            f"QPushButton:disabled {{ background:{BG_CARD}; color:{TEXT_DIM}; }}"
        )
        self._btn_train_path.clicked.connect(self._train_path_model)
        v.addWidget(self._btn_train_path)

        return g

    # ── status refresh ─────────────────────────────────────────────────────────

    def _refresh_status(self):
        # Mask dataset
        n_mask = self._mask_dm.count()
        self._mask_ds_label.setText(
            f"Dataset: {n_mask} muestras estéreo  (~{n_mask*2} imágenes)"
        )

        if MASK_MODEL_PATH.exists():
            try:
                with open(MASK_MODEL_PATH, "rb") as f:
                    md = pickle.load(f)
                self._mask_status_label.setText("Estado: ✓ Modelo entrenado")
                self._mask_status_label.setStyleSheet(f"color:{GREEN_ON}; font-size:12px;")
                self._mask_meta_label.setText(
                    f"Última sesión: {md.get('date','?')}  |  "
                    f"F1={md.get('f1_train',0):.3f}  "
                    f"P={md.get('precision',0):.3f}  "
                    f"R={md.get('recall',0):.3f}  |  "
                    f"{md.get('n_pairs',0)} imágenes · "
                    f"{md.get('n_augmented',0)} augmentadas"
                )
                self._btn_train_mask.setText("🔄  Re-entrenar Modelo de Máscaras")
            except Exception:
                self._mask_status_label.setText("Estado: ⚠ Error al leer modelo")
                self._mask_status_label.setStyleSheet(f"color:{YELLOW_WARN}; font-size:12px;")
        else:
            self._mask_status_label.setText("Estado: ✗ No entrenado")
            self._mask_status_label.setStyleSheet(f"color:{RED_OFF}; font-size:12px;")
            self._mask_meta_label.setText("")
            self._btn_train_mask.setText("▶  Entrenar Modelo de Máscaras")

        self._btn_train_mask.setEnabled(n_mask >= 1)

        # Path dataset
        n_path = self._path_dm.count()
        self._path_ds_label.setText(
            f"Dataset: {n_path} muestras estéreo  (~{n_path*2} imágenes)"
        )

        if PATH_MODEL_PATH.exists():
            try:
                with open(PATH_MODEL_PATH, "rb") as f:
                    pd_ = pickle.load(f)
                self._path_status_label.setText("Estado: ✓ Modelo entrenado")
                self._path_status_label.setStyleSheet(f"color:{GREEN_ON}; font-size:12px;")
                self._path_meta_label.setText(
                    f"Última sesión: {pd_.get('date','?')}  |  {pd_.get('n_pairs',0)} imágenes"
                )
                self._btn_train_path.setText("🔄  Re-entrenar Modelo de Paths")
            except Exception:
                pass
        else:
            if n_path < 5:
                self._path_status_label.setText(
                    f"Estado: ✗ No entrenado  (tienes {n_path}, necesitas ≥ 5)"
                )
                self._path_status_label.setStyleSheet(f"color:{YELLOW_WARN}; font-size:12px;")
            else:
                self._path_status_label.setText("Estado: ✗ No entrenado")
                self._path_status_label.setStyleSheet(f"color:{RED_OFF}; font-size:12px;")
            self._path_meta_label.setText("")

        self._btn_train_path.setEnabled(n_path >= 5)

    # ── dataset viewers ────────────────────────────────────────────────────────

    def _view_mask_dataset(self):
        from gui.dataset_viewer import DatasetViewerDialog
        dlg = DatasetViewerDialog(self._mask_dm, parent=self)
        dlg.exec_()
        self._refresh_status()

    def _view_path_dataset(self):
        from gui.dataset_viewer import DatasetViewerDialog
        dlg = DatasetViewerDialog(self._path_dm, parent=self)
        dlg.exec_()
        self._refresh_status()

    # ── training ───────────────────────────────────────────────────────────────

    def _log_msg(self, msg: str, level: str = "INFO"):
        ts = datetime.now().strftime("%H:%M:%S")
        color = {
            "ERROR":   RED_OFF,
            "WARNING": YELLOW_WARN,
            "SUCCESS": GREEN_ON,
        }.get(level, TEXT_SEC)
        html = (
            f'<span style="color:{TEXT_DIM}">[{ts}]</span> '
            f'<span style="color:{color}">{msg}</span>'
        )
        self._log.append(html)
        self._log.verticalScrollBar().setValue(
            self._log.verticalScrollBar().maximum()
        )

    def _set_training_ui(self, training: bool):
        self._btn_train_mask.setEnabled(not training)
        self._btn_train_path.setEnabled(not training)
        self._progress.setVisible(training)
        if training:
            self._progress.setValue(0)

    def _train_mask_model(self):
        if self._train_thread and self._train_thread.isRunning():
            return
        self._log.clear()
        self._log_msg("═══ Iniciando entrenamiento: Segmentación de Cable ═══", "SUCCESS")
        self._set_training_ui(True)

        self._train_thread = MaskTrainingThread(self._mask_dm)
        self._train_thread.log_sig.connect(self._log_msg)
        self._train_thread.progress_sig.connect(self._progress.setValue)
        self._train_thread.done_sig.connect(self._on_mask_done)
        self._train_thread.start()

    def _on_mask_done(self, success: bool, summary: str):
        self._set_training_ui(False)
        if success:
            self._log_msg(f"═══ {summary} ═══", "SUCCESS")
            self._refresh_status()
        else:
            self._log_msg(f"✗ Error: {summary}", "ERROR")
            QMessageBox.warning(self, "Error de entrenamiento", summary)

    def _train_path_model(self):
        """Path model training — placeholder, lógica a implementar."""
        QMessageBox.information(
            self, "Próximamente",
            "El modelo de Wire Path requiere más arquitectura (graph-based tracker).\n"
            "Sigue recolectando muestras mientras tanto.\n\n"
            f"Tienes {self._path_dm.count()} muestras actualmente."
        )
