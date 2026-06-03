#!/usr/bin/env python3
"""
Diálogo de procesamiento 3D para generar modelos desde pares estéreo
Maneja toda la pipeline de procesamiento: disparidad -> profundidad -> nube de puntos
"""

import os
import cv2
import numpy as np
from datetime import datetime
from pathlib import Path

from PyQt5.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel,
                           QPushButton, QProgressBar, QTextEdit, QGroupBox,
                           QGridLayout, QMessageBox, QCheckBox, QSpinBox,
                           QDoubleSpinBox, QFrame, QApplication, QComboBox,
                           QFileDialog, QTabWidget, QWidget, QScrollArea,
                           QListWidget, QListWidgetItem)
from PyQt5.QtCore import QThread, pyqtSignal, QTimer, Qt
from PyQt5.QtGui import QPixmap, QImage, QFont, QPainter

from processing.stereo_processor import StereoProcessor
from processing.point_cloud_generator import PointCloudExporter
from utils.logger import get_logger

logger = get_logger(__name__)

class ProcessingWorkerThread(QThread):
    """Hilo para ejecutar procesamiento 3D sin bloquear UI"""
    progress_update = pyqtSignal(int, str)
    processing_complete = pyqtSignal(bool, dict)
    log_message = pyqtSignal(str, str)  # message, level
    intermediate_result = pyqtSignal(str, object)  # tipo, datos

    def __init__(self, camera_config, processing_params, cable_masks=None, wire_paths=None):
        super().__init__()
        self.camera_config = camera_config
        self.processing_params = processing_params
        self.cable_masks = cable_masks  # (mask_left, mask_right) o None
        self.wire_paths = wire_paths    # {'left': [...], 'right': [...]} o None - YA CALCULADOS
        self.should_stop = False
        
    def run(self):
        """Ejecutar pipeline completo de procesamiento 3D"""
        try:
            self.log_message.emit("Starting 3D processing...", "INFO")

            # Inicializar procesador
            processor = StereoProcessor(self.camera_config)

            # Cargar imágenes
            self.progress_update.emit(5, "Loading images...")
            left_img = cv2.imread(self.processing_params['left_image'])
            right_img = cv2.imread(self.processing_params['right_image'])

            if left_img is None or right_img is None:
                raise RuntimeError("Could not load images")

            self.log_message.emit(f"Images loaded: {left_img.shape}", "INFO")

            # === DECIDIR QUÉ MÉTODO USAR ===
            if self.wire_paths is not None:
                # ============================================
                # MÉTODO GEOMÉTRICO: Usar paths YA CALCULADOS
                # NO vuelve a correr SmartWireTracker
                # ============================================
                self.log_message.emit("🎯 Using PRE-CALCULATED GEOMETRIC PATHS", "INFO")
                self.log_message.emit(f"   Left path: {len(self.wire_paths['left'])} points", "INFO")
                self.log_message.emit(f"   Right path: {len(self.wire_paths['right'])} points", "INFO")

                # Rectificar imágenes primero
                self.progress_update.emit(10, "Rectifying images...")
                left_rect, right_rect = processor.rectify_images(left_img, right_img)

                # Calcular disparidad DIRECTAMENTE desde los paths
                self.progress_update.emit(30, "Calculating disparity from geometric paths...")

                image_shape = left_rect.shape[:2]
                disparity_result = processor.compute_disparity_from_wire_paths(
                    self.wire_paths['left'],
                    self.wire_paths['right'],
                    image_shape,
                    save_debug=True
                )

                if not disparity_result['success']:
                    raise RuntimeError("Could not calculate disparity from geometric paths")

                # Generar nube de puntos DIRECTAMENTE desde los matches
                # (NO desde disparity_map que pierde puntos por colisión de píxeles)
                self.progress_update.emit(70, "Generating 3D point cloud from matches...")

                point_cloud_result = processor.generate_point_cloud_from_matches(
                    disparity_result['matches'],
                    disparity_result['disparities'],
                    left_rect
                )

                self.log_message.emit(f"☁️ Cloud generated: {point_cloud_result['num_points']} 3D points", "INFO")

                # Calcular profundidad para estadísticas (opcional)
                depth_result = processor.disparity_to_depth(disparity_result['disparity_map'])

                # Construir resultado final
                result = {
                    'success': True,
                    'algorithm': 'GEOMETRIC_PATH',
                    'disparity': disparity_result,
                    'depth': depth_result,
                    'point_cloud': point_cloud_result
                }

            elif self.cable_masks is not None:
                # ============================================
                # FALLBACK: Tiene máscara pero no paths
                # Usar SGBM con máscara como filtro
                # ============================================
                mask_left, _ = self.cable_masks
                self.log_message.emit("⚠️ No geometric paths, using SGBM + mask", "WARNING")

                result = processor.process_stereo_pair(
                    left_img, right_img,
                    algorithm=self.processing_params['algorithm'],
                    progress_callback=self.progress_callback,
                    save_debug_images=True,
                    cable_mask=mask_left
                )

            else:
                # ============================================
                # MÉTODO TRADICIONAL: SGBM (sin nada)
                # ============================================
                self.log_message.emit("⚠️ No cable mask - using traditional SGBM", "WARNING")

                result = processor.process_stereo_pair(
                    left_img, right_img,
                    algorithm=self.processing_params['algorithm'],
                    progress_callback=self.progress_callback,
                    save_debug_images=True,
                    cable_mask=None
                )

            if not result['success']:
                raise RuntimeError(f"Processing error: {result.get('error')}")
            
            # Emitir resultados intermedios
            self.intermediate_result.emit("disparity", result['disparity']['disparity_map'])
            self.intermediate_result.emit("depth", result['depth']['depth_map'])
            self.intermediate_result.emit("confidence", result['disparity']['confidence_map'])
            
            # Exportar nube de puntos si se solicita
            if self.processing_params.get('export_point_cloud', True):
                self.progress_update.emit(90, "Exporting point cloud...")
                
                exporter = PointCloudExporter()
                
                # Exportar en formatos solicitados
                export_results = []
                for format_type in self.processing_params.get('export_formats', ['ply']):
                    output_file = self.processing_params['output_dir'] / f"point_cloud.{format_type}"
                    
                    export_result = exporter.export_point_cloud(
                        result['point_cloud']['points'],
                        result['point_cloud']['colors'],
                        str(output_file),
                        format_type
                    )
                    
                    if export_result['success']:
                        export_results.append(str(output_file))
                        self.log_message.emit(f"Cloud exported: {output_file}", "INFO")
                
                result['export_files'] = export_results
            
            self.progress_update.emit(100, "Processing completed")
            self.processing_complete.emit(True, result)
            
        except Exception as e:
            self.log_message.emit(f"Error during processing: {e}", "ERROR")
            self.processing_complete.emit(False, {'error': str(e)})
    
    def progress_callback(self, progress, message):
        """Callback para progreso desde el procesador"""
        if not self.should_stop:
            # Ajustar rango: procesamiento va del 10% al 85%
            adjusted_progress = 10 + int(progress * 0.75)
            self.progress_update.emit(adjusted_progress, message)
    
    def stop(self):
        """Detener procesamiento"""
        self.should_stop = True

