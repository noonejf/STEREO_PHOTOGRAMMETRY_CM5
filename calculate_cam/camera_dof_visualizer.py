"""
Camera Depth of Field Visualizer
=================================
Depth-of-field visualizer for cameras with interchangeable lenses.
Includes pixel-per-thread calculation at different distances.
"""

import sys
import numpy as np
import math
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QGroupBox, QLabel, QComboBox, QDoubleSpinBox, QSpinBox,
    QSlider, QSplitter, QFrame, QGridLayout, QSizePolicy
)
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QFont, QColor, QPalette
import matplotlib
matplotlib.use('Qt5Agg')
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
import matplotlib.patches as mpatches
import matplotlib.ticker as ticker

# ─────────────────────────────────────────────────────────────────────────────
# CAMERA AND LENS DATA
# ─────────────────────────────────────────────────────────────────────────────

CAMERAS = {
    "Raspberry Pi HQ Camera (IMX477)": {
        "sensor_width_mm":  6.287,
        "sensor_height_mm": 4.712,
        "resolution_h":     4056,
        "resolution_v":     3040,
        "pixel_size_um":    1.55,
        "optical_size":     '1/2.3"',
        "description":      "12.3 MP — sensor 6.287×4.712 mm — pixel 1.55 µm",
        "lenses": ["Lens 6mm F1.2 (CS-Mount)", "Lens 8mm F1.6-F16 Zoom (C-Mount)", "Varifocal Lens 2.8-12mm F1.6 (C-Mount)"],
    },
    "Raspberry Pi Camera Module 3 (IMX708)": {
        "sensor_width_mm":  7.4,
        "sensor_height_mm": 5.55,
        "resolution_h":     9152,
        "resolution_v":     6944,
        "pixel_size_um":    1.4,          # estimated from 1/1.7" sensor
        "optical_size":     '1/1.7"',
        "description":      "64 MP — sensor 7.4×5.55 mm — fixed manual focus",
        "lenses": ["Integrated Lens 5.1mm F1.8 (fixed)"],
    },
}

LENSES = {
    "Lens 6mm F1.2 (CS-Mount)": {
        "focal_length_mm": 6.0,
        "f_number_min":    1.2,
        "f_number_max":    1.2,       # fixed lens
        "adjustable_f":   False,
        "mod_mm":          0.2,        # minimum focus distance 0.2 mm
        "fov_h_deg":       65.0,
        "mount":           "CS",
        "description":     "6 mm F1.2 · FOV 65° · MOD 0.2 mm",
    },
    "Lens 8mm F1.6-F16 Zoom (C-Mount)": {
        "focal_length_mm": 8.0,
        "f_number_min":    1.6,
        "f_number_max":    16.0,
        "adjustable_f":   True,
        "mod_mm":          150.0,      # MOD 0.15 m = 150 mm
        "fov_h_deg":       44.0,       # on 1/2.3" sensor
        "mount":           "C",
        "description":     "8 mm F1.6-F16 · FOV 44° · MOD 0.15 m",
    },
    "Integrated Lens 5.1mm F1.8 (fixed)": {
        "focal_length_mm": 5.1,
        "f_number_min":    1.8,
        "f_number_max":    1.8,
        "adjustable_f":   False,
        "mod_mm":          80.0,
        "fov_h_deg":       84.0,
        "mount":           "integrated",
        "description":     "5.1 mm F1.8 · FOV 84° diagonal · MOD 0.08 m",
    },
    "Varifocal Lens 2.8-12mm F1.6 (C-Mount)": {
        "focal_length_mm":     2.8,
        "focal_length_min_mm": 2.8,
        "focal_length_max_mm": 12.0,
        "adjustable_focal":    True,
        "f_number_min":        1.6,
        "f_number_max":        1.6,
        "adjustable_f":        False,
        "mod_mm":              300.0,
        "fov_h_deg":           120.0,
        "fov_h_tele_deg":      38.0,
        "mount":               "C",
        "description":         "2.8-12 mm F1.6 varifocal · FOV 120°→38° (IMX477) · MOD 0.3 m",
    },
}

