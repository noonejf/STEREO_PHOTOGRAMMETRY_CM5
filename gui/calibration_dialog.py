#!/usr/bin/env python3
"""
Página de calibración de cámaras estéreo.
Reemplaza el CalibrationDialog (QDialog) por CalibrationPage (QWidget)
integrado en el QStackedWidget de la ventana única.

Diseño: split horizontal
  Izquierda: vista previa en vivo (sus propios CameraPreviewWidget)
  Derecha:   controles: config, progreso, log, botones
"""

from datetime import datetime
from pathlib import Path

import cv2

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QProgressBar, QTextEdit, QGroupBox,
    QGridLayout, QMessageBox, QSpinBox,
    QDoubleSpinBox, QFrame, QSplitter, QScrollArea,
)
from PyQt5.QtCore import QEvent, QThread, pyqtSignal, QTimer, Qt
from PyQt5.QtGui import QFont

from camera.camera_calibration import CameraCalibrator
from camera.guided_session import DEFAULT_MIN_PER_BIN, DEFAULT_TILT_BINS
from gui.camera_preview import CameraPreviewWidget
from gui.guided_calibration import (
    DETECT_WIDTH, GuidedAnalysisWorker, GuidedStatusPanel,
)
from gui.icons import get_icon
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

        # ── Estado del flujo guiado ──────────────────────────────────────────
        self.guided_worker = None
        self.guided_active = False
        self._guided_busy = False        # capturando o esperando a rearmar
        self._last_left = None
        self._last_right = None
        self._rearm_left = 0
        self._match_hint = ""

        # Pide fotogramas al ritmo de la interfaz, no al de la camara. El
        # worker descarta lo que no alcanza a procesar, asi que subir esto no
        # acelera nada y solo gasta CPU.
        self._analysis_timer = QTimer(self)
        self._analysis_timer.setInterval(120)
        self._analysis_timer.timeout.connect(self._tick_analysis)

        self._rearm_timer = QTimer(self)
        self._rearm_timer.setInterval(1000)
        self._rearm_timer.timeout.connect(self._tick_rearm)

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
        bb.setContentsMargins(16, 0, 16, 0)

        # No back button: the rail on the left already has Dashboard, and a
        # second control for the same destination only adds noise.
        page_title = QLabel("Stereo Camera Calibration")
        page_title.setStyleSheet(
            f"color: {TEXT_PRIMARY}; font-weight: bold; font-size: 15px;"
            f"background: transparent;"
        )
        bb.addWidget(page_title)
        bb.addStretch()
        root.addWidget(back_bar)

        # ── Main split: left preview | right controls ─────────────────────────
        splitter = QSplitter(Qt.Horizontal)
        splitter.setChildrenCollapsible(True)
        self._splitter = splitter
        splitter.setStyleSheet(f"background-color: {BG_DEEP};")

        splitter.addWidget(self._build_preview_panel())

        # Envuelto en QScrollArea: red de seguridad para que en pantallas
        # pequenas los botones de abajo (Start/Cancel) siempre sean
        # alcanzables con scroll, en vez de quedar cortados fuera de la
        # ventana si el contenido no entra verticalmente.
        controls_scroll = QScrollArea()
        controls_scroll.setWidgetResizable(True)
        controls_scroll.setFrameShape(QFrame.NoFrame)
        controls_scroll.setStyleSheet(f"background-color: {BG_DEEP};")
        controls_scroll.setWidget(self._build_controls_panel())
        controls_scroll.setMinimumWidth(0)
        self._controls_scroll = controls_scroll
        splitter.addWidget(controls_scroll)
        # Mas espacio para las vistas que para los controles: durante la
        # captura lo que se mira es la imagen y el aviso grande.
        splitter.setSizes([620, 480])

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
        self._preview_title = title
        v.addWidget(title)

        # Aviso compacto para el modo ampliado. Al ocultar los controles se
        # ocultaba tambien el aviso grande, que es justo lo que el operador
        # necesita leer mientras posiciona el tablero, asi que la instruccion
        # se replica aqui con lo imprescindible: que hacer, inclinacion
        # actual y cuanto lleva.
        self.preview_banner = QLabel("")
        self.preview_banner.setAlignment(Qt.AlignCenter)
        self.preview_banner.setWordWrap(True)
        self.preview_banner.setVisible(False)
        v.addWidget(self.preview_banner)

        self.left_preview = CameraPreviewWidget(
            "Left Camera (CAM0)", 0, self.camera_config
        )
        self.right_preview = CameraPreviewWidget(
            "Right Camera (CAM1)", 1, self.camera_config
        )

        # Las dos vistas en un splitter cuya orientacion cambia con la forma
        # del panel. Apiladas en vertical la altura disponible se parte en
        # dos y limita la imagen, de modo que una imagen 4:3 deja la mitad
        # del ancho vacio: medido, 280x210 en una ventana de 1280x720. Lado a
        # lado cada vista usa toda la altura y la imagen crece bastante.
        # Ademas el splitter deja al operador repartir el espacio a mano.
        self._preview_split = QSplitter(Qt.Vertical)
        self._preview_split.setChildrenCollapsible(False)
        self._preview_split.setHandleWidth(4)
        self._preview_split.setStyleSheet(
            f"QSplitter::handle {{ background-color: {BORDER_SUBTLE}; }}")
        self._preview_split.addWidget(self.left_preview)
        self._preview_split.addWidget(self.right_preview)
        v.addWidget(self._preview_split, 1)

        # Preview toggle buttons
        btn_row = QHBoxLayout()
        self.btn_preview_start = QPushButton("  Start Preview")
        self.btn_preview_start.setIcon(get_icon("play", TEXT_PRIMARY, 16))
        self.btn_preview_start.setStyleSheet(
            f"QPushButton {{ background-color: {BG_CARD}; color: {TEXT_PRIMARY}; }}"
            f"QPushButton:hover {{ background-color: #3B4B60; }}"
        )
        self.btn_preview_start.clicked.connect(self.start_preview_for_positioning)

        self.btn_preview_stop = QPushButton("  Stop Preview")
        self.btn_preview_stop.setIcon(get_icon("stop", TEXT_PRIMARY, 16))
        self.btn_preview_stop.setStyleSheet(
            f"QPushButton {{ background-color: {BG_CARD}; color: {TEXT_PRIMARY}; }}"
            f"QPushButton:hover {{ background-color: #3B4B60; }}"
        )
        self.btn_preview_stop.clicked.connect(self.stop_preview_for_capture)
        self.btn_preview_stop.setEnabled(False)

        self.btn_expand = QPushButton("  Enlarge views")
        self.btn_expand.setIcon(get_icon("expand", TEXT_PRIMARY, 16))
        self.btn_expand.setCheckable(True)
        self.btn_expand.setToolTip(
            "Hide the controls so the views take the whole window. Useful while "
            "positioning the board. The large prompt stays visible above."
        )
        self.btn_expand.setStyleSheet(
            f"QPushButton {{ background-color: {BG_CARD}; color: {TEXT_PRIMARY}; }}"
            f"QPushButton:hover {{ background-color: #3B4B60; }}"
            f"QPushButton:checked {{ background-color: {ACCENT_CYAN}; color: #06202A;"
            f"font-weight: bold; }}"
        )
        self.btn_expand.toggled.connect(self._toggle_expanded_preview)

        btn_row.addWidget(self.btn_preview_start)
        btn_row.addWidget(self.btn_preview_stop)
        btn_row.addWidget(self.btn_expand)
        v.addLayout(btn_row)

        hint = QLabel(
            "The board must be fully visible in BOTH cameras."
        )
        hint.setStyleSheet(
            f"color: {TEXT_DIM}; font-size: 11px; background: transparent;"
        )
        hint.setAlignment(Qt.AlignCenter)
        hint.setWordWrap(True)
        v.addWidget(hint)

        # Explicit minimum. Without it the panel's own minimum grows when the
        # views go side by side (two labels plus a three-button row), and the
        # splitter could then no longer shrink it back: leaving the enlarged
        # mode returned the controls as a 100 px sliver.
        panel.setMinimumWidth(300)
        for b in (self.btn_preview_start, self.btn_preview_stop, self.btn_expand):
            b.setMinimumWidth(0)

        self._preview_panel = panel
        panel.installEventFilter(self)
        return panel

    def eventFilter(self, obj, event):
        """Re-orient the views when the panel shape changes."""
        if (obj is getattr(self, "_preview_panel", None)
                and event.type() == QEvent.Resize):
            self._reflow_previews(event.size())
        return super().eventFilter(obj, event)

    def _reflow_previews(self, size):
        """
        Apilar o poner lado a lado segun la forma del panel.

        Apiladas, la altura se parte en dos y es ella la que limita la
        imagen, asi que una imagen 4:3 deja la mitad del ancho vacio. Si el
        panel es mas ancho que alto, lado a lado cada vista usa toda la
        altura y la imagen sale bastante mayor.
        """
        # Umbral en 1.0: con el aspecto del sensor impuesto (4:3), en cuanto
        # el panel es mas ancho que alto conviene lado a lado, porque ahi la
        # altura deja de ser el limite y la imagen crece.
        wanted = (Qt.Horizontal if size.width() >= size.height()
                  else Qt.Vertical)
        if self._preview_split.orientation() == wanted:
            return
        self._preview_split.setOrientation(wanted)
        half = (size.width() if wanted == Qt.Horizontal else size.height()) // 2
        self._preview_split.setSizes([half, half])

    def _toggle_expanded_preview(self, expanded: bool):
        """Give the whole window to the views, or bring the controls back."""
        scroll = getattr(self, "_controls_scroll", None)
        if scroll is None:
            return
        # Hiding a pane makes the splitter forget its share, and on the way
        # back it restored the controls as a sliver with scrollbars. Save the
        # split before hiding and put it back afterwards.
        # Collapse the pane to zero width rather than hiding it. Hiding a
        # widget inside a QSplitter makes the splitter forget its share, and
        # the relayout that follows the re-show overwrote whatever sizes were
        # set afterwards: the controls came back as a sliver. Width zero
        # produces the same visual result and keeps the split intact.
        if expanded:
            self._saved_split = self._splitter.sizes()
            self._splitter.setSizes([sum(self._saved_split), 0])
        else:
            saved = getattr(self, "_saved_split", None)
            if not (saved and len(saved) == 2 and saved[1] > 40):
                total = max(self._splitter.width(), 800)
                saved = [int(total * 0.56), int(total * 0.44)]
            self._splitter.setSizes(saved)
        self._preview_title.setVisible(not expanded)
        self.preview_banner.setVisible(expanded)
        self.btn_expand.setText(
            "  Back to controls" if expanded
            else "  Enlarge views")

    def _set_preview_banner(self, title, subtitle, kind, tilt=None, st=None):
        """Mirror the main prompt in the strip used by the enlarged mode."""
        palette = {
            "idle":    (TEXT_SECONDARY, BG_CARD),
            "search":  (YELLOW_WARN, "#3A2E08"),
            "reject":  (RED_OFF, "#450A0A"),
            "pose":    (ACCENT_CYAN, "#0E3A44"),
            "hold":    (GREEN_ON, "#052E16"),
            "capture": (ACCENT_BLUE, "#1E3A5F"),
            "done":    (GREEN_ON, "#052E16"),
        }
        color, bg = palette.get(kind, palette["idle"])
        bits = []
        if self._match_hint:
            bits.append(self._match_hint.upper())
        if tilt is not None:
            bits.append(f"{tilt:.0f}°")
        if st is not None:
            bits.append(f"{st.accepted}/{st.target} views")
            done = sum(1 for c in st.bin_counts.values() if c >= 3)
            bits.append(f"{done}/4 ranges")
        right = "  ·  ".join(bits)
        self.preview_banner.setText(
            f"<span style='font-size:26px; font-weight:bold'>{title}</span>"
            f"&nbsp;&nbsp;<span style='font-size:14px'>{subtitle}</span>"
            + (f"<br><span style='font-size:15px; font-weight:bold'>{right}</span>"
               if right else ""))
        self.preview_banner.setStyleSheet(
            f"background-color:{bg}; color:{color}; border:2px solid {color};"
            f"border-radius:8px; padding:8px;")

    def _build_controls_panel(self):
        panel = QWidget()
        panel.setStyleSheet(f"background-color: {BG_DEEP};")
        v = QVBoxLayout(panel)
        v.setContentsMargins(10, 10, 10, 10)
        v.setSpacing(6)

        # Orden: primero lo que se pulsa durante una sesion, despues lo
        # que solo se consulta. Antes los botones principales quedaban por
        # debajo del borde visible en pantallas de 720 px de alto.
        v.addWidget(self._create_guided_group())
        v.addLayout(self._create_buttons())
        v.addWidget(self._create_current_status_group())
        v.addWidget(self._create_board_info_group())
        v.addWidget(self._create_capture_config_group())
        v.addWidget(self._create_progress_group())
        v.addWidget(self._create_log_group())
        v.addStretch()

        return panel

    def _create_guided_group(self):
        group = QGroupBox("Guided calibration")
        v = QVBoxLayout(group)
        v.setSpacing(8)

        self.guided_panel = GuidedStatusPanel(DEFAULT_TILT_BINS, DEFAULT_MIN_PER_BIN)
        v.addWidget(self.guided_panel)

        cfg = QHBoxLayout()
        cfg.setSpacing(6)
        cfg.addWidget(QLabel("Repositioning pause:"))
        self.rearm_spin = QSpinBox()
        self.rearm_spin.setRange(0, 15)
        self.rearm_spin.setValue(3)
        self.rearm_spin.setSuffix(" s")
        self.rearm_spin.setToolTip(
            "Time after each shot before the system looks for a pose again, so "
            "you can move without it firing immediately."
        )
        cfg.addWidget(self.rearm_spin)
        cfg.addStretch()
        v.addLayout(cfg)

        self.btn_guided_finish = QPushButton("  Finish with the views collected")
        self.btn_guided_finish.setIcon(get_icon("check", TEXT_SECONDARY, 16))
        self.btn_guided_finish.setFixedHeight(32)
        self.btn_guided_finish.setStyleSheet(
            f"QPushButton {{ background-color: {BG_CARD}; color: {TEXT_SECONDARY};"
            f"border: 1px solid {BORDER_SUBTLE}; border-radius: 6px;"
            f"font-size: 12px; }}"
            f"QPushButton:hover {{ background-color: {YELLOW_WARN}; color: #1A1203; }}"
            f"QPushButton:disabled {{ color: {TEXT_DIM}; border-color: {BG_CARD}; }}"
        )
        self.btn_guided_finish.setToolTip(
            "Close the session and calibrate with what has been captured, even "
            "if tilt ranges are missing. It names what is missing first."
        )
        self.btn_guided_finish.clicked.connect(self.finish_guided_early)
        self.btn_guided_finish.setEnabled(False)
        v.addWidget(self.btn_guided_finish)

        self.btn_guided = QPushButton("  Start guided calibration")
        self.btn_guided.setIcon(get_icon("calibration", "#06202A", 16))
        self.btn_guided.setFixedHeight(44)
        self.btn_guided.setStyleSheet(
            f"QPushButton {{ background-color: {ACCENT_CYAN}; color: #06202A;"
            f"font-weight: bold; font-size: 15px; border-radius: 6px; }}"
            f"QPushButton:hover {{ background-color: #67E8F9; }}"
            f"QPushButton:disabled {{ background-color: {BG_CARD}; color: {TEXT_DIM}; }}"
        )
        self.btn_guided.clicked.connect(self.start_guided_calibration)
        self.btn_guided.setEnabled(self.cameras_available)
        v.addWidget(self.btn_guided)

        return group

    def _create_board_info_group(self):
        group = QGroupBox("Calibration board")
        v = QVBoxLayout(group)
        st = self.camera_config.stereo

        # Mostrar el tablero que el sistema usa de verdad. Este panel
        # describia el tablero de ajedrez antiguo (9x6, 24 mm) aunque la
        # deteccion pasa por ChArUco desde hace tiempo, asi que indicaba
        # imprimir un tablero que el software no reconoce.
        if getattr(st, "use_charuco", False):
            info_label = QLabel(
                f"<b>Type:</b> ChArUco (generate it with generate_charuco.py)<br>"
                f"<b>Squares:</b> {st.charuco_squares_x} x {st.charuco_squares_y}"
                f"  &nbsp;<b>Dictionary:</b> {st.charuco_dict_name}<br>"
                f"<b>Square side:</b> {st.charuco_square_size_mm} mm"
                f"  &nbsp;<b>Marker:</b> {st.charuco_marker_size_mm} mm<br>"
                f"<b>In use:</b> the ChArUco PDF printed and mounted on a "
                f"rigid folder. Zhang's method assumes the target is planar, "
                f"so if accuracy ever falls short of the budget, check the "
                f"mounting before suspecting the software."
            )
        else:
            bs = st.calibration_board_size
            info_label = QLabel(
                f"<b>Type:</b> plain chessboard<br>"
                f"<b>Inner corners:</b> {bs[0]} x {bs[1]} "
                f"({bs[0] * bs[1]} total)<br>"
                f"<b>Square side:</b> {st.calibration_square_size_mm} mm"
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

        self.countdown_label = QLabel("Listo. Usa los botones de abajo")
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

        self.btn_start = QPushButton("  Legacy flow (countdown)")
        self.btn_start.setIcon(get_icon("clock", TEXT_SECONDARY, 16))
        self.btn_start.setFixedHeight(36)
        self.btn_start.setToolTip(
            "The previous flow: it fires every N seconds without looking at the "
            "pose, and it is the one that produced the 23 failed attempts. "
            "Kept in case it is needed; prefer the guided flow above."
        )
        self.btn_start.setStyleSheet(
            f"QPushButton {{ background-color: {BG_CARD}; color: {TEXT_SECONDARY};"
            f"border: 1px solid {BORDER_SUBTLE}; font-size: 12px;"
            f"border-radius: 6px; }}"
            f"QPushButton:hover {{ background-color: #3B4B60; color: {TEXT_PRIMARY}; }}"
            f"QPushButton:disabled {{ background-color: {BG_CARD}; color: {TEXT_DIM}; }}"
        )
        self.btn_start.clicked.connect(self.start_calibration)
        self.btn_start.setEnabled(self.cameras_available)
        row.addWidget(self.btn_start)

        self.btn_process_existing = QPushButton("  Process existing session")
        self.btn_process_existing.setIcon(get_icon("folder", "white", 16))
        self.btn_process_existing.setFixedHeight(36)
        self.btn_process_existing.setStyleSheet(
            f"QPushButton {{ background-color: {ACCENT_BLUE}; color: white;"
            f"font-weight: bold; font-size: 13px; border-radius: 6px; }}"
            f"QPushButton:hover {{ background-color: #60A5FA; }}"
        )
        self.btn_process_existing.clicked.connect(self.process_existing_session)
        row.addWidget(self.btn_process_existing)

        self.btn_cancel = QPushButton("  Cancel")
        self.btn_cancel.setIcon(get_icon("cross", TEXT_PRIMARY, 16))
        self.btn_cancel.setFixedHeight(36)
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
        if self.guided_active:
            self._stop_guided_machinery()
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
            self.btn_preview_start.setText("  Preview Active")
        except Exception as e:
            self.add_log_message(f"Error starting preview: {e}", "WARNING")

    def stop_preview_for_capture(self):
        """Stop the calibration page's camera previews."""
        try:
            self.left_preview.stop_preview()
            self.right_preview.stop_preview()
            self.btn_preview_start.setEnabled(self.cameras_available)
            self.btn_preview_stop.setEnabled(False)
            self.btn_preview_start.setText("  Start Preview")
        except Exception as e:
            self.add_log_message(f"Error stopping preview: {e}", "WARNING")

    # ── Calibration status ────────────────────────────────────────────────────

    def _load_current_calibration_status(self):
        if self.camera_config.is_calibrated():
            self.status_label.setText("System Calibrated")
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

    # ── Flujo guiado ──────────────────────────────────────────────────────────

    def start_guided_calibration(self):
        """
        Arrancar el bucle guiado.

        A diferencia del flujo por cuenta regresiva, aqui no se dispara cada N
        segundos: se dispara cuando la pose que sostiene el operador es nitida,
        esta quieta, la ven las dos camaras y aporta informacion que el
        conjunto todavia no tiene. Una foto rechazada no gasta un cupo.
        """
        target = self.num_images_spin.value()
        reply = QMessageBox.question(
            self, "Guided calibration",
            f"The system will guide you until it has {target} useful views.\n\n"
            "It only fires when the pose is worth keeping, so it may look at "
            "many more frames than that. You need to cover the four tilt "
            "ranges shown on screen.\n\n"
            "Start?",
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return

        try:
            self.capture_session_dir = self.stereo_camera.create_calibration_session_dir()
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Could not create the session: {e}")
            return

        self.add_log_message(f"Guided session at: {self.capture_session_dir}", "INFO")

        self.guided_active = True
        self._guided_busy = False
        self.images_captured = 0
        self.images_to_capture = target
        self.is_capturing = True

        self.btn_guided.setEnabled(False)
        self.btn_guided_finish.setEnabled(False)
        self.btn_start.setEnabled(False)
        self.btn_process_existing.setEnabled(False)
        self.btn_cancel.setEnabled(True)
        self.progress_bar.setVisible(True)
        self.progress_message.setVisible(True)

        self.guided_worker = GuidedAnalysisWorker(
            self.camera_config, target_views=target,
            min_per_bin=DEFAULT_MIN_PER_BIN, parent=self)
        self.guided_worker.analysis.connect(self._on_guided_analysis)
        self.guided_worker.failed.connect(
            lambda m: self.add_log_message(f"Analisis: {m}", "WARNING"))
        self.guided_worker.start()

        self.start_preview_for_positioning()
        try:
            self.left_preview.frame_ready.connect(self._on_left_frame)
            self.right_preview.frame_ready.connect(self._on_right_frame)
        except Exception:
            pass

        self._analysis_timer.start()
        self.guided_panel.set_banner(
            "Show the board", "Both cameras must see it", "search")

    def _on_left_frame(self, frame):
        self._last_left = frame

    def _on_right_frame(self, frame):
        self._last_right = frame

    @staticmethod
    def _to_detect_gray(frame):
        """Reducir y pasar a gris. El preview llega en RGB."""
        h, w = frame.shape[:2]
        if w > DETECT_WIDTH:
            s = DETECT_WIDTH / float(w)
            frame = cv2.resize(frame, (DETECT_WIDTH, int(round(h * s))),
                               interpolation=cv2.INTER_AREA)
        if frame.ndim == 3:
            return cv2.cvtColor(frame, cv2.COLOR_RGB2GRAY)
        return frame

    def _tick_analysis(self):
        if not self.guided_active or self._guided_busy:
            return
        if self._last_left is None or self._last_right is None:
            return
        try:
            gl = self._to_detect_gray(self._last_left)
            gr = self._to_detect_gray(self._last_right)
        except Exception as e:
            self.add_log_message(f"Unreadable preview: {e}", "WARNING")
            return
        self.guided_worker.offer(gl, gr)

    def _on_guided_analysis(self, res):
        if not self.guided_active:
            return

        st = res.get("status_obj")
        tilt = res.get("tilt_deg")
        status = res.get("status")

        active_bin = None
        if tilt is not None:
            for lo, hi, label in DEFAULT_TILT_BINS:
                if lo <= tilt < hi:
                    active_bin = label
                    break

        if st is not None:
            self.guided_panel.update_status(
                st, active_bin, hint_text=self._translate_hint(st.hint))
            self.btn_guided_finish.setEnabled(st.accepted >= 6)
            self.progress_bar.setValue(int(round(100 * st.overall_progress())))
            self.progress_message.setText(
                f"{st.accepted} of {st.target} useful views "
                f"({st.seen} frames seen)")
        self.guided_panel.set_tilt(tilt, active_bin)

        # Pintar el objetivo en las DOS vistas. El worker lo calcula sobre
        # la imagen reducida de deteccion, asi que hay que llevarlo a la
        # escala del preview; si no, la guia quedaria desplazada respecto de
        # lo que el operador ve.
        self._match_hint = ("" if res.get("match", 0.0) >= 0.80
                            else res.get("match_hint", ""))
        self._apply_target_overlays(res)

        if self._guided_busy:
            return

        if status == "accepted":
            self.add_log_message(f"View kept: {res.get('message')}", "INFO")
            self._guided_capture()
        elif status == "no_board":
            self.guided_panel.set_banner(
                "Show the board", res.get("message", ""), "search")
            self._set_preview_banner("Show the board",
                                     res.get("message", ""), "search", tilt, st)
        elif status == "rejected_quality":
            sub = self._friendly_reason(res.get("message", ""))
            mv, mx = res.get("motion_px"), res.get("max_motion_px")
            if mv is not None and mx and mv > mx:
                # Dar la cifra, no solo el adjetivo: asi el operador sabe si
                # le falta mucho o esta a punto.
                sub = (f"Moving: {mv:.1f} px, needs to drop below {mx:.1f}. "
                       f"Hold it still for a second")
            self.guided_panel.set_banner("Adjust", sub, "reject")
            self._set_preview_banner("Adjust", sub, "reject", tilt, st)
        elif status == "rejected_pose":
            # El detalle de que falta ya aparece en la caja de ayuda, debajo.
            # Repetirlo aqui solo gastaba espacio.
            msg = res.get("message", "")
            sub = ("You already have this pose" if "duplicate" in msg.lower()
                   else "That tilt is outside every useful range")
            self.guided_panel.set_banner("Change the pose", sub, "pose")
            self._set_preview_banner("Change the pose", sub, "pose", tilt, st)

    def _apply_target_overlays(self, res):
        """Draw the pose to match on both previews, at preview scale."""
        tl, tr = res.get("target_left"), res.get("target_right")
        frame = self._last_left
        if tl is None or frame is None:
            self.left_preview.clear_overlay()
            self.right_preview.clear_overlay()
            return

        scale = frame.shape[1] / float(DETECT_WIDTH)
        matched = res.get("match", 0.0) >= 0.80
        label = "hold it there" if matched else res.get("match_hint", "")

        self.left_preview.set_overlay(tl * scale, matched, label)
        if tr is not None:
            self.right_preview.set_overlay(tr * scale, matched, "")

    @staticmethod
    def _friendly_reason(message: str) -> str:
        """
        Turn the technical rejection reason into something to act on.

        The measurement modules report what is wrong; the operator needs to
        know what to do about it, which is not the same sentence.
        """
        m = message.lower()
        if "blur" in m:
            return "Blurred: check focus, or hold the board steadier"
        if "moving" in m:
            return "Moving: hold it still for a second"
        if "corner" in m or "detected" in m:
            return "Too few corners visible: show the whole board"
        if "clipped" in m:
            return "Blown highlights: turn the board or lower the light"
        if "too small" in m:
            return "Too far: bring the board closer"
        if "too large" in m:
            return "Too close: move the board back"
        return message

    @staticmethod
    def _translate_hint(hint: str) -> str:
        """
        Make the session hint read as an instruction.

        The session states what is missing in its own terms; this puts it in
        the imperative and spells out the bin labels.
        """
        import re as _re

        bins = {
            "frontal, for the distortion terms":
                "frontal, for the distortion coefficients",
            "slightly tilted": "slightly tilted",
            "clearly tilted": "clearly tilted",
            "strongly tilted": "strongly tilted",
        }

        m = _re.match(r"need (\d+) more view\(s\) at ([\d.]+) to ([\d.]+) "
                      r"degrees of tilt \((.+)\)", hint)
        if m:
            n, lo, hi, label = m.groups()
            noun = "view" if n == "1" else "views"
            return (f"{n} more {noun} between {float(lo):.0f} and "
                    f"{float(hi):.0f} degrees of tilt "
                    f"({bins.get(label, label)})")

        m = _re.match(r"(\d+) more view\(s\)\. Least determined: (\w+); (.+)",
                      hint)
        if m:
            n, worst, what = m.groups()
            noun = "view" if n == "1" else "views"
            return (f"{n} more {noun}. Least determined parameter is "
                    f"{worst}: {what}")

        m = _re.match(r"(\d+) more view\(s\)$", hint)
        if m:
            n = m.group(1)
            return f"{n} more view" if n == "1" else f"{n} more views"

        if hint.startswith("complete"):
            return "Done: tilt ranges covered and target reached"
        return hint

    def _guided_capture(self):
        """Pose buena: congelar el analisis y tomar el par a resolucion completa."""
        self._guided_busy = True
        self.guided_worker.set_paused(True)
        self._analysis_timer.stop()
        self.guided_panel.set_banner(
            "HOLD STILL", "Taking the shot, do not move the board", "hold")
        self._set_preview_banner(
            "HOLD STILL", "Taking the shot, do not move the board", "hold")
        self.stop_preview_for_capture()
        QTimer.singleShot(350, self._guided_execute_capture)

    def _guided_execute_capture(self):
        if not self.guided_active:
            return
        try:
            self.stereo_camera.capture_single_calibration_pair(
                self.capture_session_dir, self.images_captured)
            self.images_captured += 1
        except Exception as e:
            self.add_log_message(f"Capture error: {e}", "ERROR")
            QMessageBox.critical(self, "Capture error", str(e))
            self.cancel_calibration()
            return

        st = self.guided_worker.session.status() if self.guided_worker.session else None
        if st is not None and st.complete:
            self.add_log_message(
                f"Target reached: {st.accepted} useful views out of "
                f"{st.seen} frames seen", "INFO")
            self._finish_guided()
            return

        self._rearm_left = self.rearm_spin.value()
        self.start_preview_for_positioning()
        if self._rearm_left > 0:
            self._tick_rearm()
            self._rearm_timer.start()
        else:
            self._resume_guided()

    def _tick_rearm(self):
        if not self.guided_active:
            self._rearm_timer.stop()
            return
        if self._rearm_left > 0:
            hint = ""
            if self.guided_worker and self.guided_worker.session:
                hint = self._translate_hint(self.guided_worker.session.hint())
            self.guided_panel.set_banner(
                f"Move  {self._rearm_left}", hint, "capture")
            self._set_preview_banner(
                f"Move  {self._rearm_left}", hint, "capture")
            self._rearm_left -= 1
        else:
            self._rearm_timer.stop()
            self._resume_guided()

    def _resume_guided(self):
        if not self.guided_active:
            return
        self._guided_busy = False
        self.guided_worker.set_paused(False)
        self._analysis_timer.start()
        hint = ""
        if self.guided_worker and self.guided_worker.session:
            hint = self._translate_hint(self.guided_worker.session.hint())
        self.guided_panel.set_banner("Looking for a pose", hint, "search")
        self._set_preview_banner("Looking for a pose", hint, "search")

    def finish_guided_early(self):
        """
        Close the session before all four ranges are covered.

        Physical space, board size or the operator's reach can make one tilt
        unattainable, and having no way out but cancelling and losing the
        whole session would be worse. It names what is missing first, because
        an empty range is exactly what left the focal length unrecoverable in
        the 23 previous attempts.
        """
        if not self.guided_active or self.guided_worker is None:
            return
        session = self.guided_worker.session
        if session is None:
            return

        st = session.status()
        missing = [f"{lo:.0f} to {hi:.0f} degrees ({st.bin_counts[lab]} of "
                   f"{session.min_per_bin})"
                   for lo, hi, lab in session.tilt_bins
                   if st.bin_counts[lab] < session.min_per_bin]

        if missing:
            detail = "\n".join(f"  - {m}" for m in missing)
            msg = (f"You have {st.accepted} useful views, but these tilt "
                   f"ranges are not covered:\n\n{detail}\n\n"
                   "An empty range leaves parameters poorly determined. "
                   "With the highest tilt range empty the focal length can "
                   "stay unresolved, which is exactly what happened in the "
                   "23 previous attempts.\n\n"
                   "Calibrate anyway with what there is?")
        else:
            msg = (f"All four ranges are covered and you have {st.accepted} "
                   f"views of {st.target}.\n\nCalibrate now?")

        if QMessageBox.question(self, "Finish early", msg,
                                QMessageBox.Yes | QMessageBox.No,
                                QMessageBox.No) != QMessageBox.Yes:
            return

        if self.images_captured < 1:
            QMessageBox.warning(self, "No captures",
                                "No photograph has been saved yet.")
            return

        self.add_log_message(
            f"Session closed by the operator with {st.accepted} views", "WARNING")
        if missing:
            self.add_log_message(
                f"Ranges not covered: {'; '.join(missing)}", "WARNING")
        self._finish_guided()

    def _finish_guided(self):
        """Cerrar el bucle y pasar la sesion al ajuste a resolucion completa."""
        self._stop_guided_machinery()
        self.guided_panel.set_banner(
            "Captures complete", "Computing the calibration", "done")
        self._set_preview_banner(
            "Captures complete", "Computing the calibration", "done")

        if self.guided_worker and self.guided_worker.session:
            res = self.guided_worker.session.result()
            self.guided_panel.set_spread(res.get("tilt_spread_deg", 0.0))
            self.add_log_message(
                f"Guided: {res['n_views']} views from {res['frames_seen']} "
                f"frames, tilt spread "
                f"{res.get('tilt_spread_deg', 0):.0f} degrees", "INFO")
            for reason, n in sorted(res.get("rejections", {}).items(),
                                    key=lambda kv: -kv[1])[:5]:
                self.add_log_message(f"  rejected, {reason}: {n}", "INFO")

        self._process_calibration_images()

    def _stop_guided_machinery(self):
        """Soltar temporizadores, senales y el hilo. Seguro de llamar dos veces."""
        self.guided_active = False
        self._analysis_timer.stop()
        self._rearm_timer.stop()
        for prev, slot in ((getattr(self, "left_preview", None), self._on_left_frame),
                           (getattr(self, "right_preview", None), self._on_right_frame)):
            if prev is not None:
                try:
                    prev.frame_ready.disconnect(slot)
                except (TypeError, RuntimeError):
                    pass
        if self.guided_worker is not None:
            try:
                self.guided_worker.stop()
            except Exception:
                pass
        self._last_left = None
        self._last_right = None
        for prev in (getattr(self, "left_preview", None),
                     getattr(self, "right_preview", None)):
            if prev is not None:
                try:
                    prev.clear_overlay()
                except Exception:
                    pass

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
            self.add_log_message("Calibration completed successfully", "INFO")
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

        if self.guided_active:
            self._stop_guided_machinery()
            self.guided_panel.set_banner(
                "Cancelled", "You can start again whenever you want", "idle")

        if self.countdown_timer.isActive():
            self.countdown_timer.stop()

        if self.processing_thread and self.processing_thread.isRunning():
            self.processing_thread.stop()
            self.processing_thread.wait(2000)

        self._reset_ui_after_calibration()

    def _reset_ui_after_calibration(self):
        self.btn_start.setEnabled(self.cameras_available)
        self.btn_guided.setEnabled(self.cameras_available)
        self.btn_guided_finish.setEnabled(False)
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
