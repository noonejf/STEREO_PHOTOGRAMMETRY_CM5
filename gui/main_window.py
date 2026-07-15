#!/usr/bin/env python3
"""
Ventana única del sistema de fotogrametría estéreo CM5.
Sidebar de navegación + QStackedWidget con 3 páginas:
  0 – Dashboard  (preview + controles + log)
  1 – Calibration (workflow inline con preview propia)
  2 – 3D Processing (configuración + resultados)
"""

import sys
from datetime import datetime

from PyQt5.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QTextEdit, QProgressBar,
    QGroupBox, QMessageBox, QSplitter, QFrame,
    QApplication, QStackedWidget,
)
from PyQt5.QtCore import QThread, pyqtSignal, QTimer, Qt
from PyQt5.QtGui import QFont

from camera.stereo_camera import StereoCamera
from gui.camera_preview import CameraPreviewWidget
from gui.calibration_dialog import CalibrationPage
from gui.processing_dialog import ProcessingPage
from gui.ai_page import AIPage
from utils.logger import get_logger

logger = get_logger(__name__)

# ── Color palette (dark mode, same family as INTISAT) ─────────────────────────
BG_DEEP        = "#0F172A"
BG_PANEL       = "#1E293B"
BG_CARD        = "#273548"
BG_SIDEBAR     = "#0B1120"
ACCENT_CYAN    = "#22D3EE"
ACCENT_BLUE    = "#3B82F6"
ACCENT_GREEN   = "#16A34A"
ACCENT_ORANGE  = "#F59E0B"
TEXT_PRIMARY   = "#E2E8F0"
TEXT_SECONDARY = "#94A3B8"
TEXT_DIM       = "#64748B"
BORDER_SUBTLE  = "#334155"
GREEN_ON       = "#22C55E"
RED_OFF        = "#EF4444"
YELLOW_WARN    = "#EAB308"

GLOBAL_QSS = f"""
QMainWindow  {{ background-color: {BG_DEEP}; }}
QWidget      {{ color: {TEXT_PRIMARY}; font-family: "Segoe UI", "Roboto", sans-serif;
                font-size: 13px; background-color: transparent; }}
QGroupBox {{
    background-color: {BG_PANEL};
    border: 1px solid {BORDER_SUBTLE};
    border-radius: 8px;
    margin-top: 14px;
    padding: 14px 10px 10px 10px;
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    subcontrol-position: top left;
    padding: 2px 12px;
    color: {ACCENT_CYAN};
    font-weight: bold;
    font-size: 13px;
}}
QLabel       {{ color: {TEXT_PRIMARY}; background-color: transparent; }}
QPushButton {{
    background-color: {ACCENT_BLUE};
    color: white;
    border: none;
    border-radius: 6px;
    padding: 8px 16px;
    font-weight: 600;
    font-size: 13px;
}}
QPushButton:hover    {{ background-color: #60A5FA; }}
QPushButton:pressed  {{ background-color: #2563EB; }}
QPushButton:disabled {{ background-color: {BG_CARD}; color: {TEXT_DIM}; }}
QProgressBar {{
    background-color: {BG_DEEP};
    border: 1px solid {BORDER_SUBTLE};
    border-radius: 4px;
    text-align: center;
    color: {TEXT_PRIMARY};
    height: 18px;
    font-size: 12px;
}}
QProgressBar::chunk {{ background-color: {ACCENT_BLUE}; border-radius: 3px; }}
QTextEdit, QPlainTextEdit {{
    background-color: {BG_DEEP};
    color: #A5F3FC;
    border: 1px solid {BORDER_SUBTLE};
    border-radius: 6px;
    padding: 8px;
    font-family: "Consolas", "Courier New", monospace;
    font-size: 12px;
}}
QScrollBar:vertical {{
    background: {BG_DEEP}; width: 8px; border-radius: 4px;
}}
QScrollBar::handle:vertical {{
    background: {BORDER_SUBTLE}; border-radius: 4px; min-height: 30px;
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0px; }}
QComboBox {{
    background-color: {BG_CARD};
    color: {TEXT_PRIMARY};
    border: 1px solid {BORDER_SUBTLE};
    border-radius: 6px;
    padding: 5px 10px;
}}
QComboBox QAbstractItemView {{
    background-color: {BG_PANEL};
    color: {TEXT_PRIMARY};
    selection-background-color: {ACCENT_BLUE};
    border: 1px solid {BORDER_SUBTLE};
}}
QSpinBox, QDoubleSpinBox {{
    background-color: {BG_CARD};
    color: {TEXT_PRIMARY};
    border: 1px solid {BORDER_SUBTLE};
    border-radius: 4px;
    padding: 4px 8px;
}}
QCheckBox         {{ color: {TEXT_PRIMARY}; spacing: 8px; }}
QCheckBox::indicator {{
    width: 16px; height: 16px;
    border: 1px solid {BORDER_SUBTLE};
    border-radius: 3px;
    background-color: {BG_CARD};
}}
QCheckBox::indicator:checked {{
    background-color: {ACCENT_BLUE}; border-color: {ACCENT_BLUE};
}}
QSplitter::handle {{ background-color: {BORDER_SUBTLE}; }}
QListWidget {{
    background-color: {BG_DEEP};
    color: {TEXT_PRIMARY};
    border: 1px solid {BORDER_SUBTLE};
    border-radius: 4px;
}}
QListWidget::item:selected {{ background-color: {ACCENT_BLUE}; }}
QTabWidget::pane  {{ background-color: {BG_PANEL}; border: 1px solid {BORDER_SUBTLE}; }}
QTabBar::tab {{
    background-color: {BG_CARD};
    color: {TEXT_SECONDARY};
    padding: 6px 16px;
    border: 1px solid {BORDER_SUBTLE};
}}
QTabBar::tab:selected {{
    background-color: {BG_PANEL};
    color: {ACCENT_CYAN};
    border-bottom: 2px solid {ACCENT_CYAN};
}}
QFrame {{ color: {TEXT_PRIMARY}; }}
QScrollArea {{ border: none; background: transparent; }}
"""


