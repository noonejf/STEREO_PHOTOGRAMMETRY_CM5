#!/usr/bin/env python3
"""
Página de calibración de cámaras estéreo.
Reemplaza el CalibrationDialog (QDialog) por CalibrationPage (QWidget)
integrado en el QStackedWidget de la ventana única.

Diseño: split horizontal
  Izquierda — vista previa en vivo (sus propios CameraPreviewWidget)
  Derecha   — controles: config, progreso, log, botones
"""

from datetime import datetime
from pathlib import Path

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QProgressBar, QTextEdit, QGroupBox,
    QGridLayout, QMessageBox, QSpinBox,
    QDoubleSpinBox, QFrame, QSplitter,
)
from PyQt5.QtCore import QThread, pyqtSignal, QTimer, Qt
from PyQt5.QtGui import QFont

from camera.camera_calibration import CameraCalibrator
from gui.camera_preview import CameraPreviewWidget
from utils.logger import get_logger

logger = get_logger(__name__)

# ── Color constants (same palette as main_window) ─────────────────────────────
BG_DEEP        = "#0F172A"
BG_PANEL       = "#1E293B"
BG_CARD        = "#273548"
BG_SIDEBAR     = "#0B1120"
ACCENT_CYAN    = "#22D3EE"
ACCENT_BLUE    = "#3B82F6"
ACCENT_GREEN   = "#16A34A"
TEXT_PRIMARY   = "#E2E8F0"
TEXT_SECONDARY = "#94A3B8"
TEXT_DIM       = "#64748B"
BORDER_SUBTLE  = "#334155"
GREEN_ON       = "#22C55E"
RED_OFF        = "#EF4444"
YELLOW_WARN    = "#EAB308"


# ── Background processing thread (unchanged) ─────────────────────────────────

class CalibrationProcessingThread(QThread):
    """Hilo para ejecutar el procesamiento de calibración sin bloquear UI."""
    progress_update    = pyqtSignal(int, str)
    calibration_complete = pyqtSignal(bool, dict)
    log_message        = pyqtSignal(str, str)   # message, level

    def __init__(self, camera_config, session_dir):
        super().__init__()
        self.camera_config = camera_config
        self.session_dir   = session_dir
        self.should_stop   = False

    def run(self):
        try:
            self.log_message.emit("Starting image processing...", "INFO")
            calibrator = CameraCalibrator(self.camera_config)
            result = calibrator.calibrate_from_session(
                self.session_dir,
                progress_callback=self._progress_callback,
            )
            if result['success']:
                self.log_message.emit("Processing completed successfully", "INFO")
            else:
                self.log_message.emit(
                    f"Processing error: {result.get('error')}", "ERROR"
                )
            self.calibration_complete.emit(result['success'], result)
        except Exception as e:
            self.log_message.emit(f"Fatal error during processing: {e}", "ERROR")
            self.calibration_complete.emit(False, {'error': str(e)})

    def _progress_callback(self, progress, message):
        if not self.should_stop:
            mapped = 50 + int(progress * 0.5)
            self.progress_update.emit(mapped, message)

    def stop(self):
        self.should_stop = True


# ── Calibration page ──────────────────────────────────────────────────────────