# ─────────────────────────────────────────────────────────────────────────────
# OPTICS PHYSICS
# ─────────────────────────────────────────────────────────────────────────────

def circle_of_confusion(sensor_width_mm, resolution_h):
    """
    Circle of confusion (CoC) in mm.
    We use the 1-pixel criterion as the sharpness limit.
    """
    pixel_pitch_mm = sensor_width_mm / resolution_h
    return pixel_pitch_mm  # 1 pixel = CoC


def image_distance(focal_mm, focus_distance_mm):
    """
    Image distance (v) using the thin-lens equation:
      1/f = 1/v - 1/u  →  v = f*u / (u - f)
    focus_distance_mm: object distance from the lens (u > 0)
    """
    u = focus_distance_mm
    f = focal_mm
    if u <= f:
        return None   # object inside focal point → image at infinity or virtual
    v = (f * u) / (u - f)
    return v


def depth_of_field(focal_mm, f_number, coc_mm, focus_distance_m):
    """
    Depth of field using the standard hyperfocal formula.
    Returns (near_m, far_m, dof_m).
    """
    f   = focal_mm / 1000.0        # in metres
    N   = f_number
    c   = coc_mm / 1000.0          # in metres
    D   = focus_distance_m         # metres

    # Hyperfocal distance
    H = (f**2) / (N * c) + f

    near = (H * D) / (H + D)
    if D >= H:
        far = float('inf')
    else:
        far = (H * D) / (H - D)

    dof = far - near if far != float('inf') else float('inf')
    return near, far, dof, H


def pixels_per_mm_at_distance(sensor_width_mm, resolution_h, focal_mm, distance_m):
    """
    How many pixels correspond to 1 mm of the object at 'distance_m'.
    Scale = f / (d - f)  →  pixels/mm object = (pixels/mm sensor) / magnification
    magnification = f / (d_mm - f)
    """
    d_mm = distance_m * 1000.0
    f    = focal_mm

    if d_mm <= f:
        return None

    magnification = f / (d_mm - f)          # v/u
    px_per_mm_sensor = resolution_h / sensor_width_mm
    px_per_mm_object = px_per_mm_sensor * magnification
    return px_per_mm_object


def thread_pixels(sensor_width_mm, resolution_h, focal_mm, distance_m, thread_diameter_mm):
    """
    Pixels occupied by the thread (diameter) at a given distance.
    """
    ppmm = pixels_per_mm_at_distance(sensor_width_mm, resolution_h, focal_mm, distance_m)
    if ppmm is None:
        return None
    return ppmm * thread_diameter_mm


# ─────────────────────────────────────────────────────────────────────────────
# MATPLOTLIB WIDGET
# ─────────────────────────────────────────────────────────────────────────────