class ResultsVisualizationWidget(QWidget):
    """Widget para visualizar resultados del procesamiento"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.init_ui()
        
    def init_ui(self):
        """Inicializar interfaz de visualización"""
        layout = QVBoxLayout(self)
        
        # Tabs para diferentes visualizaciones
        self.tabs = QTabWidget()
        layout.addWidget(self.tabs)
        
        # Tab de disparidad
        self.disparity_tab = self.create_image_tab("Disparity Map")
        self.tabs.addTab(self.disparity_tab, "Disparity")
        
        # Tab de profundidad
        self.depth_tab = self.create_image_tab("Depth Map")
        self.tabs.addTab(self.depth_tab, "Depth")
        
        # Tab de confianza
        self.confidence_tab = self.create_image_tab("Confidence Map")
        self.tabs.addTab(self.confidence_tab, "Confidence")
        
        # Tab de estadísticas
        self.stats_tab = self.create_stats_tab()
        self.tabs.addTab(self.stats_tab, "Statistics")
        
    def create_image_tab(self, title):
        """Crear tab para visualización de imagen"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        
        # Título
        title_label = QLabel(title)
        title_label.setFont(QFont("Arial", 12, QFont.Bold))
        title_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(title_label)
        
        # Área de scroll para imagen
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setAlignment(Qt.AlignCenter)
        
        # Label para imagen
        image_label = QLabel()
        image_label.setAlignment(Qt.AlignCenter)
        image_label.setMinimumSize(400, 300)
        image_label.setStyleSheet("""
            QLabel {
                border: 2px dashed #CCCCCC;
                background-color: #F9F9F9;
                color: #666666;
            }
        """)
        image_label.setText("No data")
        
        scroll_area.setWidget(image_label)
        layout.addWidget(scroll_area)
        
        # Guardar referencia al label
        widget.image_label = image_label
        
        return widget
    
    def create_stats_tab(self):
        """Crear tab de estadísticas"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        
        # Título
        title = QLabel("Processing Statistics")
        title.setFont(QFont("Arial", 12, QFont.Bold))
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)
        
        # Área de texto para estadísticas
        self.stats_text = QTextEdit()
        self.stats_text.setReadOnly(True)
        self.stats_text.setFont(QFont("Courier New", 10))
        layout.addWidget(self.stats_text)
        
        return widget
    
    def update_disparity(self, disparity_map):
        """Actualizar visualización de disparidad"""
        try:
            # Normalizar para visualización
            disparity_vis = cv2.normalize(disparity_map, None, 0, 255, cv2.NORM_MINMAX)
            disparity_vis = disparity_vis.astype(np.uint8)
            
            # Aplicar colormap
            disparity_color = cv2.applyColorMap(disparity_vis, cv2.COLORMAP_JET)
            
            # Convertir a QPixmap
            height, width, channel = disparity_color.shape
            bytes_per_line = 3 * width
            q_image = QImage(disparity_color.data, width, height, bytes_per_line, QImage.Format_RGB888)
            q_image = q_image.rgbSwapped()  # BGR -> RGB
            
            pixmap = QPixmap.fromImage(q_image)
            
            # Escalar si es muy grande
            if pixmap.width() > 800 or pixmap.height() > 600:
                pixmap = pixmap.scaled(800, 600, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            
            self.disparity_tab.image_label.setPixmap(pixmap)
            
        except Exception as e:
            logger.error(f"Error actualizando visualización de disparidad: {e}")
    
    def update_depth(self, depth_map):
        """Actualizar visualización de profundidad"""
        try:
            # Crear visualización de profundidad
            depth_vis = depth_map.copy()
            depth_vis[depth_vis == 0] = np.nan  # Marcar píxeles inválidos
            
            # Normalizar para visualización
            valid_mask = ~np.isnan(depth_vis)
            if np.any(valid_mask):
                depth_min = np.nanmin(depth_vis)
                depth_max = np.nanmax(depth_vis)
                
                depth_normalized = (depth_vis - depth_min) / (depth_max - depth_min)
                depth_normalized = np.nan_to_num(depth_normalized, 0) * 255
                depth_normalized = depth_normalized.astype(np.uint8)
                
                # Aplicar colormap inverso (más cerca = más caliente)
                depth_color = cv2.applyColorMap(255 - depth_normalized, cv2.COLORMAP_HOT)
                
                # Marcar píxeles inválidos en negro
                invalid_mask = ~valid_mask
                depth_color[invalid_mask] = [0, 0, 0]
                
                # Convertir a QPixmap
                height, width, channel = depth_color.shape
                bytes_per_line = 3 * width
                q_image = QImage(depth_color.data, width, height, bytes_per_line, QImage.Format_RGB888)
                q_image = q_image.rgbSwapped()
                
                pixmap = QPixmap.fromImage(q_image)
                
                if pixmap.width() > 800 or pixmap.height() > 600:
                    pixmap = pixmap.scaled(800, 600, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                
                self.depth_tab.image_label.setPixmap(pixmap)
            else:
                self.depth_tab.image_label.setText("No valid depth data")
                
        except Exception as e:
            logger.error(f"Error actualizando visualización de profundidad: {e}")
    
    def update_confidence(self, confidence_map):
        """Actualizar visualización de confianza"""
        try:
            # Normalizar mapa de confianza
            confidence_vis = (confidence_map * 255).astype(np.uint8)
            
            # Aplicar colormap
            confidence_color = cv2.applyColorMap(confidence_vis, cv2.COLORMAP_VIRIDIS)
            
            # Convertir a QPixmap
            height, width, channel = confidence_color.shape
            bytes_per_line = 3 * width
            q_image = QImage(confidence_color.data, width, height, bytes_per_line, QImage.Format_RGB888)
            q_image = q_image.rgbSwapped()
            
            pixmap = QPixmap.fromImage(q_image)
            
            if pixmap.width() > 800 or pixmap.height() > 600:
                pixmap = pixmap.scaled(800, 600, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            
            self.confidence_tab.image_label.setPixmap(pixmap)
            
        except Exception as e:
            logger.error(f"Error actualizando visualización de confianza: {e}")
    
    def update_statistics(self, processing_result):
        """Actualizar estadísticas de procesamiento"""
        try:
            stats_text = "=== 3D PROCESSING STATISTICS ===\n\n"
            
            # Información general
            stats_text += f"Processing time: {processing_result.get('processing_time_seconds', 0):.2f} seconds\n"
            stats_text += f"Algorithm used: {processing_result.get('algorithm_used', 'N/A')}\n"
            stats_text += f"Input shape: {processing_result.get('input_shape', 'N/A')}\n\n"
            
            # Estadísticas de disparidad
            if 'disparity' in processing_result:
                disp_data = processing_result['disparity']
                stats_text += "--- DISPARITY ---\n"
                stats_text += f"Minimum disparity: {disp_data.get('min_disparity', 0):.2f} pixels\n"
                stats_text += f"Maximum disparity: {disp_data.get('max_disparity', 0):.2f} pixels\n"
                stats_text += f"Average disparity: {disp_data.get('mean_disparity', 0):.2f} pixels\n"
                stats_text += f"Valid pixels: {disp_data.get('valid_pixels', 0):,}\n"
                stats_text += f"Filtering applied: {'Yes' if disp_data.get('filtered', False) else 'No'}\n\n"
            
            # Estadísticas de profundidad
            if 'depth' in processing_result:
                depth_data = processing_result['depth']
                stats_text += "--- DEPTH ---\n"
                stats_text += f"Minimum depth: {depth_data.get('min_depth', 0):.3f} meters\n"
                stats_text += f"Maximum depth: {depth_data.get('max_depth', 0):.3f} meters\n"
                stats_text += f"Average depth: {depth_data.get('mean_depth', 0):.3f} meters\n"
                stats_text += f"Baseline: {depth_data.get('baseline_meters', 0)*1000:.1f} mm\n"
                stats_text += f"Focal length: {depth_data.get('focal_length_pixels', 0):.1f} pixels\n\n"
            
            # Estadísticas de nube de puntos
            if 'point_cloud' in processing_result:
                pc_data = processing_result['point_cloud']
                stats_text += "--- POINT CLOUD ---\n"
                stats_text += f"Number of points: {pc_data.get('num_points', 0):,}\n"
                stats_text += f"Density: {pc_data.get('density', 0):.4f}\n"
                
                bounds = pc_data.get('bounds', {})
                stats_text += f"X Bounds: {bounds.get('x_min', 0):.3f} to {bounds.get('x_max', 0):.3f} m\n"
                stats_text += f"Y Bounds: {bounds.get('y_min', 0):.3f} to {bounds.get('y_max', 0):.3f} m\n"
                stats_text += f"Z Bounds: {bounds.get('z_min', 0):.3f} to {bounds.get('z_max', 0):.3f} m\n\n"
            
            # Métricas de calidad
            if 'quality_metrics' in processing_result:
                quality = processing_result['quality_metrics']
                stats_text += "--- QUALITY ---\n"
                stats_text += f"Valid pixel ratio: {quality.get('valid_pixel_ratio', 0):.1%}\n"
                stats_text += f"Average confidence: {quality.get('mean_confidence', 0):.3f}\n"
                stats_text += f"Point density: {quality.get('point_density', 0):.4f}\n\n"
            
            # Archivos exportados
            if 'export_files' in processing_result:
                stats_text += "--- EXPORTED FILES ---\n"
                for file_path in processing_result['export_files']:
                    file_size = Path(file_path).stat().st_size / (1024 * 1024)  # MB
                    stats_text += f"• {Path(file_path).name} ({file_size:.1f} MB)\n"
            
            self.stats_text.setText(stats_text)
            
        except Exception as e:
            logger.error(f"Error actualizando estadísticas: {e}")
            self.stats_text.setText(f"Error loading statistics: {e}")

class WireTrackingWorkerThread(QThread):
    """Hilo que ejecuta SmartWireTracker y emite el path parcial para animacion"""
    path_updated = pyqtSignal(list, int)  # path parcial, iteracion
    tracking_finished = pyqtSignal(dict)  # resultado final

    def __init__(self, mask, start_pt, end_pt):
        super().__init__()
        self.mask = mask
        self.start_pt = start_pt
        self.end_pt = end_pt

    def run(self):
        from processing.smart_wire_tracker import SmartWireTracker
        # Escalar max_iterations según resolución de la máscara
        h, w = self.mask.shape[:2]
        resolution_scale = max(1.0, (h * w) / (1920 * 1440))
        max_iter = int(10000 * min(resolution_scale, 10))  # Tope: 100k

        tracker = SmartWireTracker(self.mask, self.start_pt, self.end_pt)
        result = tracker.track_wire(
            max_iterations=max_iter,
            step_callback=self._on_step
        )
        self.tracking_finished.emit(result)

    def _on_step(self, path, iteration):
        self.path_updated.emit(path, iteration)


class WireTrackingVisualizationDialog(QDialog):
    """Ventana que muestra en tiempo real como el tracker reconstruye el cable"""

    def __init__(self, left_img, right_img, mask_left, mask_right,
                 start_left, end_left, start_right, end_right, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Wire Tracking - Live Reconstruction")
        self.setModal(True)

        # Guardar datos
        self.left_img = left_img.copy()
        self.right_img = right_img.copy()
        self.mask_left = mask_left
        self.mask_right = mask_right
        self.start_left = start_left
        self.end_left = end_left
        self.start_right = start_right
        self.end_right = end_right

        # Estado
        self.current_path_left = []
        self.current_path_right = []
        self.result_left = None
        self.result_right = None
        self.phase = "idle"  # idle -> left -> right -> done

        # Ajustar al tamano de pantalla
        screen = QApplication.primaryScreen()
        if screen:
            available = screen.availableGeometry()
            w = min(1100, available.width() - 40)
            h = min(550, available.height() - 60)
            self.resize(w, h)
        else:
            self.resize(1100, 550)

        self._build_ui()
        # Iniciar automaticamente
        QTimer.singleShot(300, self._start_left_tracking)

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(4)
        layout.setContentsMargins(6, 6, 6, 6)

        # Estado
        self.status_label = QLabel("Preparing...")
        self.status_label.setFont(QFont("Arial", 11, QFont.Bold))
        self.status_label.setAlignment(Qt.AlignCenter)
        self.status_label.setStyleSheet("color: #1976D2; margin: 2px;")
        layout.addWidget(self.status_label)

        # Dos imagenes lado a lado
        images_layout = QHBoxLayout()

        # Izquierda
        left_frame = QFrame()
        left_frame_layout = QVBoxLayout(left_frame)
        left_frame_layout.setContentsMargins(2, 2, 2, 2)
        self.left_header = QLabel(f"Left - S:{self.start_left} E:{self.end_left}")
        self.left_header.setFont(QFont("Arial", 9, QFont.Bold))
        self.left_header.setAlignment(Qt.AlignCenter)
        self.left_header.setStyleSheet("color: #2196F3;")
        left_frame_layout.addWidget(self.left_header)
        self.left_image_label = QLabel()
        self.left_image_label.setAlignment(Qt.AlignCenter)
        # Mostrar endpoints detectados en la imagen inicial
        left_init = self._draw_wire_on_image(self.left_img, [], "LEFT")
        self.left_image_label.setPixmap(self._cv2_to_pixmap(left_init))
        left_frame_layout.addWidget(self.left_image_label)
        images_layout.addWidget(left_frame)

        # Derecha
        right_frame = QFrame()
        right_frame_layout = QVBoxLayout(right_frame)
        right_frame_layout.setContentsMargins(2, 2, 2, 2)
        self.right_header = QLabel(f"Right - S:{self.start_right} E:{self.end_right}")
        self.right_header.setFont(QFont("Arial", 9, QFont.Bold))
        self.right_header.setAlignment(Qt.AlignCenter)
        self.right_header.setStyleSheet("color: #FF9800;")
        right_frame_layout.addWidget(self.right_header)
        self.right_image_label = QLabel()
        self.right_image_label.setAlignment(Qt.AlignCenter)
        # Mostrar endpoints detectados en la imagen inicial
        right_init = self._draw_wire_on_image(self.right_img, [], "RIGHT")
        self.right_image_label.setPixmap(self._cv2_to_pixmap(right_init))
        right_frame_layout.addWidget(self.right_image_label)
        images_layout.addWidget(right_frame)

        layout.addLayout(images_layout)

        # Boton cerrar (deshabilitado hasta que termine)
        self.btn_close = QPushButton("Processing...")
        self.btn_close.setFixedHeight(30)
        self.btn_close.setEnabled(False)
        self.btn_close.clicked.connect(self.accept)
        self.btn_close.setStyleSheet("""
            QPushButton {
                background-color: #2196F3; color: white;
                font-weight: bold; border-radius: 4px;
            }
            QPushButton:hover { background-color: #1976D2; }
            QPushButton:disabled { background-color: #CCCCCC; color: #666666; }
        """)
        layout.addWidget(self.btn_close)

    def _start_left_tracking(self):
        self.phase = "left"
        self.status_label.setText("Processing left image...")
        self.left_header.setText("Left - processing...")

        self.worker = WireTrackingWorkerThread(
            self.mask_left, self.start_left, self.end_left
        )
        self.worker.path_updated.connect(self._on_left_path_update)
        self.worker.tracking_finished.connect(self._on_left_finished)
        self.worker.start()

    def _on_left_path_update(self, path, iteration):
        self.current_path_left = path
        vis = self._draw_wire_on_image(self.left_img, path, "LEFT")
        self.left_image_label.setPixmap(self._cv2_to_pixmap(vis))
        self.left_header.setText(f"Left - {len(path)} pts (iter {iteration})")

    def _on_left_finished(self, result):
        self.result_left = result
        self.current_path_left = result['path']
        # Dibujar resultado final
        vis = self._draw_wire_on_image(self.left_img, result['path'], "LEFT")
        self.left_image_label.setPixmap(self._cv2_to_pixmap(vis))
        self.left_header.setText(
            f"Left - {len(result['path'])} pts | Cov: {result['coverage']*100:.1f}%"
        )
        # Iniciar derecha
        QTimer.singleShot(500, self._start_right_tracking)

    def _start_right_tracking(self):
        self.phase = "right"
        self.status_label.setText("Processing right image...")
        self.right_header.setText("Right - processing...")

        self.worker = WireTrackingWorkerThread(
            self.mask_right, self.start_right, self.end_right
        )
        self.worker.path_updated.connect(self._on_right_path_update)
        self.worker.tracking_finished.connect(self._on_right_finished)
        self.worker.start()

    def _on_right_path_update(self, path, iteration):
        self.current_path_right = path
        vis = self._draw_wire_on_image(self.right_img, path, "RIGHT")
        self.right_image_label.setPixmap(self._cv2_to_pixmap(vis))
        self.right_header.setText(f"Right - {len(path)} pts (iter {iteration})")

    def _on_right_finished(self, result):
        self.result_right = result
        self.current_path_right = result['path']
        vis = self._draw_wire_on_image(self.right_img, result['path'], "RIGHT")
        self.right_image_label.setPixmap(self._cv2_to_pixmap(vis))
        self.right_header.setText(
            f"Right - {len(result['path'])} pts | Cov: {result['coverage']*100:.1f}%"
        )
        self.phase = "done"
        self.status_label.setText("Reconstruction completed")
        self.status_label.setStyleSheet("color: #2E7D32; font-weight: bold;")
        self.btn_close.setText("Close")
        self.btn_close.setEnabled(True)

    def get_results(self):
        """Retorna los resultados del tracking de ambas imagenes"""
        if self.result_left and self.result_right:
            return {
                'success': self.result_left['success'] and self.result_right['success'],
                'left': self.result_left,
                'right': self.result_right
            }
        return None

    def _draw_wire_on_image(self, img, path, side):
        vis = img.copy()

        # Siempre dibujar los endpoints DETECTADOS (start/end del EndpointDetector)
        if side == "LEFT":
            det_start, det_end = self.start_left, self.end_left
        else:
            det_start, det_end = self.start_right, self.end_right

        # Escalar el tamaño de los marcadores según resolución
        h, w = vis.shape[:2]
        marker_size = max(6, min(w, h) // 150)
        font_scale = max(0.5, min(w, h) / 2000.0)
        thickness = max(1, marker_size // 3)

        # Dibujar endpoints detectados (siempre visibles)
        cv2.circle(vis, (int(det_start[0]), int(det_start[1])),
                   marker_size, (0, 255, 0), -1)  # Verde = START
        cv2.circle(vis, (int(det_end[0]), int(det_end[1])),
                   marker_size, (0, 0, 255), -1)    # Rojo = END
        # Etiquetas
        cv2.putText(vis, "START",
                    (int(det_start[0]) + marker_size + 2, int(det_start[1]) + marker_size),
                    cv2.FONT_HERSHEY_SIMPLEX, font_scale, (0, 255, 0), thickness)
        cv2.putText(vis, "END",
                    (int(det_end[0]) + marker_size + 2, int(det_end[1]) + marker_size),
                    cv2.FONT_HERSHEY_SIMPLEX, font_scale, (0, 0, 255), thickness)

        if len(path) < 2:
            return vis

        # Dibujar path del tracker
        color = (0, 200, 255) if side == "LEFT" else (0, 165, 255)
        line_thickness = max(1, marker_size // 3)
        for i in range(len(path) - 1):
            pt1 = (int(path[i][0]), int(path[i][1]))
            pt2 = (int(path[i+1][0]), int(path[i+1][1]))
            cv2.line(vis, pt1, pt2, color, line_thickness, cv2.LINE_AA)

        return vis

    def _cv2_to_pixmap(self, cv_img):
        if len(cv_img.shape) == 2:
            cv_img = cv2.cvtColor(cv_img, cv2.COLOR_GRAY2BGR)
        rgb = cv2.cvtColor(cv_img, cv2.COLOR_BGR2RGB)
        h, w, ch = rgb.shape
        bytes_per_line = ch * w
        q_image = QImage(rgb.data, w, h, bytes_per_line, QImage.Format_RGB888)
        pixmap = QPixmap.fromImage(q_image.copy())  # .copy() para evitar dangling pointer
        max_w, max_h = 520, 400
        if pixmap.width() > max_w or pixmap.height() > max_h:
            pixmap = pixmap.scaled(max_w, max_h, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        return pixmap


class ProcessingDialog(QDialog):
    """Diálogo principal de procesamiento 3D"""
    
    def __init__(self, camera_config, parent=None):
        super().__init__(parent)
        self.camera_config = camera_config
        self.processing_thread = None
        self.last_capture_info = None
        
        self.init_ui()
        self.load_last_capture()
        
    def init_ui(self):
        """Inicializar interfaz de usuario"""
        self.setWindowTitle("3D Processing - Model Generation")
        self.setModal(True)

        # Ajustar al tamaño de pantalla disponible
        screen = QApplication.primaryScreen()
        if screen:
            available = screen.availableGeometry()
            w = min(1000, available.width() - 40)
            h = min(700, available.height() - 40)
            self.resize(w, h)
        else:
            self.resize(1000, 700)

        layout = QVBoxLayout(self)
        layout.setSpacing(4)
        layout.setContentsMargins(6, 6, 6, 6)

        # Título
        title = QLabel("3D Processing and Model Generation")
        title.setFont(QFont("Arial", 13, QFont.Bold))
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet("color: #1976D2; margin: 4px;")
        layout.addWidget(title)
        
        # Splitter principal
        from PyQt5.QtWidgets import QSplitter
        main_splitter = QSplitter(Qt.Horizontal)
        layout.addWidget(main_splitter)
        
        # Panel izquierdo - Configuración
        config_panel = self.create_configuration_panel()
        main_splitter.addWidget(config_panel)
        
        # Panel derecho - Visualización
        self.results_widget = ResultsVisualizationWidget()
        main_splitter.addWidget(self.results_widget)
        
        # Configurar proporciones
        main_splitter.setSizes([350, 650])
        
        # Botones de acción
        buttons = self.create_buttons()
        layout.addLayout(buttons)
        
        self.apply_styles()
        
    def create_configuration_panel(self):
        """Crear panel de configuración"""
        panel = QFrame()
        panel.setFrameStyle(QFrame.StyledPanel)
        panel.setMaximumWidth(380)
        
        layout = QVBoxLayout(panel)
        
        # Selección de imágenes
        images_group = self.create_images_selection_group()
        layout.addWidget(images_group)
        
        # Configuración de algoritmo
        algorithm_group = self.create_algorithm_config_group()
        layout.addWidget(algorithm_group)
        
        # Configuración de exportación
        export_group = self.create_export_config_group()
        layout.addWidget(export_group)
        
        # Progreso
        progress_group = self.create_progress_group()
        layout.addWidget(progress_group)
        
        # Log de procesamiento
        log_group = self.create_log_group()
        layout.addWidget(log_group)
        
        layout.addStretch()
        
        return panel
    
    def create_images_selection_group(self):
        """Crear grupo de selección de imágenes"""
        group = QGroupBox("📁 Image Selection")
        layout = QVBoxLayout(group)

        # Información de última captura
        self.capture_info_label = QLabel("Loading information...")
        self.capture_info_label.setWordWrap(True)
        self.capture_info_label.setStyleSheet("""
            QLabel {
                background-color: #E8F5E8;
                padding: 8px;
                border-radius: 4px;
                border: 1px solid #4CAF50;
            }
        """)
        layout.addWidget(self.capture_info_label)

        # NUEVO: Botón para seleccionar carpeta de captura completa
        self.btn_select_capture_folder = QPushButton("📁 Select Capture Session")
        self.btn_select_capture_folder.setStyleSheet("""
            QPushButton {
                font-weight: bold;
                background-color: #2196F3;
                color: white;
                padding: 10px;
                border-radius: 5px;
            }
            QPushButton:hover {
                background-color: #1976D2;
            }
        """)
        self.btn_select_capture_folder.clicked.connect(self.select_capture_session)
        layout.addWidget(self.btn_select_capture_folder)

        # Rutas seleccionadas (se llenan automáticamente al seleccionar sesión)
        self.selected_left_path = None
        self.selected_right_path = None
        self.current_session_path = None

        # NUEVO: Botón para configurar filtro de cable
        separator2 = QLabel("─────────────────────────────")
        separator2.setAlignment(Qt.AlignCenter)
        separator2.setStyleSheet("color: #999999; font-size: 9px; margin: 5px;")
        layout.addWidget(separator2)

        self.btn_configure_cable_filter = QPushButton("🔧 Configure Cable Filter")
        self.btn_configure_cable_filter.setStyleSheet("""
            QPushButton {
                font-weight: bold;
                background-color: #FF9800;
                color: white;
                padding: 8px;
                border-radius: 5px;
                font-size: 10px;
            }
            QPushButton:hover {
                background-color: #F57C00;
            }
            QPushButton:disabled {
                background-color: #CCCCCC;
                color: #666666;
            }
        """)
        self.btn_configure_cable_filter.clicked.connect(self.open_cable_filter_config)
        self.btn_configure_cable_filter.setEnabled(False)  # Deshabilitado hasta seleccionar imágenes
        layout.addWidget(self.btn_configure_cable_filter)

        # Estado del filtro de cable
        self.cable_filter_configured = False
        self.cable_mask_left = None
        self.cable_mask_right = None
        self.cable_mask_left_rectified = None   # Máscaras rectificadas
        self.cable_mask_right_rectified = None
        self.wire_tracking_result = None  # Resultado del SmartWireTracker (paths en coordenadas rectificadas)

        self.filter_status_label = QLabel("⚠️ Filter not configured")
        self.filter_status_label.setStyleSheet("""
            QLabel {
                background-color: #FFF3E0;
                padding: 6px;
                border-radius: 3px;
                border: 1px solid #FF9800;
                color: #E65100;
                font-size: 9px;
            }
        """)
        layout.addWidget(self.filter_status_label)

        return group
    
    def create_algorithm_config_group(self):
        """Crear grupo de configuración de algoritmo"""
        group = QGroupBox("⚙️ Algorithm Configuration")
        layout = QGridLayout(group)
        
        # Algoritmo de matching
        layout.addWidget(QLabel("Matching algorithm:"), 0, 0)
        self.algorithm_combo = QComboBox()
        self.algorithm_combo.addItems(["SGBM (Recommended)", "BM (Fast)"])
        layout.addWidget(self.algorithm_combo, 0, 1)
        
        # Calidad de procesamiento
        layout.addWidget(QLabel("Quality:"), 1, 0)
        self.quality_combo = QComboBox()
        self.quality_combo.addItems(["High (Slow)", "Medium (Balanced)", "Fast"])
        self.quality_combo.setCurrentIndex(1)  # Media por defecto
        layout.addWidget(self.quality_combo, 1, 1)
        
        # Filtrado de ruido
        self.noise_filter_check = QCheckBox("Apply WLS noise filter")
        self.noise_filter_check.setChecked(True)
        layout.addWidget(self.noise_filter_check, 2, 0, 1, 2)
        
        return group
    
    def create_export_config_group(self):
        """Crear grupo de configuración de exportación"""
        group = QGroupBox("💾 Export Configuration")
        layout = QVBoxLayout(group)
        
        # Directorio de salida
        dir_layout = QHBoxLayout()
        dir_layout.addWidget(QLabel("Directory:"))
        
        self.output_dir_label = QLabel("data/results")
        self.output_dir_label.setStyleSheet("QLabel { border: 1px solid #CCC; padding: 4px; }")
        dir_layout.addWidget(self.output_dir_label)
        
        self.btn_select_output = QPushButton("📁")
        self.btn_select_output.setFixedSize(30, 30)
        self.btn_select_output.clicked.connect(self.select_output_directory)
        dir_layout.addWidget(self.btn_select_output)
        
        layout.addLayout(dir_layout)
        
        # Formatos de exportación
        layout.addWidget(QLabel("Point cloud formats:"))
        
        formats_layout = QGridLayout()
        
        self.format_ply_check = QCheckBox("PLY (Recommended)")
        self.format_ply_check.setChecked(True)
        formats_layout.addWidget(self.format_ply_check, 0, 0)
        
        self.format_xyz_check = QCheckBox("XYZ")
        formats_layout.addWidget(self.format_xyz_check, 0, 1)
        
        self.format_pcd_check = QCheckBox("PCD")
        formats_layout.addWidget(self.format_pcd_check, 1, 0)
        
        self.format_obj_check = QCheckBox("OBJ")
        formats_layout.addWidget(self.format_obj_check, 1, 1)
        
        layout.addLayout(formats_layout)
        
        return group
    
    def create_progress_group(self):
        """Crear grupo de progreso"""
        group = QGroupBox("📊 Processing Progress")
        layout = QVBoxLayout(group)
        
        # Barra de progreso
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        layout.addWidget(self.progress_bar)
        
        # Mensaje de estado
        self.progress_message = QLabel("Ready to process")
        self.progress_message.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.progress_message)
        
        return group
    
    def create_log_group(self):
        """Crear grupo de log"""
        group = QGroupBox("📝 Processing Log")
        layout = QVBoxLayout(group)
        
        self.log_text = QTextEdit()
        self.log_text.setMaximumHeight(70)
        self.log_text.setReadOnly(True)
        self.log_text.setStyleSheet("""
            QTextEdit {
                background-color: #FAFAFA;
                font-family: 'Courier New', monospace;
                font-size: 9px;
            }
        """)
        layout.addWidget(self.log_text)
        
        return group
    
    def create_buttons(self):
        """Crear botones de acción"""
        layout = QHBoxLayout()
        
        # Botón de inicio
        self.btn_start = QPushButton("🚀 Start Processing")
        self.btn_start.setFixedHeight(34)
        self.btn_start.setStyleSheet("""
            QPushButton {
                font-size: 14px;
                font-weight: bold;
                background-color: #2196F3;
                color: white;
                border: none;
                border-radius: 5px;
            }
            QPushButton:hover {
                background-color: #1976D2;
            }
            QPushButton:disabled {
                background-color: #CCCCCC;
                color: #666666;
            }
        """)
        self.btn_start.clicked.connect(self.start_processing)
        layout.addWidget(self.btn_start)
        
        # Botón de cancelar
        self.btn_cancel = QPushButton("⏹️ Cancel")
        self.btn_cancel.setFixedHeight(34)
        self.btn_cancel.clicked.connect(self.cancel_processing)
        self.btn_cancel.setEnabled(False)
        layout.addWidget(self.btn_cancel)
        
        layout.addStretch()
        
        # Botón de cerrar
        self.btn_close = QPushButton("✅ Close")
        self.btn_close.setFixedHeight(34)
        self.btn_close.clicked.connect(self.close)
        layout.addWidget(self.btn_close)
        
        return layout
    
    def apply_styles(self):
        """Aplicar estilos al diálogo"""
        self.setStyleSheet("""
            QGroupBox {
                font-weight: bold;
                border: 2px solid #CCCCCC;
                border-radius: 8px;
                margin: 5px;
                padding-top: 15px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 8px 0 8px;
                color: #333333;
            }
            QPushButton {
                padding: 6px 12px;
                border: none;
                border-radius: 4px;
                font-weight: bold;
            }
        """)
    
    def load_last_capture(self):
        """Cargar información de la última captura"""
        try:
            # Buscar último directorio de captura
            captures_dir = Path("data/captures")
            if not captures_dir.exists():
                self.capture_info_label.setText(
                    "⚠️ No captures available\n\n"
                    "To process images, you must first:\n"
                    "1️⃣ Capture a photo with 'Capture for 3D Model'\n"
                    "   or\n"
                    "2️⃣ Use the button below to manually select images"
                )
                self.capture_info_label.setStyleSheet("""
                    QLabel {
                        background-color: #FFF3E0;
                        padding: 10px;
                        border-radius: 4px;
                        border: 2px solid #FF9800;
                        color: #E65100;
                        font-weight: bold;
                    }
                """)
                self.btn_start.setEnabled(False)
                return

            # Buscar directorios de sesión
            session_dirs = [d for d in captures_dir.iterdir() if d.is_dir()]
            if not session_dirs:
                self.capture_info_label.setText(
                    "⚠️ No saved capture sessions\n\n"
                    "To process images, you must first:\n"
                    "1️⃣ Capture a photo with 'Capture for 3D Model'\n"
                    "   or\n"
                    "2️⃣ Use the button below to manually select images"
                )
                self.capture_info_label.setStyleSheet("""
                    QLabel {
                        background-color: #FFF3E0;
                        padding: 10px;
                        border-radius: 4px;
                        border: 2px solid #FF9800;
                        color: #E65100;
                        font-weight: bold;
                    }
                """)
                self.btn_start.setEnabled(False)
                return

            # Obtener la más reciente
            latest_session = max(session_dirs, key=lambda d: d.stat().st_mtime)

            # Buscar imágenes en la sesión
            left_images = list(latest_session.glob("left.jpg")) + list(latest_session.glob("left.png"))
            right_images = list(latest_session.glob("right.jpg")) + list(latest_session.glob("right.png"))

            if left_images and right_images:
                self.selected_left_path = str(left_images[0])
                self.selected_right_path = str(right_images[0])

                # Obtener información de timestamp
                capture_time = datetime.fromtimestamp(latest_session.stat().st_mtime)

                info_text = f"""✅ Last Capture Detected
📅 Date: {capture_time.strftime('%Y-%m-%d %H:%M:%S')}
📁 Session: {latest_session.name}
📷 Images: Left and Right available
🎯 Status: Ready to process

💡 You can select another session with the button above"""

                self.capture_info_label.setText(info_text)
                self.btn_start.setEnabled(True)
            else:
                self.capture_info_label.setText(
                    "⚠️ The last session is incomplete\n\n"
                    "Use the 'Select Capture Session' button to choose another session"
                )
                self.capture_info_label.setStyleSheet("""
                    QLabel {
                        background-color: #FFF3E0;
                        padding: 10px;
                        border-radius: 4px;
                        border: 2px solid #FF9800;
                        color: #E65100;
                    }
                """)
                self.btn_start.setEnabled(False)

        except Exception as e:
            logger.error(f"Error cargando última captura: {e}")
            self.capture_info_label.setText(f"❌ Error: {e}")
            self.btn_start.setEnabled(False)
    
    def select_capture_session(self):
        """Seleccionar una sesión de captura completa"""
        try:
            # Buscar directorio de capturas
            captures_dir = Path("data/captures")
            if not captures_dir.exists():
                QMessageBox.warning(
                    self, "No Captures",
                    "Capture directory not found.\n\n"
                    "You must take at least one photo with the 'Capture for 3D Model' button "
                    "before you can process images."
                )
                return

            # Buscar directorios de sesión
            session_dirs = sorted([d for d in captures_dir.iterdir() if d.is_dir()],
                                 key=lambda d: d.stat().st_mtime, reverse=True)

            if not session_dirs:
                QMessageBox.warning(
                    self, "No Sessions",
                    "No saved capture sessions found.\n\n"
                    "You must take at least one photo with the 'Capture for 3D Model' button "
                    "before you can process images."
                )
                return

            # Crear diálogo de selección con preview
            dialog = QDialog(self)
            dialog.setWindowTitle("Select Capture Session")
            dialog.setModal(True)
            dialog.resize(800, 450)

            layout = QVBoxLayout(dialog)

            # Título
            title = QLabel("Select a capture session to process")
            title.setFont(QFont("Arial", 12, QFont.Bold))
            title.setAlignment(Qt.AlignCenter)
            layout.addWidget(title)

            # --- Layout horizontal: Lista | Preview ---
            content_layout = QHBoxLayout()

            # === Lado izquierdo: Lista de sesiones ===
            list_widget = QListWidget()
            list_widget.setFont(QFont("Courier New", 10))
            list_widget.setMinimumWidth(320)

            for session_dir in session_dirs:
                left_img = session_dir / "left.jpg"
                if not left_img.exists(): left_img = session_dir / "left.png"
                right_img = session_dir / "right.jpg"
                if not right_img.exists(): right_img = session_dir / "right.png"

                capture_time = datetime.fromtimestamp(session_dir.stat().st_mtime)
                date_str = capture_time.strftime('%Y-%m-%d %H:%M:%S')

                if left_img.exists() and right_img.exists():
                    status_icon = "+"
                    status_text = "Complete"
                else:
                    status_icon = "!"
                    status_text = "Incomplete"

                item_text = f"[{status_icon}] {session_dir.name}\n    {date_str} | {status_text}"
                item = QListWidgetItem(item_text)
                item.setData(Qt.UserRole, session_dir)

                if not (left_img.exists() and right_img.exists()):
                    item.setFlags(item.flags() & ~Qt.ItemIsEnabled)

                list_widget.addItem(item)

            content_layout.addWidget(list_widget, stretch=1)

            # === Lado derecho: Preview panel ===
            preview_frame = QFrame()
            preview_frame.setFrameShape(QFrame.StyledPanel)
            preview_frame.setMinimumWidth(280)
            preview_frame.setStyleSheet("QFrame { background-color: #2b2b2b; border-radius: 4px; }")
            preview_layout = QVBoxLayout(preview_frame)

            preview_title = QLabel("Preview")
            preview_title.setFont(QFont("Arial", 10, QFont.Bold))
            preview_title.setAlignment(Qt.AlignCenter)
            preview_title.setStyleSheet("color: #cccccc; padding: 4px;")
            preview_layout.addWidget(preview_title)

            left_preview_label = QLabel("Left")
            left_preview_label.setAlignment(Qt.AlignCenter)
            left_preview_label.setStyleSheet("color: #888888;")
            left_preview_label.setFixedHeight(180)
            preview_layout.addWidget(left_preview_label)

            right_preview_label = QLabel("Right")
            right_preview_label.setAlignment(Qt.AlignCenter)
            right_preview_label.setStyleSheet("color: #888888;")
            right_preview_label.setFixedHeight(180)
            preview_layout.addWidget(right_preview_label)

            preview_layout.addStretch()
            content_layout.addWidget(preview_frame, stretch=0)

            layout.addLayout(content_layout)

            # Callback: actualizar preview al seleccionar un item
            def _update_preview(current_item, _previous_item):
                if current_item is None:
                    left_preview_label.setText("Left")
                    right_preview_label.setText("Right")
                    return

                session_path = current_item.data(Qt.UserRole)
                if session_path is None:
                    return

                for img_base, label in [("left", left_preview_label),
                                        ("right", right_preview_label)]:
                    img_path = session_path / f"{img_base}.jpg"
                    if not img_path.exists():
                        img_path = session_path / f"{img_base}.png"
                        
                    if img_path.exists():
                        pixmap = QPixmap(str(img_path))
                        if not pixmap.isNull():
                            scaled = pixmap.scaled(
                                label.width() - 4, label.height() - 4,
                                Qt.KeepAspectRatio, Qt.SmoothTransformation
                            )
                            label.setPixmap(scaled)
                        else:
                            label.setText(f"Cannot load {img_path.name}")
                    else:
                        label.setText(f"No {img_base}.jpg/png")

            list_widget.currentItemChanged.connect(_update_preview)

            # Seleccionar el primer item para mostrar preview inicial
            if list_widget.count() > 0:
                list_widget.setCurrentRow(0)

            # Información adicional
            info_label = QLabel(f"Total sessions: {len(session_dirs)}")
            info_label.setStyleSheet("color: #666666; font-style: italic; padding: 5px;")
            layout.addWidget(info_label)

            # Botones
            buttons_layout = QHBoxLayout()

            btn_ok = QPushButton("Select")
            btn_ok.setDefault(True)
            btn_ok.clicked.connect(dialog.accept)
            buttons_layout.addWidget(btn_ok)

            btn_cancel = QPushButton("Cancel")
            btn_cancel.clicked.connect(dialog.reject)
            buttons_layout.addWidget(btn_cancel)

            layout.addLayout(buttons_layout)

            # Ejecutar diálogo
            if dialog.exec_() == QDialog.Accepted:
                selected_items = list_widget.selectedItems()
                if selected_items:
                    selected_session = selected_items[0].data(Qt.UserRole)

                    # Cargar imágenes de la sesión seleccionada
                    l_path = selected_session / "left.jpg"
                    if not l_path.exists(): l_path = selected_session / "left.png"
                    r_path = selected_session / "right.jpg"
                    if not r_path.exists(): r_path = selected_session / "right.png"
                    self.selected_left_path = str(l_path)
                    self.selected_right_path = str(r_path)
                    self.current_session_path = selected_session

                    # Actualizar display
                    capture_time = datetime.fromtimestamp(selected_session.stat().st_mtime)

                    info_text = f"""✅ Session Selected
📁 {selected_session.name}
📅 Date: {capture_time.strftime('%Y-%m-%d %H:%M:%S')}
📷 Images: Left and Right loaded
🎯 Status: Ready to process"""

                    self.capture_info_label.setText(info_text)

                    # Habilitar botón de configurar filtro
                    self.btn_configure_cable_filter.setEnabled(True)
                    self.capture_info_label.setStyleSheet("""
                        QLabel {
                            background-color: #E8F5E8;
                            padding: 8px;
                            border-radius: 4px;
                            border: 1px solid #4CAF50;
                        }
                    """)
                    self.btn_start.setEnabled(True)

                    self.add_log_message(f"Session loaded: {selected_session.name}")
                else:
                    QMessageBox.information(self, "No Selection", "You did not select any session.")

        except Exception as e:
            logger.error(f"Error selecting capture session: {e}")
            QMessageBox.critical(self, "Error", f"Error selecting session:\n{e}")

    def update_manual_selection_display(self):
        """Actualizar display de selección manual"""
        if self.selected_left_path and self.selected_right_path:
            left_name = Path(self.selected_left_path).name
            right_name = Path(self.selected_right_path).name

            info_text = f"""📁 Manual Selection
📷 Left: {left_name}
📷 Right: {right_name}
🎯 Status: Ready to process"""

            self.capture_info_label.setText(info_text)
            self.capture_info_label.setStyleSheet("""
                QLabel {
                    background-color: #E3F2FD;
                    padding: 8px;
                    border-radius: 4px;
                    border: 1px solid #2196F3;
                }
            """)
            self.btn_start.setEnabled(True)
    
    def select_output_directory(self):
        """Seleccionar directorio de salida"""
        dir_path = QFileDialog.getExistingDirectory(
            self, "Select Output Directory", "data/results"
        )
        if dir_path:
            self.output_dir_label.setText(dir_path)
    
    def get_selected_export_formats(self):
        """Obtener formatos de exportación seleccionados"""
        formats = []
        if self.format_ply_check.isChecked():
            formats.append('ply')
        if self.format_xyz_check.isChecked():
            formats.append('xyz')
        if self.format_pcd_check.isChecked():
            formats.append('pcd')
        if self.format_obj_check.isChecked():
            formats.append('obj')
        return formats if formats else ['ply']  # PLY por defecto
    
    def start_processing(self):
        """Iniciar procesamiento 3D"""
        try:
            # Validar selección de imágenes
            if not (self.selected_left_path and self.selected_right_path):
                QMessageBox.warning(self, "Warning", 
                                  "You must select both images (left and right)")
                return
            
            if not (Path(self.selected_left_path).exists() and Path(self.selected_right_path).exists()):
                QMessageBox.critical(self, "Error", "One or both images do not exist")
                return
            
            # Preparar directorio de salida
            output_dir = Path(self.output_dir_label.text())
            output_dir.mkdir(parents=True, exist_ok=True)
            
            # Preparar parámetros de procesamiento
            algorithm = "SGBM" if "SGBM" in self.algorithm_combo.currentText() else "BM"
            
            processing_params = {
                'left_image': self.selected_left_path,
                'right_image': self.selected_right_path,
                'algorithm': algorithm,
                'quality': self.quality_combo.currentText(),
                'use_noise_filter': self.noise_filter_check.isChecked(),
                'export_point_cloud': True,
                'export_formats': self.get_selected_export_formats(),
                'output_dir': output_dir
            }
            
            self.add_log_message("Starting 3D processing...")
            
            # Configurar UI
            self.btn_start.setEnabled(False)
            self.btn_cancel.setEnabled(True)
            self.progress_bar.setValue(0)

            # Preparar máscaras y paths de cable si están configurados
            cable_masks = None
            wire_paths = None

            if self.cable_filter_configured and self.cable_mask_left is not None and self.cable_mask_right is not None:
                cable_masks = (self.cable_mask_left, self.cable_mask_right)

                # Usar paths geométricos si ya fueron calculados
                if self.wire_tracking_result is not None and self.wire_tracking_result.get('success'):
                    wire_paths = {
                        'left': self.wire_tracking_result['left']['path'],
                        'right': self.wire_tracking_result['right']['path']
                    }
                    self.add_log_message("✓ Using pre-calculated geometric paths", "INFO")
                else:
                    self.add_log_message("⚠️ Wire tracking unavailable, using masks only", "WARNING")
            else:
                self.add_log_message("⚠️ No cable mask - processing full image", "WARNING")

            # Crear y iniciar hilo de procesamiento
            self.processing_thread = ProcessingWorkerThread(
                self.camera_config,
                processing_params,
                cable_masks=cable_masks,
                wire_paths=wire_paths  # Pasar paths ya calculados
            )
            
            # Conectar señales
            self.processing_thread.progress_update.connect(self.update_progress)
            self.processing_thread.processing_complete.connect(self.on_processing_complete)
            self.processing_thread.log_message.connect(self.add_log_message)
            self.processing_thread.intermediate_result.connect(self.on_intermediate_result)
            
            # Iniciar procesamiento
            self.processing_thread.start()
            
        except Exception as e:
            self.add_log_message(f"Error starting processing: {e}", "ERROR")
            QMessageBox.critical(self, "Error", f"Error starting processing:\n{e}")
    
    def cancel_processing(self):
        """Cancelar procesamiento en curso"""
        if self.processing_thread and self.processing_thread.isRunning():
            self.add_log_message("Canceling processing...", "WARNING")
            self.processing_thread.stop()
            
            if not self.processing_thread.wait(5000):
                self.processing_thread.terminate()
                self.processing_thread.wait(2000)
            
            self.reset_ui_after_processing()
    
    def update_progress(self, progress, message):
        """Actualizar progreso de procesamiento"""
        self.progress_bar.setValue(progress)
        self.progress_message.setText(message)
        QApplication.processEvents()
    
    def on_intermediate_result(self, result_type, data):
        """Manejar resultados intermedios"""
        try:
            if result_type == "disparity":
                self.results_widget.update_disparity(data)
            elif result_type == "depth":
                self.results_widget.update_depth(data)
            elif result_type == "confidence":
                self.results_widget.update_confidence(data)
        except Exception as e:
            logger.error(f"Error mostrando resultado intermedio {result_type}: {e}")
    
    def on_processing_complete(self, success, result):
        """Callback cuando termina el procesamiento"""
        try:
            if success:
                self.add_log_message("3D processing completed successfully!", "INFO")
                
                # Actualizar estadísticas
                self.results_widget.update_statistics(result)
                
                # Mostrar mensaje de éxito
                export_files = result.get('export_files', [])
                files_info = "\n".join([f"• {Path(f).name}" for f in export_files])
                
                QMessageBox.information(
                    self,
                    "Processing Successful",
                    f"The 3D model was generated correctly.\n\n"
                    f"Time: {result.get('processing_time_seconds', 0):.1f}s\n"
                    f"3D Points: {result.get('point_cloud', {}).get('num_points', 0):,}\n\n"
                    f"Generated files:\n{files_info}"
                )
                
            else:
                error_msg = result.get('error', 'Unknown error')
                self.add_log_message(f"Processing failed: {error_msg}", "ERROR")
                
                QMessageBox.critical(
                    self,
                    "Processing Error",
                    f"3D processing failed:\n\n{error_msg}"
                )
                
        except Exception as e:
            logger.error(f"Error manejando resultado: {e}")
        
        finally:
            self.reset_ui_after_processing()
    
    def reset_ui_after_processing(self):
        """Restaurar UI después del procesamiento"""
        self.btn_start.setEnabled(True)
        self.btn_cancel.setEnabled(False)
        self.progress_message.setText("Processing completed")
    
    def add_log_message(self, message, level="INFO"):
        """Agregar mensaje al log"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        formatted_message = f"[{timestamp}] {level}: {message}"
        
        self.log_text.append(formatted_message)
        self.log_text.verticalScrollBar().setValue(
            self.log_text.verticalScrollBar().maximum()
        )
        
        # También loggear al sistema
        if level == "ERROR":
            logger.error(message)
        elif level == "WARNING":
            logger.warning(message)
        else:
            logger.info(message)
    
    def open_cable_filter_config(self):
        """Abrir GUI de configuración de filtro de cable"""
        try:
            # Cargar imágenes de la sesión
            left_img = cv2.imread(self.selected_left_path)
            right_img = cv2.imread(self.selected_right_path)

            if left_img is None or right_img is None:
                QMessageBox.warning(self, "Error", "No se pudieron cargar las imágenes de la sesión")
                return

            # Importar y abrir GUI de configuración con capacidad de switch
            from edge_detection_tuner import open_cable_detection_tuner_with_switch

            result = open_cable_detection_tuner_with_switch(
                left_img, right_img,
                self.selected_left_path, self.selected_right_path
            )

            if result is not None:
                self.cable_mask_left, self.cable_mask_right = result
                self.cable_filter_configured = True

                # === DETECTAR ENDPOINTS Y ABRIR VISUALIZACION ANIMADA ===
                self.add_log_message("Detecting cable endpoints...", "INFO")

                try:
                    from processing.endpoint_detector import detect_wire_endpoints

                    start_left, end_left = detect_wire_endpoints(self.cable_mask_left)
                    start_right, end_right = detect_wire_endpoints(self.cable_mask_right)

                    self.add_log_message(f"  LEFT endpoints: {start_left} -> {end_left}", "INFO")
                    self.add_log_message(f"  RIGHT endpoints: {start_right} -> {end_right}", "INFO")

                    # Abrir dialogo animado que ejecuta el tracker en tiempo real
                    vis_dialog = WireTrackingVisualizationDialog(
                        left_img, right_img,
                        self.cable_mask_left, self.cable_mask_right,
                        start_left, end_left,
                        start_right, end_right,
                        self
                    )
                    vis_dialog.exec_()

                    # Obtener resultados del tracking
                    tracking_results = vis_dialog.get_results()

                    if tracking_results and tracking_results['success']:
                        self.wire_tracking_result = tracking_results

                        self.add_log_message(f"Wire tracking successful:", "INFO")
                        self.add_log_message(f"  LEFT: {len(tracking_results['left']['path'])} puntos, "
                                      f"Cob: {tracking_results['left']['coverage']*100:.1f}%", "INFO")
                        self.add_log_message(f"  RIGHT: {len(tracking_results['right']['path'])} puntos, "
                                      f"Cob: {tracking_results['right']['coverage']*100:.1f}%", "INFO")

                        self.filter_status_label.setText("Filter configured + Wire tracking OK")
                        self.filter_status_label.setStyleSheet("""
                            QLabel {
                                background-color: #E8F5E9;
                                padding: 6px;
                                border-radius: 3px;
                                border: 1px solid #4CAF50;
                                color: #2E7D32;
                                font-size: 9px;
                            }
                        """)
                    else:
                        self.add_log_message("Wire tracking incomplete", "WARNING")
                        self.wire_tracking_result = None

                        self.filter_status_label.setText("Filter OK, Wire tracking incomplete")
                        self.filter_status_label.setStyleSheet("""
                            QLabel {
                                background-color: #FFF3E0;
                                padding: 6px;
                                border-radius: 3px;
                                border: 1px solid #FF9800;
                                color: #E65100;
                                font-size: 9px;
                            }
                        """)

                except Exception as e:
                    logger.error(f"Error en wire tracking: {e}")
                    self.add_log_message(f"Error en wire tracking: {e}", "ERROR")
                    self.wire_tracking_result = None

                    self.filter_status_label.setText("Filter configured (no wire tracking)")
                    self.filter_status_label.setStyleSheet("""
                        QLabel {
                            background-color: #E8F5E9;
                            padding: 6px;
                            border-radius: 3px;
                            border: 1px solid #4CAF50;
                            color: #2E7D32;
                            font-size: 9px;
                        }
                    """)

                    QMessageBox.information(self, "Notice",
                        f"Cable filter configured.\n\n"
                        f"Wire tracking failed ({e}), but masks are available.")

            else:
                QMessageBox.information(self, "Cancelled",
                    "Filter configuration canceled.")

        except Exception as e:
            logger.error(f"Error opening filter configuration: {e}")
            QMessageBox.critical(self, "Error",
                f"Error opening filter configuration:\n{e}")

    def closeEvent(self, event):
        """Manejar cierre del diálogo"""
        if self.processing_thread and self.processing_thread.isRunning():
            msg = QMessageBox.question(
                self,
                "Processing in Progress",
                "Processing is in progress. Do you want to cancel and close?",
                QMessageBox.Yes | QMessageBox.No
            )

            if msg == QMessageBox.Yes:
                self.cancel_processing()
                event.accept()
            else:
                event.ignore()
        else:
            event.accept()

if __name__ == "__main__":
    # Test del diálogo de procesamiento
    import sys
    from PyQt5.QtWidgets import QApplication
    from config.camera_config import CameraConfig
    
    app = QApplication(sys.argv)
    
    try:
        config = CameraConfig()
        # Simular calibración
        config.calibration_data['is_calibrated'] = True
        
        dialog = ProcessingDialog(config)
        dialog.exec_()
        
    except Exception as e:
        QMessageBox.critical(None, "Error", f"Error iniciando diálogo:\n{e}")
    
    app.quit()