class CalibrationPage(QWidget):
    """
    Página inline de calibración.
    Emite ``calibration_updated`` cuando la calibración se completa
    y ``navigate_back`` cuando el usuario quiere volver al dashboard.
    """
    calibration_updated = pyqtSignal()
    navigate_back       = pyqtSignal()

    def __init__(self, camera_config, stereo_camera=None, parent=None):
        super().__init__(parent)
        self.camera_config   = camera_config
        self.stereo_camera   = stereo_camera
        self.cameras_available = stereo_camera is not None
        self.processing_thread = None
        self.countdown_timer   = QTimer(self)
        self.countdown_seconds = 0

        self.images_to_capture  = 0
        self.images_captured    = 0
        self.capture_session_dir = None
        self.is_capturing       = False

        self._init_ui()
        self._load_current_calibration_status()

    # ── UI construction ───────────────────────────────────────────────────────

    def _init_ui(self):
        self.setStyleSheet(f"background-color: {BG_DEEP};")
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Back bar ──────────────────────────────────────────────────────────
        back_bar = QFrame()
        back_bar.setFixedHeight(44)
        back_bar.setStyleSheet(
            f"QFrame {{ background-color: {BG_SIDEBAR};"
            f"border-bottom: 1px solid {BORDER_SUBTLE}; }}"
        )
        bb = QHBoxLayout(back_bar)
        bb.setContentsMargins(12, 0, 12, 0)

        btn_back = QPushButton("← Dashboard")
        btn_back.setStyleSheet(
            f"QPushButton {{ background-color: transparent; color: {ACCENT_CYAN};"
            f"border: none; font-weight: bold; font-size: 13px; }}"
            f"QPushButton:hover {{ color: white; }}"
        )
        btn_back.clicked.connect(self._go_back)
        bb.addWidget(btn_back)
        bb.addStretch()

        page_title = QLabel("⊕  Stereo Camera Calibration")
        page_title.setStyleSheet(
            f"color: {TEXT_PRIMARY}; font-weight: bold; font-size: 15px;"
            f"background: transparent;"
        )
        bb.addWidget(page_title)
        bb.addStretch()
        root.addWidget(back_bar)

        # ── Main split: left preview | right controls ─────────────────────────
        splitter = QSplitter(Qt.Horizontal)
        splitter.setStyleSheet(f"background-color: {BG_DEEP};")

        splitter.addWidget(self._build_preview_panel())
        splitter.addWidget(self._build_controls_panel())
        splitter.setSizes([480, 520])

        root.addWidget(splitter, 1)

    def _build_preview_panel(self):
        panel = QFrame()
        panel.setStyleSheet(
            f"QFrame {{ background-color: {BG_PANEL}; border-right: 1px solid {BORDER_SUBTLE}; }}"
        )
        v = QVBoxLayout(panel)
        v.setContentsMargins(10, 10, 10, 10)
        v.setSpacing(6)

        title = QLabel("Live Camera Preview")
        title.setStyleSheet(
            f"color: {ACCENT_CYAN}; font-weight: bold; font-size: 13px; background: transparent;"
        )
        title.setAlignment(Qt.AlignCenter)
        v.addWidget(title)

        self.left_preview = CameraPreviewWidget(
            "Left Camera (CAM0)", 0, self.camera_config
        )
        self.right_preview = CameraPreviewWidget(
            "Right Camera (CAM1)", 1, self.camera_config
        )
        v.addWidget(self.left_preview, 1)
        v.addWidget(self.right_preview, 1)

        # Preview toggle buttons
        btn_row = QHBoxLayout()
        self.btn_preview_start = QPushButton("▶  Start Preview")
        self.btn_preview_start.setStyleSheet(
            f"QPushButton {{ background-color: {BG_CARD}; color: {TEXT_PRIMARY}; }}"
            f"QPushButton:hover {{ background-color: #3B4B60; }}"
        )
        self.btn_preview_start.clicked.connect(self.start_preview_for_positioning)

        self.btn_preview_stop = QPushButton("⏹  Stop Preview")
        self.btn_preview_stop.setStyleSheet(
            f"QPushButton {{ background-color: {BG_CARD}; color: {TEXT_PRIMARY}; }}"
            f"QPushButton:hover {{ background-color: #3B4B60; }}"
        )
        self.btn_preview_stop.clicked.connect(self.stop_preview_for_capture)
        self.btn_preview_stop.setEnabled(False)

        btn_row.addWidget(self.btn_preview_start)
        btn_row.addWidget(self.btn_preview_stop)
        v.addLayout(btn_row)

        hint = QLabel(
            "Position the chessboard so it is clearly visible\n"
            "in BOTH cameras before each capture."
        )
        hint.setStyleSheet(
            f"color: {TEXT_DIM}; font-size: 11px; background: transparent;"
        )
        hint.setAlignment(Qt.AlignCenter)
        hint.setWordWrap(True)
        v.addWidget(hint)

        return panel

    def _build_controls_panel(self):
        panel = QWidget()
        panel.setStyleSheet(f"background-color: {BG_DEEP};")
        v = QVBoxLayout(panel)
        v.setContentsMargins(10, 10, 10, 10)
        v.setSpacing(6)

        v.addWidget(self._create_board_info_group())
        v.addWidget(self._create_capture_config_group())
        v.addWidget(self._create_current_status_group())
        v.addWidget(self._create_progress_group())
        v.addWidget(self._create_log_group())
        v.addLayout(self._create_buttons())

        return panel

    def _create_board_info_group(self):
        group = QGroupBox("Checkerboard Requirements")
        v = QVBoxLayout(group)
        board_size  = self.camera_config.stereo.calibration_board_size
        square_size = self.camera_config.stereo.calibration_square_size_mm
        info_label = QLabel(
            f"<b>Board:</b> {board_size[0]} × {board_size[1]} inner corners"
            f"  ({board_size[0] * board_size[1]} total)<br>"
            f"<b>Square size:</b> {square_size} mm<br>"
            f"<b>Tip:</b> Use the preview on the left to position the board "
            f"and move it to different angles between shots."
        )
        info_label.setWordWrap(True)
        info_label.setStyleSheet(
            f"background-color: {BG_CARD}; color: {TEXT_SECONDARY};"
            f"padding: 10px; border-radius: 6px; font-size: 12px;"
        )
        v.addWidget(info_label)
        return group

    def _create_capture_config_group(self):
        group = QGroupBox("Capture Configuration")
        grid = QGridLayout(group)
        grid.setSpacing(6)

        grid.addWidget(QLabel("Number of images:"), 0, 0)
        self.num_images_spin = QSpinBox()
        self.num_images_spin.setRange(15, 50)
        self.num_images_spin.setValue(self.camera_config.stereo.min_calibration_images)
        self.num_images_spin.setSuffix(" images")
        grid.addWidget(self.num_images_spin, 0, 1)

        grid.addWidget(QLabel("Settling time:"), 1, 0)
        self.delay_spin = QDoubleSpinBox()
        self.delay_spin.setRange(5.0, 30.0)
        self.delay_spin.setValue(8.0)
        self.delay_spin.setSuffix(" s")
        self.delay_spin.setDecimals(1)
        grid.addWidget(self.delay_spin, 1, 1)

        grid.addWidget(QLabel("Initial countdown:"), 2, 0)
        self.countdown_spin = QSpinBox()
        self.countdown_spin.setRange(5, 30)
        self.countdown_spin.setValue(10)
        self.countdown_spin.setSuffix(" s")
        grid.addWidget(self.countdown_spin, 2, 1)

        return group

    def _create_current_status_group(self):
        group = QGroupBox("Current Calibration Status")
        v = QVBoxLayout(group)
        self.status_label = QLabel()
        self.status_label.setAlignment(Qt.AlignCenter)
        v.addWidget(self.status_label)
        self.details_label = QLabel()
        self.details_label.setWordWrap(True)
        self.details_label.setVisible(False)
        self.details_label.setStyleSheet(
            f"color: {TEXT_SECONDARY}; font-size: 12px; background: transparent;"
        )
        v.addWidget(self.details_label)
        return group

    def _create_progress_group(self):
        group = QGroupBox("Progress")
        v = QVBoxLayout(group)

        self.countdown_label = QLabel("Ready — start the calibration below")
        self.countdown_label.setFont(QFont("Segoe UI", 13, QFont.Bold))
        self.countdown_label.setAlignment(Qt.AlignCenter)
        self.countdown_label.setStyleSheet(
            f"background-color: {BG_CARD}; color: {TEXT_SECONDARY};"
            f"padding: 12px; border-radius: 6px; border: 1px solid {BORDER_SUBTLE};"
        )
        v.addWidget(self.countdown_label)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setVisible(False)
        v.addWidget(self.progress_bar)

        self.progress_message = QLabel("")
        self.progress_message.setAlignment(Qt.AlignCenter)
        self.progress_message.setVisible(False)
        self.progress_message.setStyleSheet(
            f"color: {TEXT_SECONDARY}; font-size: 12px; background: transparent;"
        )
        v.addWidget(self.progress_message)
        return group

    def _create_log_group(self):
        group = QGroupBox("Activity Log")
        v = QVBoxLayout(group)
        self.log_text = QTextEdit()
        self.log_text.setMaximumHeight(110)
        self.log_text.setReadOnly(True)
        v.addWidget(self.log_text)
        return group

    def _create_buttons(self):
        row = QHBoxLayout()
        row.setSpacing(8)

        self.btn_start = QPushButton("▶  Start Calibration")
        self.btn_start.setFixedHeight(40)
        self.btn_start.setStyleSheet(
            f"QPushButton {{ background-color: {ACCENT_GREEN}; color: white;"
            f"font-weight: bold; font-size: 14px; border-radius: 6px; }}"
            f"QPushButton:hover {{ background-color: #15803D; }}"
            f"QPushButton:disabled {{ background-color: {BG_CARD}; color: {TEXT_DIM}; }}"
        )
        self.btn_start.clicked.connect(self.start_calibration)
        self.btn_start.setEnabled(self.cameras_available)
        row.addWidget(self.btn_start)

        self.btn_process_existing = QPushButton("📂  Process Existing Session")
        self.btn_process_existing.setFixedHeight(40)
        self.btn_process_existing.setStyleSheet(
            f"QPushButton {{ background-color: {ACCENT_BLUE}; color: white;"
            f"font-weight: bold; font-size: 13px; border-radius: 6px; }}"
            f"QPushButton:hover {{ background-color: #60A5FA; }}"
        )
        self.btn_process_existing.clicked.connect(self.process_existing_session)
        row.addWidget(self.btn_process_existing)

        self.btn_cancel = QPushButton("✕  Cancel")
        self.btn_cancel.setFixedHeight(40)
        self.btn_cancel.setStyleSheet(
            f"QPushButton {{ background-color: {BG_CARD}; color: {TEXT_PRIMARY};"
            f"border-radius: 6px; }}"
            f"QPushButton:hover {{ background-color: {RED_OFF}; color: white; }}"
        )
        self.btn_cancel.clicked.connect(self.cancel_calibration)
        self.btn_cancel.setEnabled(False)
        row.addWidget(self.btn_cancel)

        return row

    # ── Navigation ────────────────────────────────────────────────────────────

    def _go_back(self):
        """Navigate back to the dashboard page."""
        self.stop_preview_for_capture()
        main_window = self.window()
        if hasattr(main_window, 'navigate_to'):
            main_window.navigate_to(0)  # PAGE_DASHBOARD

    # ── Preview helpers ───────────────────────────────────────────────────────

    def start_preview_for_positioning(self):
        """Start the calibration page's own camera previews."""
        if not self.cameras_available:
            return
        try:
            self.left_preview.start_preview()
            self.right_preview.start_preview()
            self.btn_preview_start.setEnabled(False)
            self.btn_preview_stop.setEnabled(True)
            self.btn_preview_start.setText("▶  Preview Active")
        except Exception as e:
            self.add_log_message(f"Error starting preview: {e}", "WARNING")

    def stop_preview_for_capture(self):
        """Stop the calibration page's camera previews."""
        try:
            self.left_preview.stop_preview()
            self.right_preview.stop_preview()
            self.btn_preview_start.setEnabled(self.cameras_available)
            self.btn_preview_stop.setEnabled(False)
            self.btn_preview_start.setText("▶  Start Preview")
        except Exception as e:
            self.add_log_message(f"Error stopping preview: {e}", "WARNING")

    # ── Calibration status ────────────────────────────────────────────────────

    def _load_current_calibration_status(self):
        if self.camera_config.is_calibrated():
            self.status_label.setText("✓ System Calibrated")
            self.status_label.setStyleSheet(
                f"color: {GREEN_ON}; font-weight: bold; font-size: 14px;"
                f"background: transparent;"
            )
            if hasattr(self.camera_config, 'calibration_data'):
                calib_data = self.camera_config.calibration_data
                err = calib_data.get('calibration_error', 0)
                date = calib_data.get('calibration_date', 'N/A')
                self.details_label.setText(
                    f"Date: {date}  ·  Reprojection error: {err:.3f} px"
                )
                self.details_label.setVisible(True)
        else:
            self.status_label.setText("✗ Calibration Required")
            self.status_label.setStyleSheet(
                f"color: {RED_OFF}; font-weight: bold; font-size: 14px;"
                f"background: transparent;"
            )
            self.details_label.setVisible(False)

    # ── Countdown helpers ─────────────────────────────────────────────────────

    def _set_countdown_style(self, title, subtitle, seconds):
        self.countdown_label.setText(f"{title}\n{subtitle}")
        if seconds > 3:
            color, bg = ACCENT_BLUE, "#1E3A5F"
        elif seconds > 0:
            color, bg = RED_OFF, "#450A0A"
        elif seconds == -1:    # processing
            color, bg = YELLOW_WARN, "#451A03"
        elif seconds == -2:    # success
            color, bg = GREEN_ON, "#052E16"
        elif seconds == -3:    # error
            color, bg = RED_OFF, "#450A0A"
        else:                  # standby
            color, bg = TEXT_SECONDARY, BG_CARD

        self.countdown_label.setStyleSheet(
            f"background-color: {bg}; color: {color};"
            f"padding: 12px; border-radius: 6px; border: 1px solid {color};"
            f"font-size: 14px; font-weight: bold;"
        )

    # ── Capture loop ──────────────────────────────────────────────────────────

    def start_calibration(self):
        reply = QMessageBox.question(
            self, "Confirm Calibration",
            f"This will capture {self.num_images_spin.value()} image pairs.\n\n"
            "Start?",
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return

        self.btn_start.setEnabled(False)
        self.btn_cancel.setEnabled(True)
        self.progress_bar.setVisible(True)
        self.progress_message.setVisible(True)

        self.is_capturing    = True
        self.images_to_capture = self.num_images_spin.value()
        self.images_captured = 0

        try:
            self.capture_session_dir = self.stereo_camera.create_calibration_session_dir()
            self.add_log_message(
                f"Session created at: {self.capture_session_dir}", "INFO"
            )
        except Exception as e:
            QMessageBox.critical(
                self, "Error", f"Could not create session directory: {e}"
            )
            self.cancel_calibration()
            return

        self._start_countdown(self.countdown_spin.value(), self._tick_initial)

    def _start_countdown(self, seconds, tick_fn):
        self.countdown_seconds = seconds
        try:
            self.countdown_timer.timeout.disconnect()
        except TypeError:
            pass
        self.countdown_timer.timeout.connect(tick_fn)
        self.countdown_timer.start(1000)
        tick_fn()

    def _tick_initial(self):
        if self.countdown_seconds > 0:
            self._set_countdown_style(
                "PREPARE THE BOARD!",
                f"Initial capture in: {self.countdown_seconds}s",
                self.countdown_seconds,
            )
            self.countdown_seconds -= 1
        else:
            self.countdown_timer.stop()
            self._capture_one_pair()

    def _tick_between_shots(self):
        if self.countdown_seconds > 0:
            self._set_countdown_style(
                "REPOSITION THE BOARD!",
                f"Next capture in: {self.countdown_seconds}s",
                self.countdown_seconds,
            )
            self.countdown_seconds -= 1
        else:
            self.countdown_timer.stop()
            self._capture_one_pair()

    def _capture_one_pair(self):
        if not self.is_capturing:
            return
        self.progress_message.setText(
            f"Capturing image {self.images_captured + 1} / {self.images_to_capture}..."
        )
        self.add_log_message(
            f"Capturing pair {self.images_captured + 1}", "INFO"
        )
        self.stop_preview_for_capture()
        QTimer.singleShot(500, self._execute_capture)

    def _execute_capture(self):
        try:
            self.stereo_camera.capture_single_calibration_pair(
                self.capture_session_dir, self.images_captured
            )
            self.images_captured += 1
            progress = int((self.images_captured / self.images_to_capture) * 50)
            self.progress_bar.setValue(progress)
        except Exception as e:
            self.add_log_message(f"Fatal capture error: {e}", "ERROR")
            QMessageBox.critical(self, "Capture Error", f"Capture failed: {e}")
            self.cancel_calibration()
            return

        if self.images_captured >= self.images_to_capture:
            self.add_log_message("Image capture completed.", "INFO")
            self._process_calibration_images()
        else:
            self.start_preview_for_positioning()
            self._start_countdown(int(self.delay_spin.value()), self._tick_between_shots)

    def _process_calibration_images(self):
        self.add_log_message("Starting calibration processing...", "INFO")
        self._set_countdown_style("PROCESSING", "Calculating parameters...", -1)
        self.progress_message.setText("Processing images...")

        self.processing_thread = CalibrationProcessingThread(
            self.camera_config, self.capture_session_dir
        )
        self.processing_thread.progress_update.connect(self._update_progress)
        self.processing_thread.log_message.connect(self.add_log_message)
        self.processing_thread.calibration_complete.connect(self._on_calibration_complete)
        self.processing_thread.start()

    def _on_calibration_complete(self, success, result):
        self.is_capturing = False

        if success:
            self.add_log_message("✓ Calibration completed successfully", "INFO")
            self._set_countdown_style("CALIBRATION SUCCESSFUL", "System ready!", -2)
            self.progress_bar.setValue(100)

            avg_dist = result.get('average_distance_meters', 0) * 100
            dist_msg = f"Average distance to board: {avg_dist:.1f} cm"
            self.add_log_message(dist_msg, "INFO")

            # Notify main window
            self.calibration_updated.emit()

            QMessageBox.information(
                self, "Success",
                f"Calibration completed and saved.\n\n{dist_msg}"
            )

            # Navigate back to dashboard after a short delay
            QTimer.singleShot(500, lambda: self.window().navigate_to(0)
                              if hasattr(self.window(), 'navigate_to') else None)
        else:
            error_details = result.get('error', 'Unknown error')
            self.add_log_message(f"✗ Calibration failed: {error_details}", "ERROR")
            self._set_countdown_style("CALIBRATION ERROR", "Check log and try again", -3)
            QMessageBox.critical(
                self, "Calibration Error", f"Calibration failed:\n\n{error_details}"
            )
            self._reset_ui_after_calibration()

    # ── Progress / log ────────────────────────────────────────────────────────

    def _update_progress(self, progress, message):
        self.progress_bar.setValue(progress)
        self.progress_message.setText(message)

    def add_log_message(self, message, level="INFO"):
        ts = datetime.now().strftime("%H:%M:%S")
        color = {
            "ERROR":   RED_OFF,
            "WARNING": YELLOW_WARN,
        }.get(level, TEXT_SECONDARY)
        self.log_text.append(
            f'<span style="color:{TEXT_DIM}">[{ts}]</span> '
            f'<span style="color:{color}">{level}: {message}</span>'
        )
        self.log_text.verticalScrollBar().setValue(
            self.log_text.verticalScrollBar().maximum()
        )

    # ── Cancel / reset ────────────────────────────────────────────────────────

    def cancel_calibration(self):
        self.add_log_message("Calibration canceled by user", "WARNING")
        self.is_capturing = False

        if self.countdown_timer.isActive():
            self.countdown_timer.stop()

        if self.processing_thread and self.processing_thread.isRunning():
            self.processing_thread.stop()
            self.processing_thread.wait(2000)

        self._reset_ui_after_calibration()

    def _reset_ui_after_calibration(self):
        self.btn_start.setEnabled(self.cameras_available)
        self.btn_process_existing.setEnabled(True)
        self.btn_cancel.setEnabled(False)
        self.is_capturing = False
        self.progress_bar.setVisible(False)
        self.progress_message.setVisible(False)
        self._set_countdown_style(
            "Ready to start", "Use the buttons below", 0
        )
        self.start_preview_for_positioning()

    # ── Process existing session ──────────────────────────────────────────────

    def process_existing_session(self):
        from PyQt5.QtWidgets import QFileDialog, QInputDialog

        calibration_dir = Path("data/calibration")
        if not calibration_dir.exists():
            QMessageBox.warning(
                self, "Error", "Calibration directory not found"
            )
            return

        sessions = [
            item for item in calibration_dir.iterdir()
            if item.is_dir()
            and item.name.startswith("calibration_")
            and not item.name.endswith("_BACKUP")
            and any(item.glob("calib_pair_*"))
        ]

        if not sessions:
            QMessageBox.warning(
                self, "No Sessions",
                "No calibration sessions found.\n\n"
                "First capture calibration photos on the Raspberry Pi."
            )
            return

        session_names = [s.name for s in sorted(sessions, reverse=True)]
        session_name, ok = QInputDialog.getItem(
            self, "Select Session",
            "Select calibration session to process:",
            session_names, 0, False,
        )
        if not ok or not session_name:
            return

        selected_session = calibration_dir / session_name
        num_pairs = len(list(selected_session.glob("calib_pair_*")))

        reply = QMessageBox.question(
            self, "Confirm Processing",
            f"Session: {session_name}\n"
            f"Image pairs: {num_pairs}\n\n"
            "Process this session to recalibrate?",
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return

        self.add_log_message(f"Processing session: {session_name}", "INFO")
        self.btn_process_existing.setEnabled(False)
        self.btn_start.setEnabled(False)
        self.btn_cancel.setEnabled(True)
        self.progress_bar.setVisible(True)
        self.progress_message.setVisible(True)
        self.progress_bar.setValue(0)

        self.processing_thread = CalibrationProcessingThread(
            self.camera_config, selected_session
        )
        self.processing_thread.progress_update.connect(self._update_progress)
        self.processing_thread.log_message.connect(self.add_log_message)
        self.processing_thread.calibration_complete.connect(self._on_calibration_complete)
        self.processing_thread.start()


# Alias for any code that still references the old QDialog name
CalibrationDialog = CalibrationPage