# ── Countdown thread ──────────────────────────────────────────────────────────

class CountdownThread(QThread):
    countdown_update   = pyqtSignal(int)
    countdown_finished = pyqtSignal()

    def __init__(self, seconds=10):
        super().__init__()
        self.seconds = seconds
        self.running = True

    def run(self):
        for i in range(self.seconds, 0, -1):
            if not self.running:
                return
            self.countdown_update.emit(i)
            self.msleep(1000)
        if self.running:
            self.countdown_finished.emit()

    def stop(self):
        self.running = False


# ── Sidebar button ────────────────────────────────────────────────────────────

class _SidebarButton(QPushButton):
    def __init__(self, icon_text: str, label: str, parent=None):
        super().__init__(parent)
        self.setText(f"{icon_text}\n{label}")
        self.setFixedSize(88, 76)
        self.setCursor(Qt.PointingHandCursor)
        self._set_active(False)

    def _set_active(self, active: bool):
        if active:
            self.setStyleSheet(f"""
                QPushButton {{
                    background-color: {BG_PANEL};
                    color: {ACCENT_CYAN};
                    border: none;
                    border-left: 3px solid {ACCENT_CYAN};
                    border-radius: 0;
                    font-weight: bold;
                    font-size: 11px;
                    padding: 4px 2px;
                }}
            """)
        else:
            self.setStyleSheet(f"""
                QPushButton {{
                    background-color: transparent;
                    color: {TEXT_DIM};
                    border: none;
                    border-left: 3px solid transparent;
                    border-radius: 0;
                    font-weight: 600;
                    font-size: 11px;
                    padding: 4px 2px;
                }}
                QPushButton:hover {{
                    background-color: rgba(128,128,128,0.08);
                    color: {TEXT_PRIMARY};
                }}
            """)


# ── Main window ───────────────────────────────────────────────────────────────