class DoFCanvas(FigureCanvas):
    def __init__(self, parent=None):
        self.fig = Figure(figsize=(10, 5), facecolor='#1e1e2e')
        super().__init__(self.fig)
        self.setParent(parent)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.ax = self.fig.add_subplot(111)
        self._style_ax()

    def _style_ax(self):
        ax = self.ax
        ax.set_facecolor('#181825')
        for spine in ax.spines.values():
            spine.set_color('#45475a')
        ax.tick_params(colors='#cdd6f4', labelsize=9)
        ax.xaxis.label.set_color('#cdd6f4')
        ax.yaxis.label.set_color('#cdd6f4')
        ax.title.set_color('#cdd6f4')
        self.fig.tight_layout(pad=2)

    def plot(self, near_m, far_m, focus_m, hyperfocal_m,
             camera_name, lens_name, f_number,
             near_px, far_px, thread_mm, coc_mm,
             focus_distance_m):
        ax = self.ax
        ax.clear()
        self._style_ax()

        MAX_DIST = 100.0
        far_plot = min(far_m, MAX_DIST) if far_m != float('inf') else MAX_DIST

        # ── Out-of-focus zone (full background) ──
        ax.barh(0, MAX_DIST, left=0, height=0.5,
                color='#313244', alpha=0.6, zorder=1)

        # ── In-focus zone ──
        dof_start = max(near_m, 0)
        dof_end   = far_plot
        ax.barh(0, dof_end - dof_start, left=dof_start, height=0.5,
                color='#a6e3a1', alpha=0.85, zorder=2, label='In-focus zone')

        # ── Focus point line ──
        ax.axvline(focus_m, color='#f38ba8', linewidth=2.5,
                   zorder=5, label=f'Focus: {focus_m:.2f} m')

        # ── DoF limits ──
        ax.axvline(near_m, color='#fab387', linewidth=1.5,
                   linestyle='--', zorder=4, label=f'Near: {near_m:.3f} m')
        if far_m != float('inf'):
            ax.axvline(far_m, color='#89dceb', linewidth=1.5,
                       linestyle='--', zorder=4, label=f'Far: {far_m:.3f} m')
        else:
            ax.axvline(MAX_DIST, color='#89dceb', linewidth=1.5,
                       linestyle='--', zorder=4, label='Far: ∞')

        # ── Hyperfocal ──
        if hyperfocal_m <= MAX_DIST:
            ax.axvline(hyperfocal_m, color='#cba6f7', linewidth=1.2,
                       linestyle=':', zorder=3, label=f'Hyperfocal: {hyperfocal_m:.1f} m')

        # ── Origin (camera) ──
        ax.annotate('📷 Camera\n(origin)', xy=(0, 0), xytext=(2, 0.35),
                    color='#cdd6f4', fontsize=8,
                    arrowprops=dict(arrowstyle='->', color='#cdd6f4', lw=1))

        # ── Pixel labels ──
        info_color = '#f9e2af'
        y_text = -0.28

        if near_px is not None:
            ax.text(near_m, y_text,
                    f'{near_px:.2f} px\n(near)',
                    color=info_color, fontsize=7.5, ha='center', va='top',
                    bbox=dict(boxstyle='round,pad=0.2', fc='#1e1e2e', alpha=0.7))

        if far_px is not None:
            ax.text(min(far_m, MAX_DIST), y_text,
                    f'{far_px:.2f} px\n(far)',
                    color=info_color, fontsize=7.5, ha='center', va='top',
                    bbox=dict(boxstyle='round,pad=0.2', fc='#1e1e2e', alpha=0.7))

        # ── Axes and labels ──
        ax.set_xlim(0, MAX_DIST)
        ax.set_ylim(-0.55, 0.65)
        ax.set_xlabel('Distance from camera (m)', fontsize=10)
        ax.set_yticks([])
        ax.set_title(
            f'{camera_name.split("(")[0].strip()}  ·  {lens_name.split("(")[0].strip()}  ·  '
            f'F/{f_number:.1f}  ·  Focus: {focus_m:.3f} m\n'
            f'CoC: {coc_mm*1000:.1f} µm  ·  DoF: {near_m:.3f} m → '
            f'{"∞" if far_m==float("inf") else f"{far_m:.3f} m"}',
            fontsize=9, pad=8
        )

        ax.xaxis.set_major_locator(ticker.MultipleLocator(10))
        ax.xaxis.set_minor_locator(ticker.MultipleLocator(5))
        ax.grid(axis='x', which='major', color='#45475a', linewidth=0.6, alpha=0.5)
        ax.grid(axis='x', which='minor', color='#313244', linewidth=0.3, alpha=0.4)

        ax.legend(loc='upper right', fontsize=7.5,
                  facecolor='#1e1e2e', edgecolor='#45475a',
                  labelcolor='#cdd6f4', framealpha=0.9)

        self.fig.tight_layout(pad=2)
        self.draw()


# ─────────────────────────────────────────────────────────────────────────────
# MAIN WINDOW
# ─────────────────────────────────────────────────────────────────────────────

