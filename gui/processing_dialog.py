#!/usr/bin/env python3
"""
Página de procesamiento 3D integrada en la ventana única.
Reemplaza ProcessingDialog (QDialog) por ProcessingPage (QWidget).

WireTrackingVisualizationDialog permanece como QDialog (visualización
breve y modal durante el tracking — no necesita ser una página persistente).
"""

import cv2
import numpy as np
from datetime import datetime
from pathlib import Path

from PyQt5.QtWidgets import (
    QDialog, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QProgressBar, QTextEdit, QGroupBox,
    QGridLayout, QMessageBox, QCheckBox,
    QFrame, QApplication, QComboBox,
    QFileDialog, QTabWidget, QScrollArea,
    QListWidget, QListWidgetItem, QSplitter,
)
from PyQt5.QtCore import QThread, pyqtSignal, QTimer, Qt
from PyQt5.QtGui import QPixmap, QImage, QFont

from processing.stereo_processor import StereoProcessor
from processing.point_cloud_generator import PointCloudExporter
from utils.logger import get_logger

logger = get_logger(__name__)

# ── Color palette ─────────────────────────────────────────────────────────────
BG_DEEP        = "#0F172A"
BG_PANEL       = "#1E293B"
BG_CARD        = "#273548"
BG_SIDEBAR     = "#0B1120"
ACCENT_CYAN    = "#22D3EE"
ACCENT_BLUE    = "#3B82F6"
ACCENT_ORANGE  = "#F59E0B"
TEXT_PRIMARY   = "#E2E8F0"
TEXT_SECONDARY = "#94A3B8"
TEXT_DIM       = "#64748B"
BORDER_SUBTLE  = "#334155"
GREEN_ON       = "#22C55E"
RED_OFF        = "#EF4444"
YELLOW_WARN    = "#EAB308"


# ── Worker threads (logic unchanged) ─────────────────────────────────────────

class ProcessingWorkerThread(QThread):
    """Hilo para ejecutar procesamiento 3D sin bloquear UI."""
    progress_update    = pyqtSignal(int, str)
    processing_complete = pyqtSignal(bool, dict)
    log_message        = pyqtSignal(str, str)
    intermediate_result = pyqtSignal(str, object)

    def __init__(self, camera_config, processing_params,
                 cable_masks=None, wire_paths=None):
        super().__init__()
        self.camera_config    = camera_config
        self.processing_params = processing_params
        self.cable_masks      = cable_masks
        self.wire_paths       = wire_paths
        self.should_stop      = False

    def run(self):
        try:
            self.log_message.emit("Starting 3D processing...", "INFO")
            processor = StereoProcessor(self.camera_config)

            self.progress_update.emit(5, "Loading images...")
            left_img  = cv2.imread(self.processing_params['left_image'])
            right_img = cv2.imread(self.processing_params['right_image'])
            if left_img is None or right_img is None:
                raise RuntimeError("Could not load images")
            self.log_message.emit(f"Images loaded: {left_img.shape}", "INFO")

            if self.wire_paths is not None:
                # ── Geometric path method ───────────────────────────────────
                self.log_message.emit("Using PRE-CALCULATED GEOMETRIC PATHS", "INFO")
                self.log_message.emit(
                    f"   Left path: {len(self.wire_paths['left'])} points", "INFO"
                )
                self.log_message.emit(
                    f"   Right path: {len(self.wire_paths['right'])} points", "INFO"
                )

                self.progress_update.emit(10, "Rectifying images...")
                left_rect, right_rect = processor.rectify_images(left_img, right_img)

                self.progress_update.emit(30, "Calculating disparity from geometric paths...")
                image_shape = left_rect.shape[:2]
                disparity_result = processor.compute_disparity_from_wire_paths(
                    self.wire_paths['left'], self.wire_paths['right'],
                    image_shape, save_debug=True,
                )
                if not disparity_result['success']:
                    raise RuntimeError(
                        "Could not calculate disparity from geometric paths"
                    )

                self.progress_update.emit(70, "Generating 3D point cloud from matches...")
                point_cloud_result = processor.generate_point_cloud_from_matches(
                    disparity_result['matches'],
                    disparity_result['disparities'],
                    left_rect,
                )
                self.log_message.emit(
                    f"Cloud generated: {point_cloud_result['num_points']} 3D points",
                    "INFO",
                )

                depth_result = processor.disparity_to_depth(
                    disparity_result['disparity_map']
                )

                wire_metrics_summary = None
                try:
                    from processing.wire_metrics import compute_wire_metrics
                    wm = compute_wire_metrics(
                        matches          = disparity_result.get('matches', []),
                        disparities      = disparity_result.get('disparities', []),
                        calibration_data = processor.calibration_data,
                        dt_profile_left  = self.wire_paths.get('dt_profile_left'),
                    )
                    if wm is not None:
                        wire_metrics_summary = wm.summary()
                        m = wire_metrics_summary
                        self.log_message.emit(
                            f"Cable: {m['total_length_m']*100:.1f} cm | "
                            f"straightness={m['straightness']:.3f} | "
                            f"depth={m['min_depth_m']*100:.1f}–{m['max_depth_m']*100:.1f} cm",
                            "INFO",
                        )
                except Exception as _e:
                    self.log_message.emit(f"Wire metrics skipped: {_e}", "WARNING")

                result = {
                    'success': True,
                    'algorithm': 'GEOMETRIC_PATH',
                    'disparity': disparity_result,
                    'depth': depth_result,
                    'point_cloud': point_cloud_result,
                    'wire_metrics': wire_metrics_summary,
                }

            elif self.cable_masks is not None:
                # ── SGBM with mask ──────────────────────────────────────────
                mask_left, _ = self.cable_masks
                self.log_message.emit("No geometric paths, using SGBM + mask", "WARNING")
                result = processor.process_stereo_pair(
                    left_img, right_img,
                    algorithm=self.processing_params['algorithm'],
                    progress_callback=self._progress_callback,
                    save_debug_images=True,
                    cable_mask=mask_left,
                )
            else:
                # ── Traditional SGBM ────────────────────────────────────────
                self.log_message.emit(
                    "No cable mask — using traditional SGBM", "WARNING"
                )
                result = processor.process_stereo_pair(
                    left_img, right_img,
                    algorithm=self.processing_params['algorithm'],
                    progress_callback=self._progress_callback,
                    save_debug_images=True,
                    cable_mask=None,
                )

            if not result['success']:
                raise RuntimeError(f"Processing error: {result.get('error')}")

            self.intermediate_result.emit("disparity", result['disparity']['disparity_map'])
            self.intermediate_result.emit("depth",     result['depth']['depth_map'])
            self.intermediate_result.emit("confidence", result['disparity']['confidence_map'])

            if self.processing_params.get('export_point_cloud', True):
                self.progress_update.emit(90, "Exporting point cloud...")
                exporter = PointCloudExporter()
                export_results = []
                for fmt in self.processing_params.get('export_formats', ['ply']):
                    out = self.processing_params['output_dir'] / f"point_cloud.{fmt}"
                    exp = exporter.export_point_cloud(
                        result['point_cloud']['points'],
                        result['point_cloud']['colors'],
                        str(out), fmt,
                    )
                    if exp['success']:
                        export_results.append(str(out))
                        self.log_message.emit(f"Cloud exported: {out}", "INFO")
                result['export_files'] = export_results

            self.progress_update.emit(100, "Processing completed")
            self.processing_complete.emit(True, result)

        except Exception as e:
            self.log_message.emit(f"Error during processing: {e}", "ERROR")
            self.processing_complete.emit(False, {'error': str(e)})

    def _progress_callback(self, progress, message):
        if not self.should_stop:
            adjusted = 10 + int(progress * 0.75)
            self.progress_update.emit(adjusted, message)

    def stop(self):
        self.should_stop = True


