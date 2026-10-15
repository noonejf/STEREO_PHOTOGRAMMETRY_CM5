#!/usr/bin/env python3
"""
Interfaz del flujo de calibracion guiado.

Conecta camera/guided_session.py con la pagina de calibracion. La logica de
decision no vive aqui: aqui vive el hilo que la ejecuta fuera de la UI y los
widgets que muestran su estado.

Tres cosas gobiernan el diseno:

1. El operador sostiene el tablero lejos de la pantalla. Todo lo que necesita
   leer mientras calibra va en texto grande, con color, y en una sola linea.
   El detalle numerico va aparte, para revisarlo despues.

2. La deteccion ChArUco y el reajuste de la calibracion son caros y crecen con
   el numero de vistas. Corren en GuidedAnalysisWorker, nunca en el hilo de la
   interfaz, y sobre una copia reducida del preview. La UI no se bloquea.

3. El preview y la captura a resolucion completa compiten por la camara: hay
   que detener uno para hacer la otra. Por eso el guiado analiza el preview
   pero la foto que entra a la calibracion es un par a resolucion completa.
   Es la division que describe el capitulo 4 del entregable de calibracion.
"""

from __future__ import annotations

from typing import Optional, Tuple

import cv2
import numpy as np

from PyQt5.QtCore import QMutex, QThread, QWaitCondition, Qt, pyqtSignal
from PyQt5.QtWidgets import (
    QFrame, QGridLayout, QHBoxLayout, QLabel, QProgressBar, QVBoxLayout, QWidget,
)

from camera.calibration_guidance import GateAThresholds
from camera.guided_session import DEFAULT_MIN_PER_BIN, GuidedCalibrationSession

# Paleta, igual que el resto de la aplicacion
BG_PANEL = "#1E293B"
BG_CARD = "#273548"
TEXT_PRIMARY = "#E2E8F0"
TEXT_SECONDARY = "#94A3B8"
TEXT_DIM = "#64748B"
BORDER_SUBTLE = "#334155"
GREEN_ON = "#22C55E"
RED_OFF = "#EF4444"
YELLOW_WARN = "#EAB308"
ACCENT_CYAN = "#22D3EE"
ACCENT_BLUE = "#3B82F6"

#: Ancho al que se reduce el preview para detectar. El preview nativo es
#: 1920x1440; detectar ahi cuesta demasiado para un bucle interactivo, y el
#: angulo de inclinacion, que es lo que decide, no necesita esa resolucion.
DETECT_WIDTH = 960


def build_guided_board(camera_config):
    """Construir el tablero ChArUco desde la configuracion del proyecto.

    Devuelve (board, detector, dictionary). ``detector`` es None en OpenCV
    antiguo, donde hay que usar la ruta de interpolateCornersCharuco.
    """
    st = camera_config.stereo
    adict = cv2.aruco.getPredefinedDictionary(
        getattr(cv2.aruco, st.charuco_dict_name))
    sq = st.charuco_square_size_mm / 1000.0
    mk = st.charuco_marker_size_mm / 1000.0

    if hasattr(cv2.aruco, "CharucoBoard"):
        board = cv2.aruco.CharucoBoard(
            (st.charuco_squares_x, st.charuco_squares_y), sq, mk, adict)
        return board, cv2.aruco.CharucoDetector(board), adict

    board = cv2.aruco.CharucoBoard_create(
        st.charuco_squares_x, st.charuco_squares_y, sq, mk, adict)
    return board, None, adict


def detect_charuco(gray, board, detector, adict):
    """Devolver (corners, ids) o (None, None)."""
    if detector is not None:
        corners, ids, _, _ = detector.detectBoard(gray)
        if corners is None or len(corners) == 0:
            return None, None
        return corners, ids

    params = cv2.aruco.DetectorParameters_create()
    mc, mids, _ = cv2.aruco.detectMarkers(gray, adict, parameters=params)
    if mids is None or len(mids) == 0:
        return None, None
    _, cc, ci = cv2.aruco.interpolateCornersCharuco(mc, mids, gray, board)
    if cc is None or len(cc) == 0:
        return None, None
    return cc, ci


# ── Hilo de analisis ─────────────────────────────────────────────────────────

