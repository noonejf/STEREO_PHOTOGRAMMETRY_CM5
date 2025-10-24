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
    
    def __init__(self, camera_config, processing_params):
        super().__init__()
        self.camera_config = camera_config
        self.processing_params = processing_params
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
            
            # Procesar par estéreo
            result = processor.process_stereo_pair(
                left_img, right_img,
                algorithm=self.processing_params['algorithm'],
                progress_callback=self.progress_callback,
                save_debug_images=True  # ✅ Activar modo depuración
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
        self.resize(1000, 700)
        
        layout = QVBoxLayout(self)
        
        # Título
        title = QLabel("🏗️ Procesamiento 3D y Generación de Modelo")
        title.setFont(QFont("Arial", 18, QFont.Bold))
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet("color: #1976D2; margin: 10px;")
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

        # Separador
        separator = QLabel("─── o seleccionar imágenes individuales ───")
        separator.setAlignment(Qt.AlignCenter)
        separator.setStyleSheet("color: #999999; font-size: 9px; margin: 5px;")
        layout.addWidget(separator)

        # Botones de selección manual de imágenes individuales
        manual_layout = QHBoxLayout()

        self.btn_select_left = QPushButton("📷 Seleccionar Izquierda")
        self.btn_select_left.clicked.connect(self.select_left_image)
        manual_layout.addWidget(self.btn_select_left)

        self.btn_select_right = QPushButton("📷 Seleccionar Derecha")
        self.btn_select_right.clicked.connect(self.select_right_image)
        manual_layout.addWidget(self.btn_select_right)

        layout.addLayout(manual_layout)

        # Rutas seleccionadas
        self.selected_left_path = None
        self.selected_right_path = None

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
        self.log_text.setMaximumHeight(100)
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
        self.btn_start.setFixedHeight(45)
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
        self.btn_cancel.setFixedHeight(45)
        self.btn_cancel.clicked.connect(self.cancel_processing)
        self.btn_cancel.setEnabled(False)
        layout.addWidget(self.btn_cancel)
        
        layout.addStretch()
        
        # Botón de cerrar
        self.btn_close = QPushButton("✅ Cerrar")
        self.btn_close.setFixedHeight(45)
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
    
    def select_left_image(self):
        """Seleccionar imagen izquierda manualmente"""
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Seleccionar Imagen Izquierda",
            "data/captures", "Imágenes (*.jpg *.jpeg *.png *.bmp)"
        )
        if file_path:
            self.selected_left_path = file_path
            self.update_manual_selection_display()
    
    def select_right_image(self):
        """Seleccionar imagen derecha manualmente"""
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Seleccionar Imagen Derecha", 
            "data/captures", "Imágenes (*.jpg *.jpeg *.png *.bmp)"
        )
        if file_path:
            self.selected_right_path = file_path
            self.update_manual_selection_display()
    
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

                    # Actualizar display
                    capture_time = datetime.fromtimestamp(selected_session.stat().st_mtime)

                    info_text = f"""✅ Sesión Seleccionada
📁 {selected_session.name}
📅 Fecha: {capture_time.strftime('%Y-%m-%d %H:%M:%S')}
📷 Imágenes: Izquierda y Derecha cargadas
🎯 Estado: Listo para procesar"""

                    self.capture_info_label.setText(info_text)
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
            
            # Crear y iniciar hilo de procesamiento
            self.processing_thread = ProcessingWorkerThread(
                self.camera_config,
                processing_params
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