DARK_STYLE = """
QMainWindow, QWidget {
    background-color: #1e1e2e;
    color: #cdd6f4;
    font-family: 'Segoe UI', 'Ubuntu', sans-serif;
}
QGroupBox {
    border: 1px solid #45475a;
    border-radius: 6px;
    margin-top: 10px;
    font-weight: bold;
    font-size: 11px;
    color: #89b4fa;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 10px;
    padding: 0 4px;
}
QLabel { color: #cdd6f4; font-size: 11px; }
QComboBox {
    background-color: #313244;
    color: #cdd6f4;
    border: 1px solid #45475a;
    border-radius: 4px;
    padding: 4px 8px;
    min-height: 24px;
}
QComboBox::drop-down { border: none; }
QComboBox QAbstractItemView {
    background-color: #313244;
    color: #cdd6f4;
    selection-background-color: #45475a;
}
QDoubleSpinBox, QSpinBox {
    background-color: #313244;
    color: #cdd6f4;
    border: 1px solid #45475a;
    border-radius: 4px;
    padding: 3px 6px;
    min-height: 24px;
}
QSlider::groove:horizontal {
    height: 6px;
    background: #313244;
    border-radius: 3px;
}
QSlider::handle:horizontal {
    background: #89b4fa;
    width: 16px;
    height: 16px;
    margin: -5px 0;
    border-radius: 8px;
}
QSlider::sub-page:horizontal { background: #89b4fa; border-radius: 3px; }
QFrame[frameShape="4"] { color: #45475a; }
"""