class GuidedAnalysisWorker(QThread):
    """
    Corre deteccion y la decision de la sesion fuera del hilo de interfaz.

    Recibe fotogramas por :meth:`offer`, que nunca bloquea: si el hilo esta
    ocupado, el fotograma nuevo reemplaza al pendiente. Asi el analisis va
    siempre sobre lo mas reciente y la cola no crece, que es lo que produciria
    retraso visible entre lo que el operador hace y lo que la pantalla dice.
    """

    analysis = pyqtSignal(dict)
    failed = pyqtSignal(str)

    def __init__(self, camera_config, target_views: int,
                 min_per_bin: int = DEFAULT_MIN_PER_BIN,
                 max_motion_px: float = 3.5, parent=None):
        super().__init__(parent)
        self.camera_config = camera_config
        self.target_views = int(target_views)
        self.min_per_bin = int(min_per_bin)
        # El umbral por defecto del modulo de medidas (2 px) se penso para un
        # flujo donde la camara esta fija. Aqui el tablero va en la mano: a un
        # metro, un pixel de la imagen reducida son unos 0.8 mm, asi que 2 px
        # rechaza el temblor normal de una mano firme y el sistema no
        # dispararia nunca. 3.5 px deja pasar la mano quieta y sigue
        # rechazando el tablero en movimiento.
        self.max_motion_px = float(max_motion_px)

        self._mutex = QMutex()
        self._wait = QWaitCondition()
        self._pending: Optional[Tuple[np.ndarray, np.ndarray]] = None
        self._running = True
        self._paused = False

        self.board, self.detector, self.adict = build_guided_board(camera_config)
        self.session: Optional[GuidedCalibrationSession] = None

    # -- API desde el hilo de interfaz ------------------------------------

    def offer(self, gray_left: np.ndarray, gray_right: np.ndarray) -> None:
        """Ofrecer un par de fotogramas. Reemplaza cualquier par pendiente."""
        self._mutex.lock()
        self._pending = (gray_left, gray_right)
        self._mutex.unlock()
        self._wait.wakeAll()

    def set_paused(self, paused: bool) -> None:
        """Pausar el analisis mientras se toma la foto a resolucion completa."""
        self._mutex.lock()
        self._paused = bool(paused)
        self._pending = None
        self._mutex.unlock()

    def stop(self) -> None:
        self._mutex.lock()
        self._running = False
        self._mutex.unlock()
        self._wait.wakeAll()
        self.wait(3000)

    # -- Bucle del hilo ---------------------------------------------------

    def run(self) -> None:
        while True:
            self._mutex.lock()
            while self._running and (self._pending is None or self._paused):
                self._wait.wait(self._mutex, 200)
            if not self._running:
                self._mutex.unlock()
                return
            gray_l, gray_r = self._pending
            self._pending = None
            self._mutex.unlock()

            try:
                self._process(gray_l, gray_r)
            except Exception as exc:                      # noqa: BLE001
                self.failed.emit(str(exc))

    def _process(self, gray_l: np.ndarray, gray_r: np.ndarray) -> None:
        if self.session is None:
            h, w = gray_l.shape[:2]
            self.session = GuidedCalibrationSession(
                self.board, (w, h),
                target_views=self.target_views,
                thresholds=GateAThresholds(max_motion_px=self.max_motion_px),
                min_per_bin=self.min_per_bin,
                # Reajustar en cada vista haria crecer el costo hasta
                # bloquear el ritmo; cada tres da realimentacion suficiente.
                refit_every=3,
                compute_max_ere=True,
            )

        corners_l, ids_l = detect_charuco(gray_l, self.board, self.detector, self.adict)

        # Condicion binocular: la vista solo sirve para los extrinsecos si
        # ambas camaras ven el tablero. Se comprueba antes de ofrecerla a la
        # sesion para no gastar un cupo en algo que no se puede emparejar.
        seen_right = False
        if corners_l is not None:
            corners_r, _ = detect_charuco(gray_r, self.board, self.detector, self.adict)
            seen_right = corners_r is not None and len(corners_r) >= 6

        if corners_l is None or not seen_right:
            st = self.session.status()
            self.analysis.emit({
                "status": "no_board",
                "message": ("tablero no visible" if corners_l is None
                            else "la camara derecha no lo ve"),
                "tilt_deg": None,
                "corners": None,
                "status_obj": st,
            })
            return

        res = self.session.submit(gray_l, corners_l, ids_l)
        st = self.session.status()
        pts = np.asarray(corners_l, np.float32).reshape(-1, 2)

        motion = None
        if res.verdict is not None and res.verdict.metrics is not None:
            motion = res.verdict.metrics.motion_px

        self.analysis.emit({
            "status": res.status,
            "message": res.message,
            "tilt_deg": None if res.pose is None else res.pose.tilt_deg,
            "motion_px": motion,
            "max_motion_px": self.max_motion_px,
            "corners": pts,
            "status_obj": st,
        })


# ── Widgets ──────────────────────────────────────────────────────────────────