class PhotogrammetryDashboard(QMainWindow):
    """Ventana única con navegación lateral y páginas apiladas."""

    PAGE_DASHBOARD   = 0
    PAGE_CALIBRATION = 1
    PAGE_PROCESSING  = 2
    PAGE_AI          = 3

    def __init__(self, camera_config, cameras_available=True):
        super().__init__()
        self.camera_config    = camera_config
        self.stereo_camera    = None
        self.cameras_available = cameras_available
        self.is_calibrated    = camera_config.is_calibrated()
        self.preview_active   = False
        self.countdown_thread = None

        self._init_ui()
        self._setup_camera_system()
        self._setup_connections()
        self._update_ui_for_camera_availability()
        self.update_calibration_status()

        logger.info(
            f"Dashboard initialized (cameras={'available' if cameras_available else 'unavailable'})"
        )
        self.showMaximized()

    # ── Build UI ──────────────────────────────────────────────────────────────

    def _init_ui(self):
        self.setWindowTitle("CM5 Stereo Photogrammetry  —  Arducam HQ 477")
        self.setMinimumSize(900, 600)
        self.setStyleSheet(GLOBAL_QSS)

        central = QWidget()
        central.setStyleSheet(f"background-color: {BG_DEEP};")
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self._build_title_bar(root)

        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)
        self._build_sidebar(body)

        # Stack
        self.stack = QStackedWidget()
        self.stack.setStyleSheet(f"background-color: {BG_DEEP};")

        self._build_dashboard_page()                          # index 0
        self.calib_page = CalibrationPage(                    # index 1
            self.camera_config, stereo_camera=None, parent=self
        )
        self.proc_page = ProcessingPage(self.camera_config, self)  # index 2
        self.ai_page   = AIPage(self)                              # index 3

        self.stack.addWidget(self.dash_page)
        self.stack.addWidget(self.calib_page)
        self.stack.addWidget(self.proc_page)
        self.stack.addWidget(self.ai_page)

        body.addWidget(self.stack, 1)
        root.addLayout(body, 1)
        self._build_status_bar(root)

        # Activate dashboard button
        self._sidebar_buttons[0]._set_active(True)

    def _build_title_bar(self, root):
        bar = QFrame()
        bar.setFixedHeight(48)
        bar.setStyleSheet(
            f"QFrame {{ background-color: {BG_SIDEBAR};"
            f"border-bottom: 1px solid {BORDER_SUBTLE}; }}"
        )
        h = QHBoxLayout(bar)
        h.setContentsMargins(16, 0, 16, 0)

        title = QLabel("CM5 Stereo Photogrammetry System")
        title.setStyleSheet(
            f"color: {ACCENT_CYAN}; font-weight: bold; font-size: 16px; background: transparent;"
        )
        h.addWidget(title)
        h.addStretch()

        subtitle = QLabel("Arducam HQ 477  ·  IMX477 12 MP  ·  Dual Camera")
        subtitle.setStyleSheet(
            f"color: {TEXT_DIM}; font-size: 12px; background: transparent;"
        )
        h.addWidget(subtitle)
        root.addWidget(bar)

    def _build_sidebar(self, body):
        sidebar = QFrame()
        sidebar.setFixedWidth(88)
        sidebar.setStyleSheet(
            f"QFrame {{ background-color: {BG_SIDEBAR};"
            f"border-right: 1px solid {BORDER_SUBTLE}; }}"
        )
        v = QVBoxLayout(sidebar)
        v.setContentsMargins(0, 8, 0, 8)
        v.setSpacing(0)

        nav_items = [
            ("⌂",  "Dashboard"),
            ("⊕",  "Calibration"),
            ("◈",  "Processing"),
            ("◉",  "AI"),
        ]
        self._sidebar_buttons = []
        for i, (icon, label) in enumerate(nav_items):
            btn = _SidebarButton(icon, label)
            btn.clicked.connect(lambda _checked, idx=i: self.navigate_to(idx))
            self._sidebar_buttons.append(btn)
            v.addWidget(btn)

        v.addStretch()
        ver = QLabel("v2.0")
        ver.setAlignment(Qt.AlignCenter)
        ver.setStyleSheet(f"color: {TEXT_DIM}; font-size: 10px; padding: 4px; background: transparent;")
        v.addWidget(ver)
        body.addWidget(sidebar)

    def _build_dashboard_page(self):
        """Construye la página de dashboard (preview + controles + log)."""
        self.dash_page = QWidget()
        self.dash_page.setStyleSheet(f"background-color: {BG_DEEP};")
        layout = QVBoxLayout(self.dash_page)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        # ── Camera preview ────────────────────────────────────────────────────
        preview_group = QGroupBox("Stereo Camera Preview")
        pv_layout = QVBoxLayout(preview_group)
        pv_layout.setSpacing(4)

        cam_row = QHBoxLayout()
        self.left_camera_preview = CameraPreviewWidget(
            "Left Camera (CAM0)", 0, self.camera_config
        )
        self.right_camera_preview = CameraPreviewWidget(
            "Right Camera (CAM1)", 1, self.camera_config
        )
        cam_row.addWidget(self.left_camera_preview)
        cam_row.addWidget(self.right_camera_preview)
        pv_layout.addLayout(cam_row)

        ctrl_row = QHBoxLayout()
        left_lbl = QLabel(f"Left: {self.camera_config.left_camera.name}")
        left_lbl.setStyleSheet(f"color: {ACCENT_BLUE}; font-weight: bold; background: transparent;")
        right_lbl = QLabel(f"Right: {self.camera_config.right_camera.name}")
        right_lbl.setStyleSheet(f"color: {ACCENT_ORANGE}; font-weight: bold; background: transparent;")

        self.btn_start_preview = QPushButton("▶  Start Preview")
        self.btn_start_preview.setStyleSheet(
            f"QPushButton {{ background-color: {BG_CARD}; color: {TEXT_PRIMARY}; }}"
            f"QPushButton:hover {{ background-color: #3B4B60; }}"
        )
        self.btn_start_preview.clicked.connect(self.toggle_preview)

        self.btn_stop_preview = QPushButton("⏹  Stop Preview")
        self.btn_stop_preview.setStyleSheet(
            f"QPushButton {{ background-color: {BG_CARD}; color: {TEXT_PRIMARY}; }}"
            f"QPushButton:hover {{ background-color: #3B4B60; }}"
        )
        self.btn_stop_preview.clicked.connect(self.stop_preview)
        self.btn_stop_preview.setEnabled(False)

        ctrl_row.addWidget(left_lbl)
        ctrl_row.addStretch()
        ctrl_row.addWidget(self.btn_start_preview)
        ctrl_row.addWidget(self.btn_stop_preview)
        ctrl_row.addStretch()
        ctrl_row.addWidget(right_lbl)
        pv_layout.addLayout(ctrl_row)
        layout.addWidget(preview_group, 3)

        # ── Bottom: controls + log ────────────────────────────────────────────
        splitter = QSplitter(Qt.Horizontal)
        splitter.setStyleSheet(f"background-color: {BG_DEEP};")
        splitter.addWidget(self._build_control_panel())
        splitter.addWidget(self._build_log_panel())
        splitter.setSizes([380, 620])
        layout.addWidget(splitter, 2)

    def _build_control_panel(self):
        panel = QFrame()
        panel.setStyleSheet(
            f"QFrame {{ background-color: {BG_PANEL}; border-radius: 8px; }}"
        )
        v = QVBoxLayout(panel)
        v.setContentsMargins(12, 12, 12, 12)
        v.setSpacing(8)

        title = QLabel("System Controls")
        title.setStyleSheet(
            f"color: {ACCENT_CYAN}; font-weight: bold; font-size: 14px; background: transparent;"
        )
        title.setAlignment(Qt.AlignCenter)
        v.addWidget(title)

        # Calibration status
        calib_group = QGroupBox("Calibration Status")
        cg = QVBoxLayout(calib_group)
        cg.setSpacing(4)

        self.calibration_status_label = QLabel("Checking...")
        self.calibration_status_label.setFont(QFont("Segoe UI", 11, QFont.Bold))
        self.calibration_status_label.setAlignment(Qt.AlignCenter)
        cg.addWidget(self.calibration_status_label)

        self.calibration_details_frame = QFrame()
        self.calibration_details_frame.setStyleSheet(
            f"QFrame {{ background-color: {BG_CARD}; border: 1px solid {BORDER_SUBTLE};"
            f"border-radius: 6px; }}"
        )
        df = QVBoxLayout(self.calibration_details_frame)
        df.setContentsMargins(10, 8, 10, 8)
        df.setSpacing(2)
        self.calib_error_label    = QLabel("Error: --")
        self.calib_images_label   = QLabel("Images: --")
        self.calib_date_label     = QLabel("Date: --")
        self.calib_baseline_label = QLabel("Baseline: --")
        for lbl in [self.calib_error_label, self.calib_images_label,
                    self.calib_date_label,  self.calib_baseline_label]:
            lbl.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 12px; background: transparent;")
            df.addWidget(lbl)
        cg.addWidget(self.calibration_details_frame)

        self.btn_calibrate = QPushButton("⊕  Calibrate Cameras")
        self.btn_calibrate.setFixedHeight(36)
        self.btn_calibrate.setStyleSheet(
            f"QPushButton {{ background-color: {ACCENT_GREEN}; color: white;"
            f"font-weight: bold; border-radius: 6px; }}"
            f"QPushButton:hover {{ background-color: #15803D; }}"
            f"QPushButton:disabled {{ background-color: {BG_CARD}; color: {TEXT_DIM}; }}"
        )
        self.btn_calibrate.clicked.connect(
            lambda: self.navigate_to(self.PAGE_CALIBRATION)
        )
        cg.addWidget(self.btn_calibrate)
        v.addWidget(calib_group)

        # Operations
        ops_group = QGroupBox("Operations")
        og = QVBoxLayout(ops_group)
        og.setSpacing(6)

        self.btn_capture_3d = QPushButton("◈  Capture for 3D Model")
        self.btn_capture_3d.setFixedHeight(38)
        self.btn_capture_3d.setStyleSheet(
            f"QPushButton {{ background-color: {ACCENT_BLUE}; color: white;"
            f"font-weight: bold; border-radius: 6px; font-size: 14px; }}"
            f"QPushButton:hover {{ background-color: #60A5FA; }}"
            f"QPushButton:disabled {{ background-color: {BG_CARD}; color: {TEXT_DIM}; }}"
        )
        self.btn_capture_3d.clicked.connect(self.start_3d_capture)
        self.btn_capture_3d.setEnabled(self.is_calibrated)
        og.addWidget(self.btn_capture_3d)

        self.btn_process_3d = QPushButton("▶  Process Captures")
        self.btn_process_3d.setFixedHeight(34)
        self.btn_process_3d.setStyleSheet(
            f"QPushButton {{ background-color: {BG_CARD}; color: {TEXT_PRIMARY}; border-radius: 6px; }}"
            f"QPushButton:hover {{ background-color: #3B4B60; }}"
            f"QPushButton:disabled {{ background-color: {BG_CARD}; color: {TEXT_DIM}; }}"
        )
        self.btn_process_3d.clicked.connect(
            lambda: self.navigate_to(self.PAGE_PROCESSING)
        )
        self.btn_process_3d.setEnabled(self.is_calibrated)
        og.addWidget(self.btn_process_3d)
        v.addWidget(ops_group)

        v.addStretch()
        return panel

    def _build_log_panel(self):
        panel = QFrame()
        panel.setStyleSheet(
            f"QFrame {{ background-color: {BG_PANEL}; border-radius: 8px; }}"
        )
        v = QVBoxLayout(panel)
        v.setContentsMargins(12, 12, 12, 12)
        v.setSpacing(6)

        # Countdown / capture control
        count_group = QGroupBox("Capture Control")
        cv = QVBoxLayout(count_group)

        self.countdown_label = QLabel("Ready for capture")
        self.countdown_label.setFont(QFont("Segoe UI", 14, QFont.Bold))
        self.countdown_label.setAlignment(Qt.AlignCenter)
        self.countdown_label.setStyleSheet(
            f"background-color: {BG_CARD}; color: {TEXT_SECONDARY};"
            f"padding: 10px; border-radius: 6px; border: 1px solid {BORDER_SUBTLE};"
        )
        cv.addWidget(self.countdown_label)

        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        cv.addWidget(self.progress_bar)

        self.btn_cancel = QPushButton("✕  Cancel")
        self.btn_cancel.setVisible(False)
        self.btn_cancel.setStyleSheet(
            f"QPushButton {{ background-color: {RED_OFF}; color: white; border-radius: 6px; }}"
        )
        self.btn_cancel.clicked.connect(self.cancel_operation)
        cv.addWidget(self.btn_cancel)
        v.addWidget(count_group)

        # Activity log
        log_group = QGroupBox("Activity Log")
        lv = QVBoxLayout(log_group)
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        lv.addWidget(self.log_text)
        v.addWidget(log_group, 1)

        return panel

    def _build_status_bar(self, root):
        bar = QFrame()
        bar.setFixedHeight(28)
        bar.setStyleSheet(
            f"QFrame {{ background-color: {BG_SIDEBAR}; border-top: 1px solid {BORDER_SUBTLE}; }}"
        )
        h = QHBoxLayout(bar)
        h.setContentsMargins(12, 0, 12, 0)

        self.status_camera_label = QLabel("Cameras: --")
        self.status_camera_label.setStyleSheet(
            f"color: {TEXT_SECONDARY}; font-size: 12px; background: transparent;"
        )
        h.addWidget(self.status_camera_label)
        h.addStretch()
        self.status_calibration_label = QLabel("Calibration: --")
        self.status_calibration_label.setStyleSheet(
            f"color: {TEXT_SECONDARY}; font-size: 12px; background: transparent;"
        )
        h.addWidget(self.status_calibration_label)
        root.addWidget(bar)

    # ── Navigation ────────────────────────────────────────────────────────────

    def navigate_to(self, page_index: int):
        current = self.stack.currentIndex()

        # Stop dashboard preview when leaving dashboard
        if current == self.PAGE_DASHBOARD and page_index != self.PAGE_DASHBOARD:
            if self.preview_active:
                self.stop_preview()

        # Inject stereo_camera into calibration page on first visit
        if page_index == self.PAGE_CALIBRATION:
            if self.calib_page.stereo_camera is None and self.stereo_camera is not None:
                self.calib_page.stereo_camera    = self.stereo_camera
                self.calib_page.cameras_available = self.cameras_available
                self.calib_page.btn_start.setEnabled(self.cameras_available)

        self.stack.setCurrentIndex(page_index)
        for i, btn in enumerate(self._sidebar_buttons):
            btn._set_active(i == page_index)

    # ── Camera system ─────────────────────────────────────────────────────────

    def _setup_camera_system(self):
        if not self.cameras_available:
            self.log_message("Running in processing-only mode (no cameras)", "WARNING")
            self.status_camera_label.setText("Cameras: Not available")
            return
        try:
            self.stereo_camera = StereoCamera(self.camera_config)
            self.log_message("Camera system initialized")
            self.status_camera_label.setText("Cameras: Connected")
        except Exception as e:
            self.log_message(f"Camera initialization error: {e}", "ERROR")
            self.status_camera_label.setText("Cameras: Error")
            self.cameras_available = False

    def _update_ui_for_camera_availability(self):
        if not self.cameras_available:
            self.btn_start_preview.setEnabled(False)
            self.btn_stop_preview.setEnabled(False)
            self.btn_capture_3d.setEnabled(False)
            self.btn_start_preview.setText("▶  Preview (Unavailable)")
            self.btn_capture_3d.setText("◈  Capture (Unavailable)")
            if self.is_calibrated:
                self.btn_process_3d.setEnabled(True)
                self.log_message("Processing-only mode — can process existing captures")
            else:
                self.log_message(
                    "No cameras: calibrate using existing sessions or transfer from Raspberry Pi",
                    "WARNING",
                )

    def _setup_connections(self):
        if hasattr(self.left_camera_preview, 'frame_ready'):
            self.left_camera_preview.frame_ready.connect(self._on_left_frame)
        if hasattr(self.right_camera_preview, 'frame_ready'):
            self.right_camera_preview.frame_ready.connect(self._on_right_frame)
        self.calib_page.calibration_updated.connect(self._on_calibration_updated)

    # ── Preview ───────────────────────────────────────────────────────────────

    def toggle_preview(self):
        if not self.preview_active:
            self.start_preview()
        else:
            self.stop_preview()

    def start_preview(self):
        try:
            self.log_message("Starting camera preview...")
            self.left_camera_preview.start_preview()
            self.right_camera_preview.start_preview()
            self.preview_active = True
            self.btn_start_preview.setEnabled(False)
            self.btn_stop_preview.setEnabled(True)
            self.btn_start_preview.setText("▶  Preview Active")
            self.log_message("Preview started")
        except Exception as e:
            self.log_message(f"Error starting preview: {e}", "ERROR")

    def stop_preview(self):
        try:
            self.log_message("Stopping preview...")
            self.left_camera_preview.stop_preview()
            self.right_camera_preview.stop_preview()
            self.preview_active = False
            self.btn_start_preview.setEnabled(True)
            self.btn_stop_preview.setEnabled(False)
            self.btn_start_preview.setText("▶  Start Preview")
            self.log_message("Preview stopped")
        except Exception as e:
            self.log_message(f"Error stopping preview: {e}", "ERROR")

    # ── Calibration status ────────────────────────────────────────────────────

    def _on_calibration_updated(self):
        self.camera_config.load_calibration()
        self.is_calibrated = self.camera_config.is_calibrated()
        self.update_calibration_status()
        calib_info = self.camera_config.get_calibration_info()
        self.log_message(
            f"Calibration updated: {calib_info['quality']} — "
            f"Error: {calib_info['error']:.3f} px — "
            f"Images: {calib_info['num_images']}"
        )

    def update_calibration_status(self):
        calib_info = self.camera_config.get_calibration_info()

        if calib_info['is_calibrated']:
            quality_color = {
                "Excelente": GREEN_ON,
                "Buena":     GREEN_ON,
                "Aceptable": YELLOW_WARN,
                "Pobre":     RED_OFF,
            }.get(calib_info['quality'], TEXT_SECONDARY)

            self.calibration_status_label.setText(
                f"✓ Calibrated — {calib_info['quality']}"
            )
            self.calibration_status_label.setStyleSheet(
                f"color: {quality_color}; font-weight: bold; background: transparent;"
            )
            self.calib_error_label.setText(
                f"Reprojection error: {calib_info['error']:.3f} px"
            )
            self.calib_images_label.setText(f"Images used: {calib_info['num_images']}")
            self.calib_date_label.setText(f"Date: {calib_info['date']}")
            if calib_info['baseline_mm']:
                self.calib_baseline_label.setText(
                    f"Baseline: {calib_info['baseline_mm']:.1f} mm"
                )
            for lbl in [self.calib_error_label, self.calib_images_label,
                        self.calib_date_label,  self.calib_baseline_label]:
                lbl.setStyleSheet(
                    f"color: {quality_color}; font-size: 12px; background: transparent;"
                )
            self.calibration_details_frame.setVisible(True)
            if hasattr(self, 'btn_capture_3d'):
                self.btn_capture_3d.setEnabled(self.cameras_available)
            if hasattr(self, 'btn_process_3d'):
                self.btn_process_3d.setEnabled(True)
            self.is_calibrated = True

        else:
            self.calibration_status_label.setText("✗ Calibration Required")
            self.calibration_status_label.setStyleSheet(
                f"color: {RED_OFF}; font-weight: bold; background: transparent;"
            )
            if hasattr(self, 'calibration_details_frame'):
                self.calibration_details_frame.setVisible(False)
            if hasattr(self, 'btn_capture_3d'):
                self.btn_capture_3d.setEnabled(False)
            if hasattr(self, 'btn_process_3d'):
                self.btn_process_3d.setEnabled(False)
            self.is_calibrated = False

        if hasattr(self, 'status_calibration_label'):
            self.status_calibration_label.setText(
                f"Calibration: {'OK' if self.is_calibrated else 'Required'}"
            )

    # ── 3D Capture ────────────────────────────────────────────────────────────

    def start_3d_capture(self):
        if not self.is_calibrated:
            QMessageBox.warning(
                self, "Warning",
                "Cameras must be calibrated before 3D capture."
            )
            return
        try:
            msg = QMessageBox(self)
            msg.setIcon(QMessageBox.Information)
            msg.setWindowTitle("3D Capture")
            msg.setText("A 10-second countdown will start.")
            msg.setInformativeText(
                "Position your object and ensure good lighting."
            )
            msg.setStandardButtons(QMessageBox.Ok | QMessageBox.Cancel)
            if msg.exec_() != QMessageBox.Ok:
                return
            self._start_countdown_capture()
        except Exception as e:
            self.log_message(f"Error starting 3D capture: {e}", "ERROR")

    def _start_countdown_capture(self):
        self.log_message("Starting capture countdown...")
        self.btn_capture_3d.setEnabled(False)
        self.btn_calibrate.setEnabled(False)
        self.btn_cancel.setVisible(True)
        self.countdown_thread = CountdownThread(10)
        self.countdown_thread.countdown_update.connect(self._update_countdown)
        self.countdown_thread.countdown_finished.connect(self._capture_stereo_pair)
        self.countdown_thread.start()

    def _update_countdown(self, seconds):
        if seconds <= 3:
            bg, fg = "#450A0A", RED_OFF
        else:
            bg, fg = "#1A2744", YELLOW_WARN
        self.countdown_label.setText(f"Capture in: {seconds}s")
        self.countdown_label.setStyleSheet(
            f"background-color: {bg}; color: {fg};"
            f"padding: 10px; border-radius: 6px; border: 1px solid {fg};"
            f"font-size: 18px; font-weight: bold;"
        )

    def _capture_stereo_pair(self):
        preview_was_active = False
        try:
            if self.preview_active:
                preview_was_active = True
                self.stop_preview()
                import time
                time.sleep(1.0)

            self.countdown_label.setText("CAPTURING...")
            self.countdown_label.setStyleSheet(
                f"background-color: #052E16; color: {GREEN_ON};"
                f"padding: 10px; border-radius: 6px; border: 1px solid {GREEN_ON};"
                f"font-size: 18px; font-weight: bold;"
            )
            QApplication.processEvents()

            if self.stereo_camera:
                result = self.stereo_camera.capture_stereo_pair()
                if result.get('success', False):
                    self.log_message("Stereo pair captured successfully")
                    self.countdown_label.setText("✓ Capture Successful")
                    self.btn_process_3d.setEnabled(True)
                else:
                    self.log_message(
                        f"Capture error: {result.get('error', 'Unknown')}", "ERROR"
                    )
                    self.countdown_label.setText("✗ Capture Error")

            self._cleanup_after_capture(preview_was_active)
        except Exception as e:
            self.log_message(f"Capture error: {e}", "ERROR")
            self.countdown_label.setText("✗ Capture Error")
            self._cleanup_after_capture(preview_was_active)

    def _cleanup_after_capture(self, restart_preview=False):
        self.btn_capture_3d.setEnabled(
            self.is_calibrated and self.cameras_available
        )
        self.btn_calibrate.setEnabled(True)
        self.btn_cancel.setVisible(False)
        if restart_preview:
            QTimer.singleShot(2000, self.start_preview)
        QTimer.singleShot(3000, self._restore_countdown_label)

    def _restore_countdown_label(self):
        self.countdown_label.setText("Ready for capture")
        self.countdown_label.setStyleSheet(
            f"background-color: {BG_CARD}; color: {TEXT_SECONDARY};"
            f"padding: 10px; border-radius: 6px; border: 1px solid {BORDER_SUBTLE};"
            f"font-size: 14px; font-weight: bold;"
        )

    def cancel_operation(self):
        if self.countdown_thread and self.countdown_thread.isRunning():
            self.countdown_thread.stop()
            self.countdown_thread.wait()
        self.log_message("Operation cancelled", "WARNING")
        self._cleanup_after_capture()
        self._restore_countdown_label()

    # ── Log ───────────────────────────────────────────────────────────────────

    def log_message(self, message, level="INFO"):
        ts = datetime.now().strftime("%H:%M:%S")
        color = {
            "ERROR":   RED_OFF,
            "WARNING": YELLOW_WARN,
        }.get(level, TEXT_SECONDARY)
        html = (
            f'<span style="color:{TEXT_DIM}">[{ts}]</span> '
            f'<span style="color:{color}">{level}: {message}</span>'
        )
        self.log_text.append(html)
        self.log_text.verticalScrollBar().setValue(
            self.log_text.verticalScrollBar().maximum()
        )
        if level == "ERROR":
            logger.error(message)
        elif level == "WARNING":
            logger.warning(message)
        else:
            logger.info(message)

    # ── Callbacks ─────────────────────────────────────────────────────────────

    def _on_left_frame(self, frame):
        pass

    def _on_right_frame(self, frame):
        pass

    # ── Close ─────────────────────────────────────────────────────────────────

    def closeEvent(self, event):
        try:
            self.log_message("Closing application...")
            if self.preview_active:
                self.stop_preview()
            if self.countdown_thread and self.countdown_thread.isRunning():
                self.countdown_thread.stop()
                self.countdown_thread.wait()
            if self.stereo_camera:
                self.stereo_camera.cleanup()
            logger.info("Application closed")
            event.accept()
        except Exception as e:
            logger.error(f"Error during close: {e}")
            event.accept()


# Alias for any code that still references the old name
MainWindow = PhotogrammetryDashboard


if __name__ == "__main__":
    from config.camera_config import CameraConfig
    app = QApplication(sys.argv)
    config = CameraConfig()
    window = PhotogrammetryDashboard(config)
    sys.exit(app.exec_())