class ResultLabel(QLabel):
    """Result label with highlighted formatting."""
    def __init__(self, text="—"):
        super().__init__(text)
        self.setFont(QFont("Consolas", 11, QFont.Bold))
        self.setStyleSheet("color: #a6e3a1; background: #313244; "
                           "border-radius: 4px; padding: 4px 8px;")
        self.setAlignment(Qt.AlignCenter)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Camera DoF Visualizer")
        self.setMinimumSize(1200, 720)
        self.setStyleSheet(DARK_STYLE)
        self._build_ui()
        self._connect_signals()
        self._update()

    # ── UI Construction ──────────────────────────────────────────────────

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QHBoxLayout(central)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(10)

        # Left panel (controls)
        left = QWidget()
        left.setFixedWidth(310)
        lv = QVBoxLayout(left)
        lv.setSpacing(8)

        # ── Camera ──
        grp_cam = QGroupBox("Camera")
        gc = QGridLayout(grp_cam)
        gc.setSpacing(6)
        self.cb_camera = QComboBox()
        self.cb_camera.addItems(CAMERAS.keys())
        self.lbl_cam_desc = QLabel()
        self.lbl_cam_desc.setWordWrap(True)
        self.lbl_cam_desc.setStyleSheet("color: #6c7086; font-size: 9px;")
        gc.addWidget(QLabel("Model:"), 0, 0)
        gc.addWidget(self.cb_camera, 0, 1)
        gc.addWidget(self.lbl_cam_desc, 1, 0, 1, 2)
        lv.addWidget(grp_cam)

        # ── Lens ──
        grp_lens = QGroupBox("Lens")
        gl = QGridLayout(grp_lens)
        gl.setSpacing(6)
        self.cb_lens = QComboBox()
        self.lbl_lens_desc = QLabel()
        self.lbl_lens_desc.setWordWrap(True)
        self.lbl_lens_desc.setStyleSheet("color: #6c7086; font-size: 9px;")

        self.lbl_fn = QLabel("Aperture F/:")
        self.sb_fn = QDoubleSpinBox()
        self.sb_fn.setRange(1.0, 22.0)
        self.sb_fn.setSingleStep(0.1)
        self.sb_fn.setValue(1.8)
        self.sb_fn.setDecimals(1)
        self.sl_fn = QSlider(Qt.Horizontal)
        self.sl_fn.setRange(10, 220)   # ×10
        self.sl_fn.setValue(18)

        # Focal length (varifocal)
        self.lbl_fl = QLabel("Focal length:")
        self.sb_fl = QDoubleSpinBox()
        self.sb_fl.setRange(2.8, 12.0)
        self.sb_fl.setSingleStep(0.1)
        self.sb_fl.setValue(2.8)
        self.sb_fl.setDecimals(1)
        self.sb_fl.setSuffix(" mm")
        self.sl_fl = QSlider(Qt.Horizontal)
        self.sl_fl.setRange(28, 120)   # ×10
        self.sl_fl.setValue(28)
        self.lbl_fov_info = QLabel()
        self.lbl_fov_info.setStyleSheet("color: #89dceb; font-size: 9px;")

        gl.addWidget(QLabel("Lens:"), 0, 0)
        gl.addWidget(self.cb_lens, 0, 1)
        gl.addWidget(self.lbl_lens_desc, 1, 0, 1, 2)
        gl.addWidget(self.lbl_fn, 2, 0)
        gl.addWidget(self.sb_fn, 2, 1)
        gl.addWidget(self.sl_fn, 3, 0, 1, 2)
        gl.addWidget(self.lbl_fl, 4, 0)
        gl.addWidget(self.sb_fl, 4, 1)
        gl.addWidget(self.sl_fl, 5, 0, 1, 2)
        gl.addWidget(self.lbl_fov_info, 6, 0, 1, 2)
        lv.addWidget(grp_lens)

        # ── Focus ──
        grp_focus = QGroupBox("Focus (focus distance)")
        gf = QGridLayout(grp_focus)
        gf.setSpacing(6)
        self.sb_focus = QDoubleSpinBox()
        self.sb_focus.setRange(0.0, 100.0)
        self.sb_focus.setSingleStep(0.01)
        self.sb_focus.setDecimals(3)
        self.sb_focus.setSuffix(" m")
        self.sb_focus.setValue(5.0)

        self.sl_focus = QSlider(Qt.Horizontal)
        self.sl_focus.setRange(1, 10000)   # 0.01 to 100 m (×100)
        self.sl_focus.setValue(500)

        self.lbl_focus_info = QLabel()
        self.lbl_focus_info.setStyleSheet("color: #fab387; font-size: 9px;")
        self.lbl_focus_info.setWordWrap(True)

        gf.addWidget(QLabel("Focus distance:"), 0, 0)
        gf.addWidget(self.sb_focus, 0, 1)
        gf.addWidget(self.sl_focus, 1, 0, 1, 2)
        gf.addWidget(self.lbl_focus_info, 2, 0, 1, 2)
        lv.addWidget(grp_focus)

        # ── Thread ──
        grp_thread = QGroupBox("Thread / Object to measure")
        gt = QGridLayout(grp_thread)
        gt.setSpacing(6)
        self.sb_thread = QDoubleSpinBox()
        self.sb_thread.setRange(0.1, 10.0)
        self.sb_thread.setSingleStep(0.1)
        self.sb_thread.setDecimals(2)
        self.sb_thread.setSuffix(" mm")
        self.sb_thread.setValue(1.0)
        gt.addWidget(QLabel("Thread diameter:"), 0, 0)
        gt.addWidget(self.sb_thread, 0, 1)
        lv.addWidget(grp_thread)

        # ── Results ──
        grp_res = QGroupBox("Results — Thread Pixels")
        gr = QGridLayout(grp_res)
        gr.setSpacing(6)

        gr.addWidget(QLabel("Px at focus point:"), 0, 0)
        self.lbl_px_focus = ResultLabel()
        gr.addWidget(self.lbl_px_focus, 0, 1)

        gr.addWidget(QLabel("Px at near limit:"), 1, 0)
        self.lbl_px_near = ResultLabel()
        gr.addWidget(self.lbl_px_near, 1, 1)

        gr.addWidget(QLabel("Px at far limit:"), 2, 0)
        self.lbl_px_far = ResultLabel()
        gr.addWidget(self.lbl_px_far, 2, 1)

        gr.addWidget(QLabel("Px at 100 m:"), 3, 0)
        self.lbl_px_100 = ResultLabel()
        gr.addWidget(self.lbl_px_100, 3, 1)

        gr.addWidget(QLabel("Total DoF:"), 4, 0)
        self.lbl_dof = ResultLabel()
        gr.addWidget(self.lbl_dof, 4, 1)

        gr.addWidget(QLabel("Hyperfocal dist.:"), 5, 0)
        self.lbl_hyp = ResultLabel()
        gr.addWidget(self.lbl_hyp, 5, 1)

        gr.addWidget(QLabel("CoC (1 px):"), 6, 0)
        self.lbl_coc = ResultLabel()
        gr.addWidget(self.lbl_coc, 6, 1)

        lv.addWidget(grp_res)
        lv.addStretch()

        # Canvas
        self.canvas = DoFCanvas()

        root.addWidget(left)
        root.addWidget(self.canvas, stretch=1)

        # Populate initial lens list
        self._update_lens_combo()

    # ── Signal connections ─────────────────────────────────────────────────

    def _connect_signals(self):
        self.cb_camera.currentIndexChanged.connect(self._on_camera_changed)
        self.cb_lens.currentIndexChanged.connect(self._on_lens_changed)

        self.sb_fn.valueChanged.connect(self._on_fn_spinbox)
        self.sl_fn.valueChanged.connect(self._on_fn_slider)

        self.sb_fl.valueChanged.connect(self._on_fl_spinbox)
        self.sl_fl.valueChanged.connect(self._on_fl_slider)

        self.sb_focus.valueChanged.connect(self._on_focus_spinbox)
        self.sl_focus.valueChanged.connect(self._on_focus_slider)

        self.sb_thread.valueChanged.connect(self._update)

    # ── Event handlers ─────────────────────────────────────────────────────

    def _on_camera_changed(self):
        self._update_lens_combo()
        self._update()

    def _on_lens_changed(self):
        self._update_fn_range()
        self._update_focus_range()
        self._update()

    def _on_fl_spinbox(self, val):
        self.sl_fl.blockSignals(True)
        self.sl_fl.setValue(int(val * 10))
        self.sl_fl.blockSignals(False)
        self._update_fov_label()
        self._update()

    def _on_fl_slider(self, val):
        self.sb_fl.blockSignals(True)
        self.sb_fl.setValue(val / 10.0)
        self.sb_fl.blockSignals(False)
        self._update_fov_label()
        self._update()

    def _update_fov_label(self):
        lens_name = self.cb_lens.currentText()
        if not lens_name:
            return
        lens = LENSES[lens_name]
        if not lens.get("adjustable_focal"):
            self.lbl_fov_info.setText("")
            return
        fl  = self.sb_fl.value()
        fl_min = lens["focal_length_min_mm"]
        fl_max = lens["focal_length_max_mm"]
        fov_w  = lens["fov_h_deg"]        # @ wide
        fov_t  = lens["fov_h_tele_deg"]   # @ tele
        # Linear FOV interpolation
        t = (fl - fl_min) / (fl_max - fl_min)
        fov = fov_w + t * (fov_t - fov_w)
        self.lbl_fov_info.setText(f"Estimated FOV: {fov:.1f}° H  (wide ← → tele)")

    def _on_fn_spinbox(self, val):
        self.sl_fn.blockSignals(True)
        self.sl_fn.setValue(int(val * 10))
        self.sl_fn.blockSignals(False)
        self._update()

    def _on_fn_slider(self, val):
        self.sb_fn.blockSignals(True)
        self.sb_fn.setValue(val / 10.0)
        self.sb_fn.blockSignals(False)
        self._update()

    def _on_focus_spinbox(self, val):
        self.sl_focus.blockSignals(True)
        self.sl_focus.setValue(int(val * 100))
        self.sl_focus.blockSignals(False)
        self._update()

    def _on_focus_slider(self, val):
        self.sb_focus.blockSignals(True)
        self.sb_focus.setValue(val / 100.0)
        self.sb_focus.blockSignals(False)
        self._update()

    # ── UI helpers ─────────────────────────────────────────────────────────

    def _update_lens_combo(self):
        cam_name = self.cb_camera.currentText()
        cam = CAMERAS[cam_name]
        self.cb_lens.blockSignals(True)
        self.cb_lens.clear()
        self.cb_lens.addItems(cam["lenses"])
        self.cb_lens.blockSignals(False)
        self.lbl_cam_desc.setText(cam["description"])
        self._update_fn_range()
        self._update_focus_range()

    def _update_fn_range(self):
        lens_name = self.cb_lens.currentText()
        if not lens_name:
            return
        lens = LENSES[lens_name]
        self.lbl_lens_desc.setText(lens["description"])
        fn_min = lens["f_number_min"]
        fn_max = lens["f_number_max"]
        self.sb_fn.setRange(fn_min, fn_max)
        self.sl_fn.setRange(int(fn_min * 10), int(fn_max * 10))
        enabled = lens["adjustable_f"]
        self.sb_fn.setEnabled(enabled)
        self.sl_fn.setEnabled(enabled)
        self.sb_fn.setValue(fn_min)

        # Varifocal focal length controls
        is_varifocal = lens.get("adjustable_focal", False)
        self.lbl_fl.setVisible(is_varifocal)
        self.sb_fl.setVisible(is_varifocal)
        self.sl_fl.setVisible(is_varifocal)
        self.lbl_fov_info.setVisible(is_varifocal)
        if is_varifocal:
            fl_min = lens["focal_length_min_mm"]
            fl_max = lens["focal_length_max_mm"]
            self.sb_fl.setRange(fl_min, fl_max)
            self.sl_fl.setRange(int(fl_min * 10), int(fl_max * 10))
            self.sb_fl.setValue(fl_min)
            self._update_fov_label()

    def _update_focus_range(self):
        lens_name = self.cb_lens.currentText()
        if not lens_name:
            return
        lens = LENSES[lens_name]
        mod_m = lens["mod_mm"] / 1000.0
        self.sb_focus.setMinimum(mod_m)
        self.sl_focus.setMinimum(int(mod_m * 100))
        if self.sb_focus.value() < mod_m:
            self.sb_focus.setValue(mod_m)
        self.lbl_focus_info.setText(
            f"MOD (minimum focus distance): {mod_m:.3f} m"
        )

    # ── Calculation and rendering ────────────────────────────────────────────

    def _update(self):
        cam_name  = self.cb_camera.currentText()
        lens_name = self.cb_lens.currentText()
        if not cam_name or not lens_name:
            return

        cam  = CAMERAS[cam_name]
        lens = LENSES[lens_name]

        sw   = cam["sensor_width_mm"]
        rh   = cam["resolution_h"]
        # Use varifocal slider value if applicable
        if lens.get("adjustable_focal", False):
            f_mm = self.sb_fl.value()
        else:
            f_mm = lens["focal_length_mm"]
        fn   = self.sb_fn.value()
        fd_m = self.sb_focus.value()
        th   = self.sb_thread.value()   # mm

        coc  = circle_of_confusion(sw, rh)                  # mm
        near, far, dof, hyp = depth_of_field(f_mm, fn, coc, fd_m)

        # Thread pixels at different points
        px_focus = thread_pixels(sw, rh, f_mm, fd_m, th)
        px_near  = thread_pixels(sw, rh, f_mm, max(near, lens["mod_mm"]/1000), th)
        px_far   = thread_pixels(sw, rh, f_mm, min(far, 100.0), th) if far != float('inf') else None
        px_100   = thread_pixels(sw, rh, f_mm, 100.0, th)

        # ── Update labels ──
        def fmt_px(v):
            return f"{v:.3f} px" if v is not None else "—"

        self.lbl_px_focus.setText(fmt_px(px_focus))
        self.lbl_px_near.setText(fmt_px(px_near))
        self.lbl_px_far.setText(fmt_px(px_far) if far != float('inf') else "∞ (hyperfocal)")
        self.lbl_px_100.setText(fmt_px(px_100))

        if dof == float('inf'):
            self.lbl_dof.setText("∞ (hyperfocal)")
        else:
            self.lbl_dof.setText(f"{dof:.4f} m")

        self.lbl_hyp.setText(f"{hyp:.2f} m")
        self.lbl_coc.setText(f"{coc*1000:.2f} µm")

        # ── Plot ──
        self.canvas.plot(
            near_m=near,
            far_m=far,
            focus_m=fd_m,
            hyperfocal_m=hyp,
            camera_name=cam_name,
            lens_name=lens_name,
            f_number=fn,
            near_px=px_near,
            far_px=px_far,
            thread_mm=th,
            coc_mm=coc,
            focus_distance_m=fd_m,
        )


# ─────────────────────────────────────────────────────────────────────────────

def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    win = MainWindow()
    win.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()