class BinChips(QWidget):
    """Los cuatro rangos de inclinacion, con cuantas vistas lleva cada uno."""

    def __init__(self, tilt_bins, min_per_bin: int, parent=None):
        super().__init__(parent)
        self.min_per_bin = min_per_bin
        self._chips = {}

        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)

        for lo, hi, label in tilt_bins:
            chip = QFrame()
            chip.setMinimumHeight(54)
            v = QVBoxLayout(chip)
            v.setContentsMargins(6, 5, 6, 5)
            v.setSpacing(1)

            rng = QLabel(f"{lo:.0f}-{hi:.0f}°")
            rng.setAlignment(Qt.AlignCenter)
            rng.setStyleSheet(
                f"color:{TEXT_SECONDARY}; font-size:11px; background:transparent;")

            cnt = QLabel(f"0/{min_per_bin}")
            cnt.setAlignment(Qt.AlignCenter)
            cnt.setStyleSheet(
                f"color:{TEXT_PRIMARY}; font-size:17px; font-weight:bold;"
                f"background:transparent;")

            v.addWidget(rng)
            v.addWidget(cnt)
            lay.addWidget(chip)
            self._chips[label] = (chip, cnt, lo, hi)

        self._paint()

    def update_counts(self, bin_counts, active_label: Optional[str] = None):
        for label, (chip, cnt, lo, hi) in self._chips.items():
            n = bin_counts.get(label, 0)
            cnt.setText(f"{n}/{self.min_per_bin}")
        self._paint(bin_counts, active_label)

    def _paint(self, bin_counts=None, active_label=None):
        for label, (chip, cnt, lo, hi) in self._chips.items():
            n = 0 if bin_counts is None else bin_counts.get(label, 0)
            done = n >= self.min_per_bin
            if label == active_label:
                border, bg = ACCENT_CYAN, "#0E3A44"
            elif done:
                border, bg = GREEN_ON, "#0B2E18"
            else:
                border, bg = BORDER_SUBTLE, BG_CARD
            chip.setStyleSheet(
                f"QFrame {{ background-color:{bg}; border:2px solid {border};"
                f"border-radius:6px; }}")
            cnt.setStyleSheet(
                f"color:{GREEN_ON if done else TEXT_PRIMARY}; font-size:17px;"
                f"font-weight:bold; background:transparent;")