# ── Results visualization widget ──────────────────────────────────────────────

class ResultsVisualizationWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        self.tabs = QTabWidget()
        layout.addWidget(self.tabs)

        self.disparity_tab  = self._make_image_tab("Disparity Map")
        self.depth_tab      = self._make_image_tab("Depth Map")
        self.confidence_tab = self._make_image_tab("Confidence Map")
        self.stats_tab      = self._make_stats_tab()

        self.tabs.addTab(self.disparity_tab,  "Disparity")
        self.tabs.addTab(self.depth_tab,      "Depth")
        self.tabs.addTab(self.confidence_tab, "Confidence")
        self.tabs.addTab(self.stats_tab,      "Statistics")

    def _make_image_tab(self, title):
        widget = QWidget()
        v = QVBoxLayout(widget)

        title_lbl = QLabel(title)
        title_lbl.setFont(QFont("Segoe UI", 12, QFont.Bold))
        title_lbl.setAlignment(Qt.AlignCenter)
        title_lbl.setStyleSheet(f"color: {ACCENT_CYAN}; background: transparent;")
        v.addWidget(title_lbl)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setAlignment(Qt.AlignCenter)

        img_label = QLabel("No data")
        img_label.setAlignment(Qt.AlignCenter)
        img_label.setMinimumSize(400, 300)
        img_label.setStyleSheet(
            f"QLabel {{ border: 2px dashed {BORDER_SUBTLE};"
            f"background-color: {BG_CARD}; color: {TEXT_DIM}; }}"
        )
        scroll.setWidget(img_label)
        v.addWidget(scroll)
        widget.image_label = img_label
        return widget

    def _make_stats_tab(self):
        widget = QWidget()
        v = QVBoxLayout(widget)
        title = QLabel("Processing Statistics")
        title.setFont(QFont("Segoe UI", 12, QFont.Bold))
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet(f"color: {ACCENT_CYAN}; background: transparent;")
        v.addWidget(title)
        self.stats_text = QTextEdit()
        self.stats_text.setReadOnly(True)
        v.addWidget(self.stats_text)
        return widget

    # ── Update methods (logic unchanged) ─────────────────────────────────────

    def update_disparity(self, disparity_map):
        try:
            vis = cv2.normalize(disparity_map, None, 0, 255, cv2.NORM_MINMAX).astype(np.uint8)
            vis = cv2.applyColorMap(vis, cv2.COLORMAP_JET)
            h, w, ch = vis.shape
            q_img = QImage(vis.data, w, h, 3 * w, QImage.Format_RGB888).rgbSwapped()
            px = QPixmap.fromImage(q_img)
            if px.width() > 800 or px.height() > 600:
                px = px.scaled(800, 600, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            self.disparity_tab.image_label.setPixmap(px)
        except Exception as e:
            logger.error(f"Error updating disparity view: {e}")

    def update_depth(self, depth_map):
        try:
            dv = depth_map.copy()
            dv[dv == 0] = np.nan
            valid = ~np.isnan(dv)
            if np.any(valid):
                d_min, d_max = np.nanmin(dv), np.nanmax(dv)
                norm = ((dv - d_min) / (d_max - d_min))
                norm = np.nan_to_num(norm, 0) * 255
                norm = norm.astype(np.uint8)
                colored = cv2.applyColorMap(255 - norm, cv2.COLORMAP_HOT)
                colored[~valid] = [0, 0, 0]
                h, w, ch = colored.shape
                q_img = QImage(colored.data, w, h, 3 * w, QImage.Format_RGB888).rgbSwapped()
                px = QPixmap.fromImage(q_img)
                if px.width() > 800 or px.height() > 600:
                    px = px.scaled(800, 600, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                self.depth_tab.image_label.setPixmap(px)
            else:
                self.depth_tab.image_label.setText("No valid depth data")
        except Exception as e:
            logger.error(f"Error updating depth view: {e}")

    def update_confidence(self, confidence_map):
        try:
            vis = (confidence_map * 255).astype(np.uint8)
            vis = cv2.applyColorMap(vis, cv2.COLORMAP_VIRIDIS)
            h, w, ch = vis.shape
            q_img = QImage(vis.data, w, h, 3 * w, QImage.Format_RGB888).rgbSwapped()
            px = QPixmap.fromImage(q_img)
            if px.width() > 800 or px.height() > 600:
                px = px.scaled(800, 600, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            self.confidence_tab.image_label.setPixmap(px)
        except Exception as e:
            logger.error(f"Error updating confidence view: {e}")

    def update_statistics(self, result):
        try:
            t  = "=== 3D PROCESSING STATISTICS ===\n\n"
            t += f"Processing time: {result.get('processing_time_seconds', 0):.2f} s\n"
            t += f"Algorithm: {result.get('algorithm_used', 'N/A')}\n"
            t += f"Input shape: {result.get('input_shape', 'N/A')}\n\n"

            if 'disparity' in result:
                d = result['disparity']
                t += "--- DISPARITY ---\n"
                t += f"Min: {d.get('min_disparity', 0):.2f} px\n"
                t += f"Max: {d.get('max_disparity', 0):.2f} px\n"
                t += f"Mean: {d.get('mean_disparity', 0):.2f} px\n"
                t += f"Valid pixels: {d.get('valid_pixels', 0):,}\n\n"

            if 'depth' in result:
                dp = result['depth']
                t += "--- DEPTH ---\n"
                t += f"Min: {dp.get('min_depth', 0):.3f} m\n"
                t += f"Max: {dp.get('max_depth', 0):.3f} m\n"
                t += f"Mean: {dp.get('mean_depth', 0):.3f} m\n"
                t += f"Baseline: {dp.get('baseline_meters', 0)*1000:.1f} mm\n\n"

            if 'point_cloud' in result:
                pc = result['point_cloud']
                t += "--- POINT CLOUD ---\n"
                t += f"Points: {pc.get('num_points', 0):,}\n"
                t += f"Density: {pc.get('density', 0):.4f}\n"
                b = pc.get('bounds', {})
                t += f"X: {b.get('x_min',0):.3f} – {b.get('x_max',0):.3f} m\n"
                t += f"Y: {b.get('y_min',0):.3f} – {b.get('y_max',0):.3f} m\n"
                t += f"Z: {b.get('z_min',0):.3f} – {b.get('z_max',0):.3f} m\n\n"

            if result.get('wire_metrics') is not None:
                wm = result['wire_metrics']
                start = wm.get('start_3d_m', [0, 0, 0])
                end   = wm.get('end_3d_m',   [0, 0, 0])
                t += "--- WIRE METRICS ---\n"
                t += f"3D length:      {wm.get('total_length_m',0)*100:.1f} cm\n"
                t += f"Straightness:   {wm.get('straightness',0):.3f}\n"
                t += f"Depth range:    {wm.get('min_depth_m',0)*100:.1f} – {wm.get('max_depth_m',0)*100:.1f} cm\n"
                t += f"Mean depth:     {wm.get('mean_depth_m',0)*100:.1f} cm\n"
                if wm.get('mean_diameter_mm', 0) > 0:
                    t += f"Est. diameter:  {wm.get('mean_diameter_mm',0):.2f} mm\n"
                t += f"Curvature p95:  {wm.get('p95_curvature_rad_m',0):.3f} rad/m\n"
                t += f"Start 3D: ({start[0]*100:.1f}, {start[1]*100:.1f}, {start[2]*100:.1f}) cm\n"
                t += f"End 3D:   ({end[0]*100:.1f}, {end[1]*100:.1f}, {end[2]*100:.1f}) cm\n\n"

            if 'export_files' in result:
                t += "--- EXPORTED FILES ---\n"
                for f in result['export_files']:
                    size_mb = Path(f).stat().st_size / (1024 * 1024)
                    t += f"• {Path(f).name} ({size_mb:.1f} MB)\n"

            self.stats_text.setText(t)
        except Exception as e:
            logger.error(f"Error updating statistics: {e}")
            self.stats_text.setText(f"Error loading statistics: {e}")


# ── Wire tracking (stays as modal QDialog) ────────────────────────────────────

class WireTrackingWorkerThread(QThread):
    path_updated     = pyqtSignal(list, int)
    tracking_finished = pyqtSignal(dict)

    def __init__(self, mask, start_pt, end_pt):
        super().__init__()
        self.mask     = mask
        self.start_pt = start_pt
        self.end_pt   = end_pt

    def run(self):
        from processing.smart_wire_tracker import SmartWireTracker
        h, w = self.mask.shape[:2]
        resolution_scale = max(1.0, (h * w) / (1920 * 1440))
        max_iter = int(10000 * min(resolution_scale, 10))
        tracker = SmartWireTracker(self.mask, self.start_pt, self.end_pt)
        result = tracker.track_wire(
            max_iterations=max_iter,
            step_callback=self._on_step,
        )
        self.tracking_finished.emit(result)

    def _on_step(self, path, iteration):
        self.path_updated.emit(path, iteration)


class WireTrackingVisualizationDialog(QDialog):
    """Modal breve que muestra en tiempo real la reconstrucción del cable."""

    def __init__(self, left_img, right_img, mask_left, mask_right,
                 start_left, end_left, start_right, end_right, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Wire Tracking — Live Reconstruction")
        self.setModal(True)

        self.left_img   = left_img.copy()
        self.right_img  = right_img.copy()
        self.mask_left  = mask_left
        self.mask_right = mask_right
        self.start_left  = start_left
        self.end_left    = end_left
        self.start_right = start_right
        self.end_right   = end_right

        self.current_path_left  = []
        self.current_path_right = []
        self.result_left  = None
        self.result_right = None
        self.phase = "idle"

        screen = QApplication.primaryScreen()
        if screen:
            g = screen.availableGeometry()
            self.resize(min(1100, g.width() - 40), min(550, g.height() - 60))
        else:
            self.resize(1100, 550)

        self._build_ui()
        QTimer.singleShot(300, self._start_left_tracking)

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(4)
        layout.setContentsMargins(6, 6, 6, 6)

        self.status_label = QLabel("Preparing...")
        self.status_label.setFont(QFont("Segoe UI", 11, QFont.Bold))
        self.status_label.setAlignment(Qt.AlignCenter)
        self.status_label.setStyleSheet(
            f"color: {ACCENT_BLUE}; background: transparent; margin: 2px;"
        )
        layout.addWidget(self.status_label)

        images_layout = QHBoxLayout()

        for side, attr_header, attr_img in [
            ("Left",  "left_header",  "left_image_label"),
            ("Right", "right_header", "right_image_label"),
        ]:
            frame = QFrame()
            fl = QVBoxLayout(frame)
            fl.setContentsMargins(2, 2, 2, 2)
            header = QLabel(f"{side} — initializing")
            header.setFont(QFont("Segoe UI", 9, QFont.Bold))
            header.setAlignment(Qt.AlignCenter)
            header.setStyleSheet(
                f"color: {ACCENT_BLUE if side == 'Left' else ACCENT_ORANGE};"
                f"background: transparent;"
            )
            fl.addWidget(header)
            img_lbl = QLabel()
            img_lbl.setAlignment(Qt.AlignCenter)
            init_img = self._draw_wire(
                self.left_img if side == "Left" else self.right_img,
                [], side.upper()
            )
            img_lbl.setPixmap(self._cv2_to_pixmap(init_img))
            fl.addWidget(img_lbl)
            images_layout.addWidget(frame)
            setattr(self, attr_header, header)
            setattr(self, attr_img,    img_lbl)

        layout.addLayout(images_layout)

        self.btn_close = QPushButton("Processing...")
        self.btn_close.setFixedHeight(30)
        self.btn_close.setEnabled(False)
        self.btn_close.clicked.connect(self.accept)
        self.btn_close.setStyleSheet(
            f"QPushButton {{ background-color: {ACCENT_BLUE}; color: white;"
            f"font-weight: bold; border-radius: 4px; }}"
            f"QPushButton:disabled {{ background-color: {BG_CARD}; color: {TEXT_DIM}; }}"
        )
        layout.addWidget(self.btn_close)

    def _start_left_tracking(self):
        self.phase = "left"
        self.status_label.setText("Processing left image...")
        self.left_header.setText("Left — processing...")
        self.worker = WireTrackingWorkerThread(
            self.mask_left, self.start_left, self.end_left
        )
        self.worker.path_updated.connect(self._on_left_update)
        self.worker.tracking_finished.connect(self._on_left_done)
        self.worker.start()

    def _on_left_update(self, path, iteration):
        self.current_path_left = path
        vis = self._draw_wire(self.left_img, path, "LEFT")
        self.left_image_label.setPixmap(self._cv2_to_pixmap(vis))
        self.left_header.setText(f"Left — {len(path)} pts (iter {iteration})")

    def _on_left_done(self, result):
        self.result_left = result
        self.current_path_left = result['path']
        vis = self._draw_wire(self.left_img, result['path'], "LEFT")
        self.left_image_label.setPixmap(self._cv2_to_pixmap(vis))
        self.left_header.setText(
            f"Left — {len(result['path'])} pts | Cov: {result['coverage']*100:.1f}%"
        )
        QTimer.singleShot(500, self._start_right_tracking)

    def _start_right_tracking(self):
        self.phase = "right"
        self.status_label.setText("Processing right image...")
        self.right_header.setText("Right — processing...")
        self.worker = WireTrackingWorkerThread(
            self.mask_right, self.start_right, self.end_right
        )
        self.worker.path_updated.connect(self._on_right_update)
        self.worker.tracking_finished.connect(self._on_right_done)
        self.worker.start()

    def _on_right_update(self, path, iteration):
        self.current_path_right = path
        vis = self._draw_wire(self.right_img, path, "RIGHT")
        self.right_image_label.setPixmap(self._cv2_to_pixmap(vis))
        self.right_header.setText(f"Right — {len(path)} pts (iter {iteration})")

    def _on_right_done(self, result):
        self.result_right = result
        self.current_path_right = result['path']
        vis = self._draw_wire(self.right_img, result['path'], "RIGHT")
        self.right_image_label.setPixmap(self._cv2_to_pixmap(vis))
        self.right_header.setText(
            f"Right — {len(result['path'])} pts | Cov: {result['coverage']*100:.1f}%"
        )
        self.phase = "done"
        self.status_label.setText("Reconstruction completed")
        self.status_label.setStyleSheet(
            f"color: {GREEN_ON}; font-weight: bold; background: transparent;"
        )
        self.btn_close.setText("Close")
        self.btn_close.setEnabled(True)

    def get_results(self):
        if self.result_left and self.result_right:
            return {
                'success': self.result_left['success'] and self.result_right['success'],
                'left':  self.result_left,
                'right': self.result_right,
            }
        return None

    def _draw_wire(self, img, path, side):
        vis = img.copy()
        det_start = self.start_left if side == "LEFT" else self.start_right
        det_end   = self.end_left   if side == "LEFT" else self.end_right
        h, w = vis.shape[:2]
        r  = max(6, min(w, h) // 150)
        ft = max(0.5, min(w, h) / 2000.0)
        th = max(1, r // 3)
        cv2.circle(vis, (int(det_start[0]), int(det_start[1])), r, (0, 255, 0), -1)
        cv2.circle(vis, (int(det_end[0]),   int(det_end[1])),   r, (0, 0, 255), -1)
        cv2.putText(vis, "START",
                    (int(det_start[0]) + r + 2, int(det_start[1]) + r),
                    cv2.FONT_HERSHEY_SIMPLEX, ft, (0, 255, 0), th)
        cv2.putText(vis, "END",
                    (int(det_end[0]) + r + 2, int(det_end[1]) + r),
                    cv2.FONT_HERSHEY_SIMPLEX, ft, (0, 0, 255), th)
        if len(path) >= 2:
            color = (0, 200, 255) if side == "LEFT" else (0, 165, 255)
            lt = max(1, r // 3)
            for i in range(len(path) - 1):
                cv2.line(vis,
                         (int(path[i][0]),   int(path[i][1])),
                         (int(path[i+1][0]), int(path[i+1][1])),
                         color, lt, cv2.LINE_AA)
        return vis

    def _cv2_to_pixmap(self, cv_img):
        if len(cv_img.shape) == 2:
            cv_img = cv2.cvtColor(cv_img, cv2.COLOR_GRAY2BGR)
        rgb = cv2.cvtColor(cv_img, cv2.COLOR_BGR2RGB)
        h, w, ch = rgb.shape
        q_img = QImage(rgb.data, w, h, ch * w, QImage.Format_RGB888)
        px = QPixmap.fromImage(q_img.copy())
        if px.width() > 520 or px.height() > 400:
            px = px.scaled(520, 400, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        return px


# ── Processing page ───────────────────────────────────────────────────────────

class ProcessingPage(QWidget):
    """Página inline de procesamiento 3D."""

    def __init__(self, camera_config, parent=None):
        super().__init__(parent)
        self.camera_config      = camera_config
        self.processing_thread  = None
        self.last_capture_info  = None

        self.selected_left_path  = None
        self.selected_right_path = None
        self.current_session_path = None

        self.cable_filter_configured  = False
        self.cable_mask_left          = None
        self.cable_mask_right         = None
        self.cable_mask_left_rectified  = None
        self.cable_mask_right_rectified = None
        self.wire_tracking_result     = None

        self._init_ui()
        self._load_last_capture()

    # ── UI construction ───────────────────────────────────────────────────────

    def _init_ui(self):
        self.setStyleSheet(f"background-color: {BG_DEEP};")
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Back bar
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

        page_title = QLabel("◈  3D Processing — Model Generation")
        page_title.setStyleSheet(
            f"color: {TEXT_PRIMARY}; font-weight: bold; font-size: 15px;"
            f"background: transparent;"
        )
        bb.addWidget(page_title)
        bb.addStretch()
        root.addWidget(back_bar)

        # Main content: left config | right results
        splitter = QSplitter(Qt.Horizontal)
        splitter.setStyleSheet(f"background-color: {BG_DEEP};")

        config_panel = self._build_config_panel()
        splitter.addWidget(config_panel)

        self.results_widget = ResultsVisualizationWidget()
        splitter.addWidget(self.results_widget)

        splitter.setSizes([360, 640])
        root.addWidget(splitter, 1)

        # Bottom action bar
        action_bar = QFrame()
        action_bar.setFixedHeight(52)
        action_bar.setStyleSheet(
            f"QFrame {{ background-color: {BG_SIDEBAR};"
            f"border-top: 1px solid {BORDER_SUBTLE}; }}"
        )
        ab = QHBoxLayout(action_bar)
        ab.setContentsMargins(12, 0, 12, 0)
        ab.setSpacing(8)

        self.btn_start = QPushButton("▶  Start Processing")
        self.btn_start.setFixedHeight(36)
        self.btn_start.setStyleSheet(
            f"QPushButton {{ background-color: {ACCENT_BLUE}; color: white;"
            f"font-weight: bold; font-size: 14px; border-radius: 6px; }}"
            f"QPushButton:hover {{ background-color: #60A5FA; }}"
            f"QPushButton:disabled {{ background-color: {BG_CARD}; color: {TEXT_DIM}; }}"
        )
        self.btn_start.clicked.connect(self.start_processing)
        ab.addWidget(self.btn_start)

        self.btn_cancel = QPushButton("⏹  Cancel")
        self.btn_cancel.setFixedHeight(36)
        self.btn_cancel.setStyleSheet(
            f"QPushButton {{ background-color: {BG_CARD}; color: {TEXT_PRIMARY};"
            f"border-radius: 6px; }}"
            f"QPushButton:hover {{ background-color: {RED_OFF}; color: white; }}"
        )
        self.btn_cancel.clicked.connect(self.cancel_processing)
        self.btn_cancel.setEnabled(False)
        ab.addWidget(self.btn_cancel)

        ab.addStretch()
        root.addWidget(action_bar)

    def _build_config_panel(self):
        panel = QFrame()
        panel.setMaximumWidth(390)
        panel.setStyleSheet(
            f"QFrame {{ background-color: {BG_PANEL}; border-right: 1px solid {BORDER_SUBTLE}; }}"
        )
        v = QVBoxLayout(panel)
        v.setContentsMargins(10, 10, 10, 10)
        v.setSpacing(6)

        v.addWidget(self._build_images_group())
        v.addWidget(self._build_algorithm_group())
        v.addWidget(self._build_export_group())
        v.addWidget(self._build_progress_group())
        v.addWidget(self._build_log_group())
        v.addStretch()
        return panel

    def _build_images_group(self):
        group = QGroupBox("Image Selection")
        v = QVBoxLayout(group)

        self.capture_info_label = QLabel("Loading information...")
        self.capture_info_label.setWordWrap(True)
        self.capture_info_label.setStyleSheet(
            f"background-color: {BG_CARD}; color: {TEXT_SECONDARY};"
            f"padding: 8px; border-radius: 4px; font-size: 12px;"
        )
        v.addWidget(self.capture_info_label)

        self.btn_select_session = QPushButton("📁  Select Capture Session")
        self.btn_select_session.setStyleSheet(
            f"QPushButton {{ background-color: {ACCENT_BLUE}; color: white;"
            f"font-weight: bold; padding: 8px; border-radius: 5px; }}"
            f"QPushButton:hover {{ background-color: #60A5FA; }}"
        )
        self.btn_select_session.clicked.connect(self.select_capture_session)
        v.addWidget(self.btn_select_session)

        sep = QLabel("──────────────────────────────")
        sep.setAlignment(Qt.AlignCenter)
        sep.setStyleSheet(f"color: {BORDER_SUBTLE}; font-size: 9px; background: transparent;")
        v.addWidget(sep)

        self.btn_configure_cable = QPushButton("🔧  Configure Cable Filter")
        self.btn_configure_cable.setStyleSheet(
            f"QPushButton {{ background-color: {ACCENT_ORANGE}; color: white;"
            f"font-weight: bold; padding: 8px; border-radius: 5px; }}"
            f"QPushButton:hover {{ background-color: #D97706; }}"
            f"QPushButton:disabled {{ background-color: {BG_CARD}; color: {TEXT_DIM}; }}"
        )
        self.btn_configure_cable.clicked.connect(self.open_cable_filter_config)
        self.btn_configure_cable.setEnabled(False)
        v.addWidget(self.btn_configure_cable)

        self.filter_status_label = QLabel("⚠  Filter not configured")
        self.filter_status_label.setStyleSheet(
            f"background-color: {BG_CARD}; color: {YELLOW_WARN};"
            f"padding: 6px; border-radius: 3px; font-size: 11px;"
        )
        v.addWidget(self.filter_status_label)

        return group

    def _build_algorithm_group(self):
        group = QGroupBox("Algorithm Configuration")
        grid = QGridLayout(group)
        grid.setSpacing(6)

        grid.addWidget(QLabel("Processing mode:"), 0, 0)
        self.processing_mode_combo = QComboBox()
        self.processing_mode_combo.addItems([
            "Geometric (Wire Tracking)",
            "Dense SGBM (Traditional)",
        ])
        grid.addWidget(self.processing_mode_combo, 0, 1)

        self.label_algorithm = QLabel("Matching algorithm:")
        grid.addWidget(self.label_algorithm, 1, 0)
        self.algorithm_combo = QComboBox()
        self.algorithm_combo.addItems(["SGBM (Recommended)", "BM (Fast)"])
        grid.addWidget(self.algorithm_combo, 1, 1)

        grid.addWidget(QLabel("Quality:"), 2, 0)
        self.quality_combo = QComboBox()
        self.quality_combo.addItems(["High (Slow)", "Medium (Balanced)", "Fast"])
        self.quality_combo.setCurrentIndex(1)
        grid.addWidget(self.quality_combo, 2, 1)

        self.noise_filter_check = QCheckBox("Apply WLS noise filter")
        self.noise_filter_check.setChecked(True)
        grid.addWidget(self.noise_filter_check, 3, 0, 1, 2)

        self.processing_mode_combo.currentIndexChanged.connect(
            self._on_processing_mode_changed
        )
        self._on_processing_mode_changed(0)
        return group

    def _on_processing_mode_changed(self, index):
        is_dense = index == 1
        self.label_algorithm.setEnabled(is_dense)
        self.algorithm_combo.setEnabled(is_dense)
        if hasattr(self, 'btn_configure_cable'):
            self.btn_configure_cable.setEnabled(not is_dense)

    def _build_export_group(self):
        group = QGroupBox("Export Configuration")
        v = QVBoxLayout(group)

        dir_row = QHBoxLayout()
        dir_row.addWidget(QLabel("Directory:"))
        self.output_dir_label = QLabel("data/results")
        self.output_dir_label.setStyleSheet(
            f"QLabel {{ border: 1px solid {BORDER_SUBTLE}; padding: 4px;"
            f"background-color: {BG_CARD}; border-radius: 4px; color: {TEXT_SECONDARY}; }}"
        )
        dir_row.addWidget(self.output_dir_label)
        btn_dir = QPushButton("📁")
        btn_dir.setFixedSize(30, 30)
        btn_dir.setStyleSheet(
            f"QPushButton {{ background-color: {BG_CARD}; border-radius: 4px; }}"
        )
        btn_dir.clicked.connect(self._select_output_dir)
        dir_row.addWidget(btn_dir)
        v.addLayout(dir_row)

        v.addWidget(QLabel("Point cloud formats:"))
        fmt_grid = QGridLayout()
        self.format_ply_check = QCheckBox("PLY (Recommended)")
        self.format_ply_check.setChecked(True)
        self.format_xyz_check = QCheckBox("XYZ")
        self.format_pcd_check = QCheckBox("PCD")
        self.format_obj_check = QCheckBox("OBJ")
        fmt_grid.addWidget(self.format_ply_check, 0, 0)
        fmt_grid.addWidget(self.format_xyz_check, 0, 1)
        fmt_grid.addWidget(self.format_pcd_check, 1, 0)
        fmt_grid.addWidget(self.format_obj_check, 1, 1)
        v.addLayout(fmt_grid)
        return group

    def _build_progress_group(self):
        group = QGroupBox("Processing Progress")
        v = QVBoxLayout(group)
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        v.addWidget(self.progress_bar)
        self.progress_message = QLabel("Ready to process")
        self.progress_message.setAlignment(Qt.AlignCenter)
        self.progress_message.setStyleSheet(
            f"color: {TEXT_SECONDARY}; font-size: 12px; background: transparent;"
        )
        v.addWidget(self.progress_message)
        return group

    def _build_log_group(self):
        group = QGroupBox("Processing Log")
        v = QVBoxLayout(group)
        self.log_text = QTextEdit()
        self.log_text.setMaximumHeight(80)
        self.log_text.setReadOnly(True)
        v.addWidget(self.log_text)
        return group

    # ── Navigation ────────────────────────────────────────────────────────────

    def _go_back(self):
        main_window = self.window()
        if hasattr(main_window, 'navigate_to'):
            main_window.navigate_to(0)

    # ── Capture session loading ───────────────────────────────────────────────

    def _load_last_capture(self):
        try:
            captures_dir = Path("data/captures")
            if not captures_dir.exists():
                self._set_no_capture_info("No capture directory found")
                return

            session_dirs = [d for d in captures_dir.iterdir() if d.is_dir()]
            if not session_dirs:
                self._set_no_capture_info("No saved capture sessions")
                return

            latest = max(session_dirs, key=lambda d: d.stat().st_mtime)
            left_imgs  = list(latest.glob("left.jpg"))  + list(latest.glob("left.png"))
            right_imgs = list(latest.glob("right.jpg")) + list(latest.glob("right.png"))

            if left_imgs and right_imgs:
                self.selected_left_path  = str(left_imgs[0])
                self.selected_right_path = str(right_imgs[0])
                ts = datetime.fromtimestamp(latest.stat().st_mtime)
                self.capture_info_label.setText(
                    f"✓ Last Capture Detected\n"
                    f"Date: {ts.strftime('%Y-%m-%d %H:%M:%S')}\n"
                    f"Session: {latest.name}\n"
                    f"Status: Ready to process"
                )
                self.capture_info_label.setStyleSheet(
                    f"background-color: {BG_CARD}; color: {GREEN_ON};"
                    f"padding: 8px; border-radius: 4px; font-size: 12px;"
                )
                self.btn_start.setEnabled(True)
            else:
                self._set_no_capture_info("Last session is incomplete")
        except Exception as e:
            logger.error(f"Error loading last capture: {e}")
            self.capture_info_label.setText(f"✗ Error: {e}")
            self.btn_start.setEnabled(False)

    def _set_no_capture_info(self, reason):
        self.capture_info_label.setText(
            f"⚠  {reason}\n\n"
            "Take a photo with 'Capture for 3D Model' on the Dashboard\n"
            "or use the button below to select a session manually."
        )
        self.capture_info_label.setStyleSheet(
            f"background-color: {BG_CARD}; color: {YELLOW_WARN};"
            f"padding: 8px; border-radius: 4px; font-size: 12px;"
        )
        self.btn_start.setEnabled(False)

    def select_capture_session(self):
        try:
            captures_dir = Path("data/captures")
            if not captures_dir.exists():
                QMessageBox.warning(
                    self, "No Captures",
                    "Capture directory not found.\n"
                    "Take at least one photo first."
                )
                return

            session_dirs = sorted(
                [d for d in captures_dir.iterdir() if d.is_dir()],
                key=lambda d: d.stat().st_mtime, reverse=True,
            )
            if not session_dirs:
                QMessageBox.warning(
                    self, "No Sessions",
                    "No capture sessions found.\n"
                    "Take at least one photo first."
                )
                return

            # ── Mini picker dialog ────────────────────────────────────────────
            dlg = QDialog(self)
            dlg.setWindowTitle("Select Capture Session")
            dlg.setModal(True)
            dlg.resize(820, 460)
            dlg.setStyleSheet(
                f"background-color: {BG_DEEP}; color: {TEXT_PRIMARY};"
            )

            dv = QVBoxLayout(dlg)
            title = QLabel("Select a capture session to process")
            title.setFont(QFont("Segoe UI", 12, QFont.Bold))
            title.setAlignment(Qt.AlignCenter)
            title.setStyleSheet(
                f"color: {ACCENT_CYAN}; background: transparent; margin: 6px;"
            )
            dv.addWidget(title)

            content = QHBoxLayout()

            # Session list
            list_widget = QListWidget()
            list_widget.setMinimumWidth(340)
            for session in session_dirs:
                l = session / "left.jpg"
                if not l.exists(): l = session / "left.png"
                r = session / "right.jpg"
                if not r.exists(): r = session / "right.png"
                ts = datetime.fromtimestamp(session.stat().st_mtime)
                complete = l.exists() and r.exists()
                icon = "✓" if complete else "!"
                item = QListWidgetItem(
                    f"[{icon}] {session.name}\n    {ts.strftime('%Y-%m-%d %H:%M:%S')}"
                )
                item.setData(Qt.UserRole, session)
                if not complete:
                    item.setFlags(item.flags() & ~Qt.ItemIsEnabled)
                list_widget.addItem(item)
            content.addWidget(list_widget, 1)

            # Preview panel
            preview_frame = QFrame()
            preview_frame.setMinimumWidth(290)
            preview_frame.setStyleSheet(
                f"QFrame {{ background-color: {BG_CARD}; border-radius: 6px; }}"
            )
            pv = QVBoxLayout(preview_frame)
            pv.addWidget(QLabel("Preview"))
            left_prev  = QLabel("Left")
            right_prev = QLabel("Right")
            for lbl in (left_prev, right_prev):
                lbl.setAlignment(Qt.AlignCenter)
                lbl.setFixedHeight(175)
                lbl.setStyleSheet(f"color: {TEXT_DIM}; background: transparent;")
                pv.addWidget(lbl)
            pv.addStretch()
            content.addWidget(preview_frame, 0)
            dv.addLayout(content)

            def _update_preview(current, _prev):
                if current is None:
                    return
                sd = current.data(Qt.UserRole)
                if not sd:
                    return
                for base, lbl in [("left", left_prev), ("right", right_prev)]:
                    p = sd / f"{base}.jpg"
                    if not p.exists(): p = sd / f"{base}.png"
                    if p.exists():
                        px = QPixmap(str(p))
                        if not px.isNull():
                            lbl.setPixmap(px.scaled(
                                lbl.width() - 4, lbl.height() - 4,
                                Qt.KeepAspectRatio, Qt.SmoothTransformation,
                            ))

            list_widget.currentItemChanged.connect(_update_preview)
            if list_widget.count() > 0:
                list_widget.setCurrentRow(0)

            info = QLabel(f"Total sessions: {len(session_dirs)}")
            info.setStyleSheet(
                f"color: {TEXT_DIM}; font-style: italic; padding: 4px; background: transparent;"
            )
            dv.addWidget(info)

            btn_row = QHBoxLayout()
            btn_ok = QPushButton("Select")
            btn_ok.setDefault(True)
            btn_ok.clicked.connect(dlg.accept)
            btn_cancel = QPushButton("Cancel")
            btn_cancel.setStyleSheet(
                f"QPushButton {{ background-color: {BG_CARD}; color: {TEXT_PRIMARY}; }}"
            )
            btn_cancel.clicked.connect(dlg.reject)
            btn_row.addWidget(btn_ok)
            btn_row.addWidget(btn_cancel)
            dv.addLayout(btn_row)

            if dlg.exec_() == QDialog.Accepted:
                items = list_widget.selectedItems()
                if not items:
                    QMessageBox.information(self, "No Selection", "No session selected.")
                    return
                sd = items[0].data(Qt.UserRole)
                l = sd / "left.jpg"
                if not l.exists(): l = sd / "left.png"
                r = sd / "right.jpg"
                if not r.exists(): r = sd / "right.png"
                self.selected_left_path   = str(l)
                self.selected_right_path  = str(r)
                self.current_session_path = sd

                ts = datetime.fromtimestamp(sd.stat().st_mtime)
                self.capture_info_label.setText(
                    f"✓ Session Selected\n"
                    f"{sd.name}\n"
                    f"Date: {ts.strftime('%Y-%m-%d %H:%M:%S')}\n"
                    f"Status: Ready to process"
                )
                self.capture_info_label.setStyleSheet(
                    f"background-color: {BG_CARD}; color: {GREEN_ON};"
                    f"padding: 8px; border-radius: 4px; font-size: 12px;"
                )
                self.btn_configure_cable.setEnabled(True)
                self.btn_start.setEnabled(True)
                self.add_log_message(f"Session loaded: {sd.name}")

        except Exception as e:
            logger.error(f"Error selecting session: {e}")
            QMessageBox.critical(self, "Error", f"Error selecting session:\n{e}")

    def _select_output_dir(self):
        path = QFileDialog.getExistingDirectory(self, "Select Output Directory", "data/results")
        if path:
            self.output_dir_label.setText(path)

    def _get_export_formats(self):
        fmts = []
        if self.format_ply_check.isChecked(): fmts.append('ply')
        if self.format_xyz_check.isChecked(): fmts.append('xyz')
        if self.format_pcd_check.isChecked(): fmts.append('pcd')
        if self.format_obj_check.isChecked(): fmts.append('obj')
        return fmts or ['ply']

    # ── Processing ────────────────────────────────────────────────────────────

    def start_processing(self):
        try:
            if not (self.selected_left_path and self.selected_right_path):
                QMessageBox.warning(
                    self, "Warning", "Select both left and right images first."
                )
                return
            if not (Path(self.selected_left_path).exists() and
                    Path(self.selected_right_path).exists()):
                QMessageBox.critical(self, "Error", "One or both images do not exist.")
                return

            output_dir = Path(self.output_dir_label.text())
            output_dir.mkdir(parents=True, exist_ok=True)

            algorithm = "SGBM" if "SGBM" in self.algorithm_combo.currentText() else "BM"
            processing_params = {
                'left_image':        self.selected_left_path,
                'right_image':       self.selected_right_path,
                'algorithm':         algorithm,
                'quality':           self.quality_combo.currentText(),
                'use_noise_filter':  self.noise_filter_check.isChecked(),
                'export_point_cloud': True,
                'export_formats':    self._get_export_formats(),
                'output_dir':        output_dir,
            }

            self.add_log_message("Starting 3D processing...")
            self.btn_start.setEnabled(False)
            self.btn_cancel.setEnabled(True)
            self.progress_bar.setValue(0)

            cable_masks = None
            wire_paths  = None
            use_dense   = self.processing_mode_combo.currentIndex() == 1

            if use_dense:
                self.add_log_message("Dense SGBM mode — full image disparity", "INFO")
            else:
                if (self.cable_filter_configured
                        and self.cable_mask_left is not None
                        and self.cable_mask_right is not None):
                    cable_masks = (self.cable_mask_left, self.cable_mask_right)
                    if (self.wire_tracking_result is not None
                            and self.wire_tracking_result.get('success')):
                        wire_paths = {
                            'left':  self.wire_tracking_result['left']['path'],
                            'right': self.wire_tracking_result['right']['path'],
                            'dt_profile_left':    self.wire_tracking_result['left'].get('dt_profile'),
                            'decision_points_2d': self.wire_tracking_result['left'].get('decision_points_2d'),
                        }
                        self.add_log_message("Using pre-calculated geometric paths", "INFO")
                    else:
                        self.add_log_message("Wire tracking unavailable, using masks only", "WARNING")
                else:
                    self.add_log_message("No cable mask — run Configure Cable Filter first", "WARNING")

            self.processing_thread = ProcessingWorkerThread(
                self.camera_config, processing_params,
                cable_masks=cable_masks, wire_paths=wire_paths,
            )
            self.processing_thread.progress_update.connect(self._update_progress)
            self.processing_thread.processing_complete.connect(self._on_processing_complete)
            self.processing_thread.log_message.connect(self.add_log_message)
            self.processing_thread.intermediate_result.connect(self._on_intermediate_result)
            self.processing_thread.start()

        except Exception as e:
            self.add_log_message(f"Error starting processing: {e}", "ERROR")
            QMessageBox.critical(self, "Error", f"Error starting processing:\n{e}")

    def cancel_processing(self):
        if self.processing_thread and self.processing_thread.isRunning():
            self.add_log_message("Canceling processing...", "WARNING")
            self.processing_thread.stop()
            if not self.processing_thread.wait(5000):
                self.processing_thread.terminate()
                self.processing_thread.wait(2000)
            self._reset_ui_after_processing()

    def _update_progress(self, progress, message):
        self.progress_bar.setValue(progress)
        self.progress_message.setText(message)
        QApplication.processEvents()

    def _on_intermediate_result(self, result_type, data):
        try:
            if result_type == "disparity":
                self.results_widget.update_disparity(data)
            elif result_type == "depth":
                self.results_widget.update_depth(data)
            elif result_type == "confidence":
                self.results_widget.update_confidence(data)
        except Exception as e:
            logger.error(f"Error displaying intermediate result {result_type}: {e}")

    def _on_processing_complete(self, success, result):
        try:
            if success:
                self.add_log_message("3D processing completed successfully!", "INFO")
                self.results_widget.update_statistics(result)
                export_files = result.get('export_files', [])
                files_info   = "\n".join([f"• {Path(f).name}" for f in export_files])
                QMessageBox.information(
                    self, "Processing Successful",
                    f"3D model generated.\n\n"
                    f"Time: {result.get('processing_time_seconds', 0):.1f}s\n"
                    f"Points: {result.get('point_cloud', {}).get('num_points', 0):,}\n\n"
                    f"Exported:\n{files_info}",
                )
            else:
                error_msg = result.get('error', 'Unknown error')
                self.add_log_message(f"Processing failed: {error_msg}", "ERROR")
                QMessageBox.critical(
                    self, "Processing Error",
                    f"3D processing failed:\n\n{error_msg}",
                )
        except Exception as e:
            logger.error(f"Error handling processing result: {e}")
        finally:
            self._reset_ui_after_processing()

    def _reset_ui_after_processing(self):
        self.btn_start.setEnabled(True)
        self.btn_cancel.setEnabled(False)
        self.progress_message.setText("Processing completed")

    # ── Cable filter ──────────────────────────────────────────────────────────

    def open_cable_filter_config(self):
        try:
            left_img  = cv2.imread(self.selected_left_path)
            right_img = cv2.imread(self.selected_right_path)
            if left_img is None or right_img is None:
                QMessageBox.warning(self, "Error", "Could not load session images.")
                return

            from edge_detection_tuner import open_cable_detection_tuner_with_switch
            result = open_cable_detection_tuner_with_switch(
                left_img, right_img,
                self.selected_left_path, self.selected_right_path,
            )

            if result is not None:
                self.cable_mask_left, self.cable_mask_right = result
                self.cable_filter_configured = True
                self.add_log_message("Detecting cable endpoints...", "INFO")

                try:
                    from processing.endpoint_detector import detect_wire_endpoints
                    start_left, end_left   = detect_wire_endpoints(self.cable_mask_left,  side="left")
                    start_right, end_right = detect_wire_endpoints(self.cable_mask_right, side="right")
                    self.add_log_message(f"  LEFT  endpoints: {start_left} -> {end_left}",   "INFO")
                    self.add_log_message(f"  RIGHT endpoints: {start_right} -> {end_right}", "INFO")

                    from gui.wire_method_choice import WireMethodChoiceDialog
                    method_dlg = WireMethodChoiceDialog(
                        left_img, right_img,
                        self.cable_mask_left, self.cable_mask_right,
                        start_left, end_left, start_right, end_right,
                        self,
                    )
                    method_dlg.exec_()
                    tracking_results = method_dlg.get_results()

                    if tracking_results and tracking_results['success']:
                        self.wire_tracking_result = tracking_results
                        self.add_log_message(
                            f"Wire tracking OK — "
                            f"LEFT {len(tracking_results['left']['path'])} pts "
                            f"| RIGHT {len(tracking_results['right']['path'])} pts",
                            "INFO",
                        )
                        self.filter_status_label.setText("✓ Filter + Wire Tracking OK")
                        self.filter_status_label.setStyleSheet(
                            f"background-color: {BG_CARD}; color: {GREEN_ON};"
                            f"padding: 6px; border-radius: 3px; font-size: 11px;"
                        )
                    else:
                        self.wire_tracking_result = None
                        self.filter_status_label.setText("⚠  Filter OK — Wire tracking incomplete")
                        self.filter_status_label.setStyleSheet(
                            f"background-color: {BG_CARD}; color: {YELLOW_WARN};"
                            f"padding: 6px; border-radius: 3px; font-size: 11px;"
                        )

                except Exception as e:
                    logger.error(f"Wire tracking error: {e}")
                    self.add_log_message(f"Wire tracking error: {e}", "ERROR")
                    self.wire_tracking_result = None
                    self.filter_status_label.setText("✓ Filter configured (no wire tracking)")
                    self.filter_status_label.setStyleSheet(
                        f"background-color: {BG_CARD}; color: {GREEN_ON};"
                        f"padding: 6px; border-radius: 3px; font-size: 11px;"
                    )
                    QMessageBox.information(
                        self, "Notice",
                        f"Cable filter configured.\n\nWire tracking failed ({e}), "
                        "but masks are available.",
                    )
            else:
                QMessageBox.information(self, "Cancelled", "Filter configuration cancelled.")

        except Exception as e:
            logger.error(f"Error opening filter config: {e}")
            QMessageBox.critical(self, "Error", f"Error opening filter:\n{e}")

    # ── Log ───────────────────────────────────────────────────────────────────

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
        if level == "ERROR":
            logger.error(message)
        elif level == "WARNING":
            logger.warning(message)
        else:
            logger.info(message)


# Alias for any code that still references the old QDialog name
ProcessingDialog = ProcessingPage
