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
            self.log_message.emit("Iniciando procesamiento 3D...", "INFO")

            # Inicializar procesador
            processor = StereoProcessor(self.camera_config)

            # Cargar imágenes
            self.progress_update.emit(5, "Cargando imágenes...")
            left_img = cv2.imread(self.processing_params['left_image'])
            right_img = cv2.imread(self.processing_params['right_image'])

            if left_img is None or right_img is None:
                raise RuntimeError("No se pudieron cargar las imágenes")

            self.log_message.emit(f"Imágenes cargadas: {left_img.shape}", "INFO")

            # === DECIDIR QUÉ MÉTODO USAR ===
            if self.wire_paths is not None:
                # ============================================
                # MÉTODO GEOMÉTRICO: Usar paths YA CALCULADOS
                # NO vuelve a correr SmartWireTracker
                # ============================================
                self.log_message.emit("🎯 Usando PATHS GEOMÉTRICOS ya calculados", "INFO")
                self.log_message.emit(f"   Path izquierdo: {len(self.wire_paths['left'])} puntos", "INFO")
                self.log_message.emit(f"   Path derecho: {len(self.wire_paths['right'])} puntos", "INFO")

                # Rectificar imágenes primero
                self.progress_update.emit(10, "Rectificando imágenes...")
                left_rect, right_rect = processor.rectify_images(left_img, right_img)

                # Calcular disparidad DIRECTAMENTE desde los paths
                self.progress_update.emit(30, "Calculando disparidad desde paths geométricos...")

                image_shape = left_rect.shape[:2]
                disparity_result = processor.compute_disparity_from_wire_paths(
                    self.wire_paths['left'],
                    self.wire_paths['right'],
                    image_shape,
                    save_debug=True
                )

                if not disparity_result['success']:
                    raise RuntimeError("No se pudo calcular disparidad desde paths geométricos")

                # Generar nube de puntos DIRECTAMENTE desde los matches
                # (NO desde disparity_map que pierde puntos por colisión de píxeles)
                self.progress_update.emit(70, "Generando nube de puntos 3D desde matches...")

                point_cloud_result = processor.generate_point_cloud_from_matches(
                    disparity_result['matches'],
                    disparity_result['disparities'],
                    left_rect
                )

                self.log_message.emit(f"☁️ Nube generada: {point_cloud_result['num_points']} puntos 3D", "INFO")

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
                self.log_message.emit("⚠️ Sin paths geométricos, usando SGBM + máscara", "WARNING")

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
                self.log_message.emit("⚠️ Sin máscara de cable - usando SGBM tradicional", "WARNING")

                result = processor.process_stereo_pair(
                    left_img, right_img,
                    algorithm=self.processing_params['algorithm'],
                    progress_callback=self.progress_callback,
                    save_debug_images=True,
                    cable_mask=None
                )

            if not result['success']:
                raise RuntimeError(f"Error en procesamiento: {result.get('error')}")
            
            # Emitir resultados intermedios
            self.intermediate_result.emit("disparity", result['disparity']['disparity_map'])
            self.intermediate_result.emit("depth", result['depth']['depth_map'])
            self.intermediate_result.emit("confidence", result['disparity']['confidence_map'])
            
            # Exportar nube de puntos si se solicita
            if self.processing_params.get('export_point_cloud', True):
                self.progress_update.emit(90, "Exportando nube de puntos...")
                
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
                        self.log_message.emit(f"Nube exportada: {output_file}", "INFO")
                
                result['export_files'] = export_results
            
            self.progress_update.emit(100, "Procesamiento completado")
            self.processing_complete.emit(True, result)
            
        except Exception as e:
            self.log_message.emit(f"Error durante procesamiento: {e}", "ERROR")
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
        self.disparity_tab = self.create_image_tab("Mapa de Disparidad")
        self.tabs.addTab(self.disparity_tab, "Disparidad")
        
        # Tab de profundidad
        self.depth_tab = self.create_image_tab("Mapa de Profundidad")
        self.tabs.addTab(self.depth_tab, "Profundidad")
        
        # Tab de confianza
        self.confidence_tab = self.create_image_tab("Mapa de Confianza")
        self.tabs.addTab(self.confidence_tab, "Confianza")
        
        # Tab de estadísticas
        self.stats_tab = self.create_stats_tab()
        self.tabs.addTab(self.stats_tab, "Estadísticas")
        
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
        image_label.setText("Sin datos")
        
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
        title = QLabel("Estadísticas de Procesamiento")
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
                self.depth_tab.image_label.setText("Sin datos de profundidad válidos")
                
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
            stats_text = "=== ESTADÍSTICAS DE PROCESAMIENTO 3D ===\n\n"
            
            # Información general
            stats_text += f"Tiempo de procesamiento: {processing_result.get('processing_time_seconds', 0):.2f} segundos\n"
            stats_text += f"Algoritmo usado: {processing_result.get('algorithm_used', 'N/A')}\n"
            stats_text += f"Forma de entrada: {processing_result.get('input_shape', 'N/A')}\n\n"
            
            # Estadísticas de disparidad
            if 'disparity' in processing_result:
                disp_data = processing_result['disparity']
                stats_text += "--- DISPARIDAD ---\n"
                stats_text += f"Disparidad mínima: {disp_data.get('min_disparity', 0):.2f} píxeles\n"
                stats_text += f"Disparidad máxima: {disp_data.get('max_disparity', 0):.2f} píxeles\n"
                stats_text += f"Disparidad promedio: {disp_data.get('mean_disparity', 0):.2f} píxeles\n"
                stats_text += f"Píxeles válidos: {disp_data.get('valid_pixels', 0):,}\n"
                stats_text += f"Filtrado aplicado: {'Sí' if disp_data.get('filtered', False) else 'No'}\n\n"
            
            # Estadísticas de profundidad
            if 'depth' in processing_result:
                depth_data = processing_result['depth']
                stats_text += "--- PROFUNDIDAD ---\n"
                stats_text += f"Profundidad mínima: {depth_data.get('min_depth', 0):.3f} metros\n"
                stats_text += f"Profundidad máxima: {depth_data.get('max_depth', 0):.3f} metros\n"
                stats_text += f"Profundidad promedio: {depth_data.get('mean_depth', 0):.3f} metros\n"
                stats_text += f"Baseline: {depth_data.get('baseline_meters', 0)*1000:.1f} mm\n"
                stats_text += f"Focal length: {depth_data.get('focal_length_pixels', 0):.1f} píxeles\n\n"
            
            # Estadísticas de nube de puntos
            if 'point_cloud' in processing_result:
                pc_data = processing_result['point_cloud']
                stats_text += "--- NUBE DE PUNTOS ---\n"
                stats_text += f"Número de puntos: {pc_data.get('num_points', 0):,}\n"
                stats_text += f"Densidad: {pc_data.get('density', 0):.4f}\n"
                
                bounds = pc_data.get('bounds', {})
                stats_text += f"Límites X: {bounds.get('x_min', 0):.3f} a {bounds.get('x_max', 0):.3f} m\n"
                stats_text += f"Límites Y: {bounds.get('y_min', 0):.3f} a {bounds.get('y_max', 0):.3f} m\n"
                stats_text += f"Límites Z: {bounds.get('z_min', 0):.3f} a {bounds.get('z_max', 0):.3f} m\n\n"
            
            # Métricas de calidad
            if 'quality_metrics' in processing_result:
                quality = processing_result['quality_metrics']
                stats_text += "--- CALIDAD ---\n"
                stats_text += f"Ratio píxeles válidos: {quality.get('valid_pixel_ratio', 0):.1%}\n"
                stats_text += f"Confianza promedio: {quality.get('mean_confidence', 0):.3f}\n"
                stats_text += f"Densidad de puntos: {quality.get('point_density', 0):.4f}\n\n"
            
            # Archivos exportados
            if 'export_files' in processing_result:
                stats_text += "--- ARCHIVOS EXPORTADOS ---\n"
                for file_path in processing_result['export_files']:
                    file_size = Path(file_path).stat().st_size / (1024 * 1024)  # MB
                    stats_text += f"• {Path(file_path).name} ({file_size:.1f} MB)\n"
            
            self.stats_text.setText(stats_text)
            
        except Exception as e:
            logger.error(f"Error actualizando estadísticas: {e}")
            self.stats_text.setText(f"Error cargando estadísticas: {e}")

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
        tracker = SmartWireTracker(self.mask, self.start_pt, self.end_pt)
        result = tracker.track_wire(
            max_iterations=10000,
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
        self.setWindowTitle("Wire Tracking - Reconstruccion en vivo")
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
        self.status_label = QLabel("Preparando...")
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
        self.left_header = QLabel("Izquierda - esperando...")
        self.left_header.setFont(QFont("Arial", 9, QFont.Bold))
        self.left_header.setAlignment(Qt.AlignCenter)
        self.left_header.setStyleSheet("color: #2196F3;")
        left_frame_layout.addWidget(self.left_header)
        self.left_image_label = QLabel()
        self.left_image_label.setAlignment(Qt.AlignCenter)
        self.left_image_label.setPixmap(self._cv2_to_pixmap(self.left_img))
        left_frame_layout.addWidget(self.left_image_label)
        images_layout.addWidget(left_frame)

        # Derecha
        right_frame = QFrame()
        right_frame_layout = QVBoxLayout(right_frame)
        right_frame_layout.setContentsMargins(2, 2, 2, 2)
        self.right_header = QLabel("Derecha - esperando...")
        self.right_header.setFont(QFont("Arial", 9, QFont.Bold))
        self.right_header.setAlignment(Qt.AlignCenter)
        self.right_header.setStyleSheet("color: #FF9800;")
        right_frame_layout.addWidget(self.right_header)
        self.right_image_label = QLabel()
        self.right_image_label.setAlignment(Qt.AlignCenter)
        self.right_image_label.setPixmap(self._cv2_to_pixmap(self.right_img))
        right_frame_layout.addWidget(self.right_image_label)
        images_layout.addWidget(right_frame)

        layout.addLayout(images_layout)

        # Boton cerrar (deshabilitado hasta que termine)
        self.btn_close = QPushButton("Procesando...")
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
        self.status_label.setText("Procesando imagen izquierda...")
        self.left_header.setText("Izquierda - procesando...")

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
        self.left_header.setText(f"Izquierda - {len(path)} pts (iter {iteration})")

    def _on_left_finished(self, result):
        self.result_left = result
        self.current_path_left = result['path']
        # Dibujar resultado final
        vis = self._draw_wire_on_image(self.left_img, result['path'], "LEFT")
        self.left_image_label.setPixmap(self._cv2_to_pixmap(vis))
        self.left_header.setText(
            f"Izquierda - {len(result['path'])} pts | Cob: {result['coverage']*100:.1f}%"
        )
        # Iniciar derecha
        QTimer.singleShot(500, self._start_right_tracking)

    def _start_right_tracking(self):
        self.phase = "right"
        self.status_label.setText("Procesando imagen derecha...")
        self.right_header.setText("Derecha - procesando...")

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
        self.right_header.setText(f"Derecha - {len(path)} pts (iter {iteration})")

    def _on_right_finished(self, result):
        self.result_right = result
        self.current_path_right = result['path']
        vis = self._draw_wire_on_image(self.right_img, result['path'], "RIGHT")
        self.right_image_label.setPixmap(self._cv2_to_pixmap(vis))
        self.right_header.setText(
            f"Derecha - {len(result['path'])} pts | Cob: {result['coverage']*100:.1f}%"
        )
        self.phase = "done"
        self.status_label.setText("Reconstruccion completada")
        self.status_label.setStyleSheet("color: #2E7D32; font-weight: bold;")
        self.btn_close.setText("Cerrar")
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
        if len(path) < 2:
            return vis
        color = (0, 200, 255) if side == "LEFT" else (0, 165, 255)
        for i in range(len(path) - 1):
            pt1 = (int(path[i][0]), int(path[i][1]))
            pt2 = (int(path[i+1][0]), int(path[i+1][1]))
            cv2.line(vis, pt1, pt2, color, 2, cv2.LINE_AA)
        start = (int(path[0][0]), int(path[0][1]))
        end = (int(path[-1][0]), int(path[-1][1]))
        cv2.circle(vis, start, 6, (0, 255, 0), -1)
        cv2.circle(vis, end, 6, (0, 0, 255), -1)
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
        self.setWindowTitle("Procesamiento 3D - Generación de Modelo")
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
        title = QLabel("Procesamiento 3D y Generacion de Modelo")
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
        group = QGroupBox("📁 Selección de Imágenes")
        layout = QVBoxLayout(group)

        # Información de última captura
        self.capture_info_label = QLabel("Cargando información...")
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
        self.btn_select_capture_folder = QPushButton("📁 Seleccionar Sesión de Captura")
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

        self.btn_configure_cable_filter = QPushButton("🔧 Configurar Filtro de Cable")
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

        self.filter_status_label = QLabel("⚠️ Filtro no configurado")
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
        group = QGroupBox("⚙️ Configuración de Algoritmo")
        layout = QGridLayout(group)
        
        # Algoritmo de matching
        layout.addWidget(QLabel("Algoritmo de matching:"), 0, 0)
        self.algorithm_combo = QComboBox()
        self.algorithm_combo.addItems(["SGBM (Recomendado)", "BM (Rápido)"])
        layout.addWidget(self.algorithm_combo, 0, 1)
        
        # Calidad de procesamiento
        layout.addWidget(QLabel("Calidad:"), 1, 0)
        self.quality_combo = QComboBox()
        self.quality_combo.addItems(["Alta (Lento)", "Media (Balanceado)", "Rápida"])
        self.quality_combo.setCurrentIndex(1)  # Media por defecto
        layout.addWidget(self.quality_combo, 1, 1)
        
        # Filtrado de ruido
        self.noise_filter_check = QCheckBox("Aplicar filtro de ruido WLS")
        self.noise_filter_check.setChecked(True)
        layout.addWidget(self.noise_filter_check, 2, 0, 1, 2)
        
        return group
    
    def create_export_config_group(self):
        """Crear grupo de configuración de exportación"""
        group = QGroupBox("💾 Configuración de Exportación")
        layout = QVBoxLayout(group)
        
        # Directorio de salida
        dir_layout = QHBoxLayout()
        dir_layout.addWidget(QLabel("Directorio:"))
        
        self.output_dir_label = QLabel("data/results")
        self.output_dir_label.setStyleSheet("QLabel { border: 1px solid #CCC; padding: 4px; }")
        dir_layout.addWidget(self.output_dir_label)
        
        self.btn_select_output = QPushButton("📁")
        self.btn_select_output.setFixedSize(30, 30)
        self.btn_select_output.clicked.connect(self.select_output_directory)
        dir_layout.addWidget(self.btn_select_output)
        
        layout.addLayout(dir_layout)
        
        # Formatos de exportación
        layout.addWidget(QLabel("Formatos de nube de puntos:"))
        
        formats_layout = QGridLayout()
        
        self.format_ply_check = QCheckBox("PLY (Recomendado)")
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
        group = QGroupBox("📊 Progreso de Procesamiento")
        layout = QVBoxLayout(group)
        
        # Barra de progreso
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        layout.addWidget(self.progress_bar)
        
        # Mensaje de estado
        self.progress_message = QLabel("Listo para procesar")
        self.progress_message.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.progress_message)
        
        return group
    
    def create_log_group(self):
        """Crear grupo de log"""
        group = QGroupBox("📝 Log de Procesamiento")
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
        self.btn_start = QPushButton("🚀 Iniciar Procesamiento")
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
        self.btn_cancel = QPushButton("⏹️ Cancelar")
        self.btn_cancel.setFixedHeight(34)
        self.btn_cancel.clicked.connect(self.cancel_processing)
        self.btn_cancel.setEnabled(False)
        layout.addWidget(self.btn_cancel)
        
        layout.addStretch()
        
        # Botón de cerrar
        self.btn_close = QPushButton("✅ Cerrar")
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
                    "⚠️ No hay capturas disponibles\n\n"
                    "Para procesar imágenes, primero debes:\n"
                    "1️⃣ Capturar una foto con 'Capturar para Modelo 3D'\n"
                    "   o\n"
                    "2️⃣ Usar el botón de abajo para seleccionar imágenes manualmente"
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
                    "⚠️ No hay sesiones de captura guardadas\n\n"
                    "Para procesar imágenes, primero debes:\n"
                    "1️⃣ Capturar una foto con 'Capturar para Modelo 3D'\n"
                    "   o\n"
                    "2️⃣ Usar el botón de abajo para seleccionar imágenes manualmente"
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
            left_images = list(latest_session.glob("left.jpg"))
            right_images = list(latest_session.glob("right.jpg"))

            if left_images and right_images:
                self.selected_left_path = str(left_images[0])
                self.selected_right_path = str(right_images[0])

                # Obtener información de timestamp
                capture_time = datetime.fromtimestamp(latest_session.stat().st_mtime)

                info_text = f"""✅ Última Captura Detectada
📅 Fecha: {capture_time.strftime('%Y-%m-%d %H:%M:%S')}
📁 Sesión: {latest_session.name}
📷 Imágenes: Izquierda y Derecha disponibles
🎯 Estado: Listo para procesar

💡 Puedes seleccionar otra sesión con el botón de arriba"""

                self.capture_info_label.setText(info_text)
                self.btn_start.setEnabled(True)
            else:
                self.capture_info_label.setText(
                    "⚠️ La última sesión está incompleta\n\n"
                    "Usa el botón 'Seleccionar Sesión de Captura' para elegir otra sesión"
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
                    self, "Sin Capturas",
                    "No se encontró el directorio de capturas.\n\n"
                    "Debes tomar al menos una foto con el botón 'Capturar para Modelo 3D' "
                    "antes de poder procesar imágenes."
                )
                return

            # Buscar directorios de sesión
            session_dirs = sorted([d for d in captures_dir.iterdir() if d.is_dir()],
                                 key=lambda d: d.stat().st_mtime, reverse=True)

            if not session_dirs:
                QMessageBox.warning(
                    self, "Sin Sesiones",
                    "No se encontraron sesiones de captura guardadas.\n\n"
                    "Debes tomar al menos una foto con el botón 'Capturar para Modelo 3D' "
                    "antes de poder procesar imágenes."
                )
                return

            # Crear diálogo de selección
            dialog = QDialog(self)
            dialog.setWindowTitle("Seleccionar Sesión de Captura")
            dialog.setModal(True)
            dialog.resize(500, 400)

            layout = QVBoxLayout(dialog)

            # Título
            title = QLabel("📁 Selecciona una sesión de captura para procesar")
            title.setFont(QFont("Arial", 12, QFont.Bold))
            title.setAlignment(Qt.AlignCenter)
            layout.addWidget(title)

            # Lista de sesiones
            list_widget = QListWidget()
            list_widget.setFont(QFont("Courier New", 10))

            for session_dir in session_dirs:
                # Verificar que tenga imágenes izquierda y derecha
                left_img = session_dir / "left.jpg"
                right_img = session_dir / "right.jpg"

                # Obtener fecha de captura
                capture_time = datetime.fromtimestamp(session_dir.stat().st_mtime)
                date_str = capture_time.strftime('%Y-%m-%d %H:%M:%S')

                # Crear item con información
                if left_img.exists() and right_img.exists():
                    status_icon = "✅"
                    status_text = "Completa"
                else:
                    status_icon = "⚠️"
                    status_text = "Incompleta"

                item_text = f"{status_icon} {session_dir.name}\n    📅 {date_str} | {status_text}"
                item = QListWidgetItem(item_text)
                item.setData(Qt.UserRole, session_dir)  # Guardar path en el item

                # Deshabilitar si no está completa
                if not (left_img.exists() and right_img.exists()):
                    item.setFlags(item.flags() & ~Qt.ItemIsEnabled)

                list_widget.addItem(item)

            layout.addWidget(list_widget)

            # Información adicional
            info_label = QLabel(f"📊 Total de sesiones: {len(session_dirs)}")
            info_label.setStyleSheet("color: #666666; font-style: italic; padding: 5px;")
            layout.addWidget(info_label)

            # Botones
            buttons_layout = QHBoxLayout()

            btn_ok = QPushButton("✅ Seleccionar")
            btn_ok.setDefault(True)
            btn_ok.clicked.connect(dialog.accept)
            buttons_layout.addWidget(btn_ok)

            btn_cancel = QPushButton("❌ Cancelar")
            btn_cancel.clicked.connect(dialog.reject)
            buttons_layout.addWidget(btn_cancel)

            layout.addLayout(buttons_layout)

            # Ejecutar diálogo
            if dialog.exec_() == QDialog.Accepted:
                selected_items = list_widget.selectedItems()
                if selected_items:
                    selected_session = selected_items[0].data(Qt.UserRole)

                    # Cargar imágenes de la sesión seleccionada
                    self.selected_left_path = str(selected_session / "left.jpg")
                    self.selected_right_path = str(selected_session / "right.jpg")
                    self.current_session_path = selected_session

                    # Actualizar display
                    capture_time = datetime.fromtimestamp(selected_session.stat().st_mtime)

                    info_text = f"""✅ Sesión Seleccionada
📁 {selected_session.name}
📅 Fecha: {capture_time.strftime('%Y-%m-%d %H:%M:%S')}
📷 Imágenes: Izquierda y Derecha cargadas
🎯 Estado: Listo para procesar"""

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

                    self.add_log_message(f"Sesión cargada: {selected_session.name}")
                else:
                    QMessageBox.information(self, "Sin Selección", "No seleccionaste ninguna sesión.")

        except Exception as e:
            logger.error(f"Error seleccionando sesión de captura: {e}")
            QMessageBox.critical(self, "Error", f"Error al seleccionar sesión:\n{e}")

    def update_manual_selection_display(self):
        """Actualizar display de selección manual"""
        if self.selected_left_path and self.selected_right_path:
            left_name = Path(self.selected_left_path).name
            right_name = Path(self.selected_right_path).name

            info_text = f"""📁 Selección Manual
📷 Izquierda: {left_name}
📷 Derecha: {right_name}
🎯 Estado: Listo para procesar"""

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
            self, "Seleccionar Directorio de Salida", "data/results"
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
                QMessageBox.warning(self, "Advertencia", 
                                  "Debe seleccionar ambas imágenes (izquierda y derecha)")
                return
            
            if not (Path(self.selected_left_path).exists() and Path(self.selected_right_path).exists()):
                QMessageBox.critical(self, "Error", "Una o ambas imágenes no existen")
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
            
            self.add_log_message("Iniciando procesamiento 3D...")
            
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
                    self.add_log_message("✓ Usando paths geométricos ya calculados", "INFO")
                else:
                    self.add_log_message("⚠️ Wire tracking no disponible, usando solo máscaras", "WARNING")
            else:
                self.add_log_message("⚠️ Sin máscara de cable - procesando imagen completa", "WARNING")

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
            self.add_log_message(f"Error iniciando procesamiento: {e}", "ERROR")
            QMessageBox.critical(self, "Error", f"Error iniciando procesamiento:\n{e}")
    
    def cancel_processing(self):
        """Cancelar procesamiento en curso"""
        if self.processing_thread and self.processing_thread.isRunning():
            self.add_log_message("Cancelando procesamiento...", "WARNING")
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
                self.add_log_message("¡Procesamiento 3D completado exitosamente!", "INFO")
                
                # Actualizar estadísticas
                self.results_widget.update_statistics(result)
                
                # Mostrar mensaje de éxito
                export_files = result.get('export_files', [])
                files_info = "\n".join([f"• {Path(f).name}" for f in export_files])
                
                QMessageBox.information(
                    self,
                    "Procesamiento Exitoso",
                    f"El modelo 3D se generó correctamente.\n\n"
                    f"Tiempo: {result.get('processing_time_seconds', 0):.1f}s\n"
                    f"Puntos 3D: {result.get('point_cloud', {}).get('num_points', 0):,}\n\n"
                    f"Archivos generados:\n{files_info}"
                )
                
            else:
                error_msg = result.get('error', 'Error desconocido')
                self.add_log_message(f"Procesamiento falló: {error_msg}", "ERROR")
                
                QMessageBox.critical(
                    self,
                    "Error en Procesamiento",
                    f"El procesamiento 3D falló:\n\n{error_msg}"
                )
                
        except Exception as e:
            logger.error(f"Error manejando resultado: {e}")
        
        finally:
            self.reset_ui_after_processing()
    
    def reset_ui_after_processing(self):
        """Restaurar UI después del procesamiento"""
        self.btn_start.setEnabled(True)
        self.btn_cancel.setEnabled(False)
        self.progress_message.setText("Procesamiento completado")
    
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
                self.add_log_message("Detectando endpoints del cable...", "INFO")

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

                        self.add_log_message(f"Wire tracking exitoso:", "INFO")
                        self.add_log_message(f"  LEFT: {len(tracking_results['left']['path'])} puntos, "
                                      f"Cob: {tracking_results['left']['coverage']*100:.1f}%", "INFO")
                        self.add_log_message(f"  RIGHT: {len(tracking_results['right']['path'])} puntos, "
                                      f"Cob: {tracking_results['right']['coverage']*100:.1f}%", "INFO")

                        self.filter_status_label.setText("Filtro configurado + Wire tracking OK")
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
                        self.add_log_message("Wire tracking no completo", "WARNING")
                        self.wire_tracking_result = None

                        self.filter_status_label.setText("Filtro OK, Wire tracking incompleto")
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

                    self.filter_status_label.setText("Filtro configurado (sin wire tracking)")
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

                    QMessageBox.information(self, "Aviso",
                        f"Filtro de cable configurado.\n\n"
                        f"Wire tracking falló ({e}), pero las máscaras están disponibles.")

            else:
                QMessageBox.information(self, "Cancelado",
                    "Configuración de filtro cancelada.")

        except Exception as e:
            logger.error(f"Error abriendo configuración de filtro: {e}")
            QMessageBox.critical(self, "Error",
                f"Error abriendo configuración de filtro:\n{e}")

    def closeEvent(self, event):
        """Manejar cierre del diálogo"""
        if self.processing_thread and self.processing_thread.isRunning():
            msg = QMessageBox.question(
                self,
                "Procesamiento en Progreso",
                "El procesamiento está en progreso. ¿Deseas cancelarlo y cerrar?",
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