class GuidedStatusPanel(QWidget):
    """
    Lo que el operador mira mientras calibra.

    Arriba la orden, en grande y con color, legible desde donde se sostiene el
    tablero. Abajo el detalle, para revisarlo al terminar.
    """

    def __init__(self, tilt_bins, min_per_bin: int, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)

        # Orden principal
        self.banner = QLabel("Listo para empezar")
        self.banner.setAlignment(Qt.AlignCenter)
        self.banner.setWordWrap(True)
        self.banner.setMinimumHeight(92)
        lay.addWidget(self.banner)

        # Inclinacion actual y lo que falta
        row = QHBoxLayout()
        row.setSpacing(8)

        self.tilt_label = QLabel("--°")
        self.tilt_label.setAlignment(Qt.AlignCenter)
        self.tilt_label.setMinimumWidth(110)
        self.tilt_label.setStyleSheet(
            f"background-color:{BG_CARD}; color:{ACCENT_CYAN};"
            f"border:1px solid {BORDER_SUBTLE}; border-radius:6px;"
            f"font-size:30px; font-weight:bold; padding:4px;")
        row.addWidget(self.tilt_label)

        self.hint_label = QLabel(
            "Aqui aparece que inclinacion falta mientras calibras.")
        self.hint_label.setWordWrap(True)
        self.hint_label.setAlignment(Qt.AlignVCenter | Qt.AlignLeft)
        self.hint_label.setStyleSheet(
            f"background-color:{BG_CARD}; color:{TEXT_PRIMARY};"
            f"border:1px solid {BORDER_SUBTLE}; border-radius:6px;"
            f"font-size:14px; padding:8px;")
        row.addWidget(self.hint_label, 1)
        lay.addLayout(row)

        # Cobertura por rango
        lay.addWidget(self._section("Cobertura de inclinaciones"))
        self.chips = BinChips(tilt_bins, min_per_bin)
        lay.addWidget(self.chips)

        # Progreso
        lay.addWidget(self._section("Progreso de la calibracion"))
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setFormat("%p%")
        self.progress.setMinimumHeight(22)
        self.progress.setStyleSheet(
            f"QProgressBar {{ background-color:{BG_CARD}; color:{TEXT_PRIMARY};"
            f"border:1px solid {BORDER_SUBTLE}; border-radius:5px;"
            f"text-align:center; font-weight:bold; }}"
            f"QProgressBar::chunk {{ background-color:{ACCENT_BLUE};"
            f"border-radius:4px; }}")
        lay.addWidget(self.progress)

        note = QLabel("No cuenta fotos: mide cobertura de poses y cuanto se han "
                      "estabilizado los parametros.")
        note.setWordWrap(True)
        note.setStyleSheet(
            f"color:{TEXT_DIM}; font-size:11px; background:transparent;")
        lay.addWidget(note)

        # Metricas
        lay.addWidget(self._section("Datos de la sesion"))
        # Dos columnas de pares: la misma informacion en la mitad de alto,
        # que es lo que permite que los botones principales quepan sin
        # desplazar en pantallas de 720 px.
        grid = QGridLayout()
        grid.setHorizontalSpacing(14)
        grid.setVerticalSpacing(3)
        self._metrics = {}
        rows = [
            ("kept", "Vistas aceptadas"),
            ("fx", "Incertidumbre de fx"),
            ("seen", "Fotogramas vistos"),
            ("ere", "Max ERE"),
            ("spread", "Rango de inclinacion"),
            ("worst", "Peor determinado"),
        ]
        for i, (key, title) in enumerate(rows):
            r, c = divmod(i, 2)
            k = QLabel(title)
            k.setStyleSheet(
                f"color:{TEXT_SECONDARY}; font-size:11px; background:transparent;")
            v = QLabel("--")
            v.setStyleSheet(
                f"color:{TEXT_PRIMARY}; font-size:12px; font-weight:bold;"
                f"background:transparent;")
            grid.addWidget(k, r, c * 2)
            grid.addWidget(v, r, c * 2 + 1, alignment=Qt.AlignRight)
            self._metrics[key] = v
        grid.setColumnStretch(1, 1)
        grid.setColumnStretch(3, 1)
        lay.addLayout(grid)

        self.set_banner("Listo para empezar", "Pulsa Iniciar calibracion guiada", "idle")

    @staticmethod
    def _section(text: str) -> QLabel:
        lab = QLabel(text.upper())
        lab.setStyleSheet(
            f"color:{TEXT_DIM}; font-size:10px; font-weight:bold;"
            f"letter-spacing:1px; background:transparent; margin-top:4px;")
        return lab

    def set_banner(self, title: str, subtitle: str = "", kind: str = "idle"):
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
        sub = f"<br><span style='font-size:15px; font-weight:normal'>{subtitle}</span>" if subtitle else ""
        self.banner.setText(
            f"<span style='font-size:30px; font-weight:bold'>{title}</span>{sub}")
        self.banner.setStyleSheet(
            f"background-color:{bg}; color:{color}; border:2px solid {color};"
            f"border-radius:8px; padding:10px;")

    def set_tilt(self, tilt_deg: Optional[float], active_bin: Optional[str] = None):
        if tilt_deg is None:
            self.tilt_label.setText("--°")
            self.tilt_label.setStyleSheet(
                f"background-color:{BG_CARD}; color:{TEXT_DIM};"
                f"border:1px solid {BORDER_SUBTLE}; border-radius:6px;"
                f"font-size:30px; font-weight:bold; padding:4px;")
        else:
            self.tilt_label.setText(f"{tilt_deg:.0f}°")
            self.tilt_label.setStyleSheet(
                f"background-color:{BG_CARD}; color:{ACCENT_CYAN};"
                f"border:1px solid {ACCENT_CYAN}; border-radius:6px;"
                f"font-size:30px; font-weight:bold; padding:4px;")

    def update_status(self, st, active_bin: Optional[str] = None,
                      hint_text: Optional[str] = None):
        """Refrescar todo lo que viene de un SessionStatus.

        ``hint_text`` permite a la pagina pasar la instruccion ya traducida,
        porque la sesion la genera en ingles.
        """
        self.chips.update_counts(st.bin_counts, active_bin)
        self.progress.setValue(int(round(100 * st.overall_progress())))
        self.hint_label.setText(hint_text if hint_text is not None else st.hint)

        self._metrics["kept"].setText(f"{st.accepted} / {st.target}")
        self._metrics["seen"].setText(str(st.seen))

        unc = st.uncertainty
        if unc is None:
            self._metrics["fx"].setText("faltan vistas para ajustar")
            self._metrics["worst"].setText("--")
        else:
            fx = unc.values.get("fx", 0.0)
            sfx = unc.sigmas.get("fx", 0.0)
            rel = (100.0 * sfx / fx) if fx else 0.0
            colour = GREEN_ON if rel < 0.3 else (YELLOW_WARN if rel < 1.0 else RED_OFF)
            self._metrics["fx"].setText(f"{rel:.2f} %")
            self._metrics["fx"].setStyleSheet(
                f"color:{colour}; font-size:12px; font-weight:bold;"
                f"background:transparent;")
            worst, iod = unc.max_iod()
            self._metrics["worst"].setText(f"{worst} (IOD {iod:.2f})")

        self._metrics["ere"].setText(
            "--" if st.max_ere_px is None else f"{st.max_ere_px:.2f} px")

    def set_spread(self, spread_deg: float):
        self._metrics["spread"].setText(f"{spread_deg:.0f}°")
