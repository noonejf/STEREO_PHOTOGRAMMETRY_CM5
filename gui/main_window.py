#!/usr/bin/env python3
"""
Ventana principal del sistema de fotogrametría estéreo CM5
Interfaz PyQt5 con vista previa de cámaras y controles principales
"""

import os
import sys
import logging
from datetime import datetime
from pathlib import Path

from PyQt5.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
                           QGridLayout, QPushButton, QLabel, QTextEdit,
                           QProgressBar, QGroupBox, QMessageBox, QStatusBar,
                           QSplitter, QFrame, QApplication)
from PyQt5.QtCore import QThread, pyqtSignal, QTimer, Qt, QSize
from PyQt5.QtGui import QPixmap, QFont, QIcon, QPalette, QColor

from camera.stereo_camera import StereoCamera
from gui.camera_preview import CameraPreviewWidget
from gui.calibration_dialog import CalibrationDialog
from gui.processing_dialog import ProcessingDialog
from utils.logger import get_logger

logger = get_logger(__name__)

class CountdownThread(QThread):
    """Hilo para cuenta regresiva sin bloquear la GUI"""
    countdown_update = pyqtSignal(int)
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

class MainWindow(QMainWindow):
    """Ventana principal del sistema de fotogrametría estéreo"""

    def __init__(self, camera_config, cameras_available=True):
        super().__init__()
        self.camera_config = camera_config
        self.stereo_camera = None
        self.countdown_thread = None
        self.cameras_available = cameras_available  # Nueva bandera

        # Estado de la aplicación
        self.is_calibrated = camera_config.is_calibrated()
        self.preview_active = False

        self.init_ui()
        self.setup_camera_system()
        self.setup_connections()
        self.update_ui_for_camera_availability()  # Actualizar UI según disponibilidad de cámaras

        logger.info(f"Ventana principal inicializada (Cámaras: {'Disponibles' if cameras_available else 'No disponibles'})")
    
    def init_ui(self):
        """Inicializar interfaz de usuario"""
        self.setWindowTitle("Sistema de Fotogrametría Estéreo CM5 - Arducam HQ 477")
        self.setGeometry(100, 100, 1200, 800)
        
        # Widget central con splitter
        central_widget = QWidget()  # ← CREAR AQUÍ
        self.setCentralWidget(central_widget)
        
        # Layout principal VERTICAL
        main_layout = QVBoxLayout(central_widget)
        
        # Splitter principal VERTICAL (arriba/abajo)
        main_splitter = QSplitter(Qt.Vertical)
        main_layout.addWidget(main_splitter)
        
        # Panel SUPERIOR - Vista previa de cámaras
        self.setup_preview_panel(main_splitter)
        
        # Panel INFERIOR - Controles + Registro
        bottom_widget = QWidget()
        main_splitter.addWidget(bottom_widget)
        bottom_layout = QHBoxLayout(bottom_widget)
        
        # Splitter horizontal para controles y registro
        bottom_splitter = QSplitter(Qt.Horizontal)
        bottom_layout.addWidget(bottom_splitter)
        
        # Panel izquierdo inferior - Controles
        self.setup_control_panel(bottom_splitter)
        
        # Panel derecho inferior - Registro (más grande)
        self.setup_log_panel(bottom_splitter)
        
        # Barra de estado
        self.setup_status_bar()
        
        # Configurar proporciones del splitter principal (arriba/abajo)
        main_splitter.setSizes([600, 300])  # Más espacio arriba para cámaras
        
        # Configurar proporciones del splitter inferior (controles/registro)
        bottom_splitter.setSizes([400, 600])  # Más espacio para registro
        
        # Aplicar estilos
        self.apply_styles()
    
    def setup_preview_panel(self, parent_splitter):
        """Configurar panel de vista previa de cámaras"""
        preview_frame = QFrame()
        preview_frame.setFrameStyle(QFrame.StyledPanel)
        parent_splitter.addWidget(preview_frame)
        
        preview_layout = QVBoxLayout(preview_frame)
        
        # Título del panel
        preview_title = QLabel("Vista Previa de Cámaras Estéreo")
        preview_title.setFont(QFont("Arial", 14, QFont.Bold))
        preview_title.setAlignment(Qt.AlignCenter)
        preview_layout.addWidget(preview_title)
        
        # Contenedor de vistas de cámaras
        cameras_widget = QWidget()
        cameras_layout = QHBoxLayout(cameras_widget)
        
        # Vista previa cámara izquierda
        self.left_camera_preview = CameraPreviewWidget("Cámara Izquierda (CAM0)", 0, self.camera_config)
        cameras_layout.addWidget(self.left_camera_preview)
        
        # Vista previa cámara derecha  
        self.right_camera_preview = CameraPreviewWidget("Cámara Derecha (CAM1)", 1, self.camera_config)
        cameras_layout.addWidget(self.right_camera_preview)
        
        preview_layout.addWidget(cameras_widget)
        
        # Controles de vista previa
        preview_controls_layout = QHBoxLayout()
        
        self.btn_start_preview = QPushButton("▶ Iniciar Vista Previa")
        self.btn_start_preview.setFixedHeight(40)
        self.btn_start_preview.clicked.connect(self.toggle_preview)
        preview_controls_layout.addWidget(self.btn_start_preview)
        
        self.btn_stop_preview = QPushButton("⏹ Detener Vista Previa")
        self.btn_stop_preview.setFixedHeight(40)
        self.btn_stop_preview.clicked.connect(self.stop_preview)
        self.btn_stop_preview.setEnabled(False)
        preview_controls_layout.addWidget(self.btn_stop_preview)
        
        preview_layout.addLayout(preview_controls_layout)
        
        # Información de cámaras
        camera_info_layout = QHBoxLayout()
        
        left_info = QLabel(f"Izq: {self.camera_config.left_camera.name}")
        left_info.setStyleSheet("color: #2196F3; font-weight: bold;")
        camera_info_layout.addWidget(left_info)
        
        camera_info_layout.addStretch()
        
        right_info = QLabel(f"Der: {self.camera_config.right_camera.name}")
        right_info.setStyleSheet("color: #FF9800; font-weight: bold;")
        camera_info_layout.addWidget(right_info)
        
        preview_layout.addLayout(camera_info_layout)
    
    def setup_control_panel(self, parent_splitter):
        """Configurar panel de controles principal"""
        control_frame = QFrame()
        control_frame.setFrameStyle(QFrame.StyledPanel)
        parent_splitter.addWidget(control_frame)
        
        control_layout = QVBoxLayout(control_frame)
        
        # Título del sistema
        system_title = QLabel("Sistema de Fotogrametría Estéreo")
        system_title.setFont(QFont("Arial", 16, QFont.Bold))
        system_title.setAlignment(Qt.AlignCenter)
        system_title.setStyleSheet("color: #1976D2; margin: 10px;")
        control_layout.addWidget(system_title)
        
        # Controles principales (PRIMERO)
        main_controls_group = self.create_main_controls_group()
        control_layout.addWidget(main_controls_group)

        # Estado de calibración (DESPUÉS)
        self.calibration_status_group = self.create_calibration_status_group()
        control_layout.addWidget(self.calibration_status_group)
        
        # Controles de captura
        capture_controls_group = self.create_capture_controls_group() 
        control_layout.addWidget(capture_controls_group)
        
        
        control_layout.addStretch()
    
    def create_calibration_status_group(self):
        """Crear grupo de estado de calibración"""
        group = QGroupBox("Estado de Calibración")
        layout = QVBoxLayout(group)

        # Indicador de estado principal
        self.calibration_status_label = QLabel()
        self.calibration_status_label.setFont(QFont("Arial", 11, QFont.Bold))
        self.calibration_status_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.calibration_status_label)

        # Panel de detalles de calibración (nuevo)
        self.calibration_details_frame = QFrame()
        self.calibration_details_frame.setFrameStyle(QFrame.StyledPanel)
        self.calibration_details_frame.setStyleSheet("""
            QFrame {
                background-color: #F5F5F5;
                border: 1px solid #CCCCCC;
                border-radius: 5px;
                padding: 5px;
            }
        """)
        details_layout = QVBoxLayout(self.calibration_details_frame)
        details_layout.setSpacing(3)
        details_layout.setContentsMargins(8, 8, 8, 8)

        # Labels de información
        self.calib_error_label = QLabel("Error: --")
        self.calib_error_label.setFont(QFont("Arial", 9))
        details_layout.addWidget(self.calib_error_label)

        self.calib_images_label = QLabel("Imágenes: --")
        self.calib_images_label.setFont(QFont("Arial", 9))
        details_layout.addWidget(self.calib_images_label)

        self.calib_date_label = QLabel("Fecha: --")
        self.calib_date_label.setFont(QFont("Arial", 9))
        details_layout.addWidget(self.calib_date_label)

        self.calib_baseline_label = QLabel("Baseline: --")
        self.calib_baseline_label.setFont(QFont("Arial", 9))
        details_layout.addWidget(self.calib_baseline_label)

        layout.addWidget(self.calibration_details_frame)

        # Actualizar estado inicial
        self.update_calibration_status()

        # Botón de calibración
        self.btn_calibrate = QPushButton("🎯 Calibrar Cámaras")
        self.btn_calibrate.setFixedHeight(50)
        self.btn_calibrate.setStyleSheet("""
            QPushButton {
                font-size: 14px;
                font-weight: bold;
                background-color: #4CAF50;
                color: white;
                border: none;
                border-radius: 5px;
            }
            QPushButton:hover {
                background-color: #45a049;
            }
            QPushButton:pressed {
                background-color: #3d8b40;
            }
        """)
        self.btn_calibrate.clicked.connect(self.start_calibration)
        layout.addWidget(self.btn_calibrate)

        return group
    
    def create_main_controls_group(self):
        """Crear grupo de controles principales"""
        group = QGroupBox("Operaciones Principales")
        layout = QVBoxLayout(group)
        
        # Botón de reconstrucción 3D
        self.btn_capture_3d = QPushButton("📸 Capturar para Modelo 3D")
        self.btn_capture_3d.setFixedHeight(50)
        self.btn_capture_3d.setStyleSheet("""
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
            QPushButton:pressed {
                background-color: #1565C0;
            }
            QPushButton:disabled {
                background-color: #CCCCCC;
                color: #666666;
            }
        """)
        self.btn_capture_3d.clicked.connect(self.start_3d_capture)
        self.btn_capture_3d.setEnabled(self.is_calibrated)
        layout.addWidget(self.btn_capture_3d)
        
        # Botón de procesamiento
        self.btn_process_3d = QPushButton("⚙️ Procesar Últimas Capturas")
        self.btn_process_3d.setFixedHeight(40)
        self.btn_process_3d.clicked.connect(self.process_last_captures)
        # IMPORTANTE: Habilitar solo si el sistema está calibrado
        # (El procesamiento 3D REQUIERE calibración válida)
        self.btn_process_3d.setEnabled(self.is_calibrated)
        layout.addWidget(self.btn_process_3d)
        
        return group
    
    def create_capture_controls_group(self):
        """Crear grupo de controles de captura"""
        group = QGroupBox("Control de Captura")
        layout = QVBoxLayout(group)
        
        # Cuenta regresiva
        self.countdown_label = QLabel("Listo para captura")
        self.countdown_label.setFont(QFont("Arial", 18, QFont.Bold))
        self.countdown_label.setAlignment(Qt.AlignCenter)
        self.countdown_label.setStyleSheet("""
            background-color: #E3F2FD;
            padding: 15px;
            border-radius: 5px;
            border: 2px solid #2196F3;
        """)
        layout.addWidget(self.countdown_label)
        
        # Progreso
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)
        
        # Botón de cancelar
        self.btn_cancel = QPushButton("❌ Cancelar")
        self.btn_cancel.clicked.connect(self.cancel_operation)
        self.btn_cancel.setVisible(False)
        layout.addWidget(self.btn_cancel)
        
        return group
    
    
    def setup_status_bar(self):
        """Configurar barra de estado"""
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        
        # Etiquetas de estado
        self.status_camera_label = QLabel("Cámaras: Desconectadas")
        self.status_calibration_label = QLabel(
            "Calibración: OK" if self.is_calibrated else "Calibración: Requerida"
        )
        
        self.status_bar.addWidget(self.status_camera_label)
        self.status_bar.addPermanentWidget(self.status_calibration_label)
    
    def apply_styles(self):
        """Aplicar estilos globales"""
        self.setStyleSheet("""
            QMainWindow {
                background-color: #FAFAFA;
            }
            QGroupBox {
                font-weight: bold;
                border: 2px solid #CCCCCC;
                border-radius: 5px;
                margin: 5px;
                padding-top: 10px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px 0 5px;
                color: #333333;
            }
            QPushButton {
                padding: 8px;
                border: none;
                border-radius: 4px;
                font-weight: bold;
            }
        """)
    
    def setup_camera_system(self):
        """Inicializar sistema de cámaras"""
        if not self.cameras_available:
            self.log_message("Sistema en modo de solo procesamiento (sin cámaras)", "WARNING")
            self.status_camera_label.setText("Cámaras: No disponibles")
            return

        try:
            self.stereo_camera = StereoCamera(self.camera_config)
            self.log_message("Sistema de cámaras inicializado")
            self.status_camera_label.setText("Cámaras: Conectadas")
        except Exception as e:
            self.log_message(f"Error inicializando cámaras: {e}", "ERROR")
            self.status_camera_label.setText("Cámaras: Error")
            self.cameras_available = False
    
    def update_ui_for_camera_availability(self):
        """Actualizar UI según disponibilidad de cámaras"""
        if not self.cameras_available:
            # Deshabilitar funciones que REQUIEREN cámaras
            self.btn_start_preview.setEnabled(False)
            self.btn_stop_preview.setEnabled(False)
            self.btn_capture_3d.setEnabled(False)

            # Agregar texto informativo
            self.btn_start_preview.setText("▶ Vista Previa (No disponible)")
            self.btn_capture_3d.setText("📸 Captura (No disponible)")

            # MANTENER calibración habilitada - puede procesar sesiones existentes
            self.btn_calibrate.setEnabled(True)
            self.btn_calibrate.setText("🎯 Calibrar (Procesar Sesión)")

            # IMPORTANTE: Habilitar procesamiento 3D si hay calibración
            if self.is_calibrated:
                self.btn_process_3d.setEnabled(True)
                self.log_message("Modo de solo procesamiento activado - puedes procesar capturas y calibración existentes")
            else:
                # Mostrar mensaje informativo
                self.log_message(
                    "Sin cámaras: Puedes recalibrar usando sesiones existentes o transferir calibración de Raspberry Pi",
                    "WARNING"
                )

    def setup_connections(self):
        """Configurar conexiones de señales"""
        # Conexiones de vista previa
        if hasattr(self.left_camera_preview, 'frame_ready'):
            self.left_camera_preview.frame_ready.connect(self.on_left_frame_ready)
        if hasattr(self.right_camera_preview, 'frame_ready'):
            self.right_camera_preview.frame_ready.connect(self.on_right_frame_ready)
    
    def update_calibration_status(self):
        """Actualizar indicador de estado de calibración"""
        # Obtener información detallada de calibración
        calib_info = self.camera_config.get_calibration_info()

        if calib_info['is_calibrated']:
            # Sistema calibrado - Mostrar estado con calidad
            quality_color = {
                "Excelente": "#2E7D32",  # Verde oscuro
                "Buena": "#43A047",      # Verde
                "Aceptable": "#F57C00",  # Naranja
                "Pobre": "#D32F2F"       # Rojo
            }.get(calib_info['quality'], "#666666")

            self.calibration_status_label.setText(
                f"✅ Sistema Calibrado - Calidad: {calib_info['quality']}"
            )
            self.calibration_status_label.setStyleSheet(
                f"color: {quality_color}; font-weight: bold;"
            )

            # Mostrar detalles
            self.calib_error_label.setText(
                f"Error de reproyección: {calib_info['error']:.3f} px"
            )
            self.calib_images_label.setText(
                f"Imágenes usadas: {calib_info['num_images']}"
            )
            self.calib_date_label.setText(
                f"Fecha: {calib_info['date']}"
            )
            if calib_info['baseline_mm']:
                self.calib_baseline_label.setText(
                    f"Baseline: {calib_info['baseline_mm']:.1f} mm"
                )

            # Colorear los labels según la calidad
            if calib_info['quality'] in ["Excelente", "Buena"]:
                detail_color = "#2E7D32"
            elif calib_info['quality'] == "Aceptable":
                detail_color = "#F57C00"
            else:
                detail_color = "#D32F2F"

            for label in [self.calib_error_label, self.calib_images_label,
                         self.calib_date_label, self.calib_baseline_label]:
                label.setStyleSheet(f"color: {detail_color};")

            # Mostrar panel de detalles
            self.calibration_details_frame.setVisible(True)

            # Habilitar captura 3D
            if hasattr(self, 'btn_capture_3d'):
                self.btn_capture_3d.setEnabled(True)

            # Habilitar procesamiento 3D (requiere calibración)
            if hasattr(self, 'btn_process_3d'):
                self.btn_process_3d.setEnabled(True)

            # Actualizar estado
            self.is_calibrated = True

        else:
            # Sistema NO calibrado
            self.calibration_status_label.setText("❌ Calibración Requerida")
            self.calibration_status_label.setStyleSheet("color: red; font-weight: bold;")

            # Ocultar panel de detalles
            if hasattr(self, 'calibration_details_frame'):
                self.calibration_details_frame.setVisible(False)

            # Deshabilitar captura 3D
            if hasattr(self, 'btn_capture_3d'):
                self.btn_capture_3d.setEnabled(False)

            # Deshabilitar procesamiento 3D (requiere calibración)
            if hasattr(self, 'btn_process_3d'):
                self.btn_process_3d.setEnabled(False)

            # Actualizar estado
            self.is_calibrated = False

        # Solo actualizar si la barra de estado ya existe
        if hasattr(self, 'status_calibration_label'):
            self.status_calibration_label.setText(
                "Calibración: OK" if self.is_calibrated else "Calibración: Requerida"
            )
    
    def log_message(self, message, level="INFO"):
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
    
    def toggle_preview(self):
        """Alternar vista previa de cámaras"""
        if not self.preview_active:
            self.start_preview()
        else:
            self.stop_preview()
    
    def start_preview(self):
        """Iniciar vista previa de cámaras"""
        try:
            self.log_message("Iniciando vista previa de cámaras...")
            
            # Iniciar vista previa en ambas cámaras
            self.left_camera_preview.start_preview()
            self.right_camera_preview.start_preview()
            
            self.preview_active = True
            self.btn_start_preview.setEnabled(False)
            self.btn_stop_preview.setEnabled(True)
            self.btn_start_preview.setText("▶ Vista Activa")
            
            self.log_message("Vista previa iniciada")
            
        except Exception as e:
            self.log_message(f"Error iniciando vista previa: {e}", "ERROR")
            QMessageBox.critical(self, "Error", f"No se pudo iniciar la vista previa:\n{e}")
    
    def stop_preview(self):
        """Detener vista previa de cámaras"""
        try:
            self.log_message("Deteniendo vista previa...")
            
            self.left_camera_preview.stop_preview()
            self.right_camera_preview.stop_preview()
            
            self.preview_active = False
            self.btn_start_preview.setEnabled(True)
            self.btn_stop_preview.setEnabled(False)
            self.btn_start_preview.setText("▶ Iniciar Vista Previa")
            
            self.log_message("Vista previa detenida")
            
        except Exception as e:
            self.log_message(f"Error deteniendo vista previa: {e}", "ERROR")
    
    def start_calibration(self):
        """Iniciar proceso de calibración"""
        try:
            # Mostrar diálogo de calibración
            # (El diálogo decidirá si puede tomar fotos o solo procesar sesiones existentes)
            dialog = CalibrationDialog(self.camera_config, self.stereo_camera, self)
            result = dialog.exec_()

            if result == dialog.Accepted:
                # Recargar estado de calibración desde el archivo
                self.camera_config.load_calibration()
                self.is_calibrated = self.camera_config.is_calibrated()
                self.update_calibration_status()

                # Mostrar mensaje con info de la nueva calibración
                calib_info = self.camera_config.get_calibration_info()
                self.log_message(
                    f"Calibración completada: {calib_info['quality']} - "
                    f"Error: {calib_info['error']:.3f} px - "
                    f"Imágenes: {calib_info['num_images']}"
                )

        except Exception as e:
            self.log_message(f"Error en calibración: {e}", "ERROR")
            QMessageBox.critical(self, "Error", f"Error durante calibración:\n{e}")
    
    def start_3d_capture(self):
        """Iniciar captura para modelo 3D"""
        if not self.is_calibrated:
            QMessageBox.warning(self, "Advertencia", 
                              "Debe calibrar las cámaras antes de la captura 3D")
            return
        
        try:
            # Mostrar advertencia y confirmar
            msg = QMessageBox()
            msg.setIcon(QMessageBox.Information)
            msg.setWindowTitle("Preparación para Captura 3D")
            msg.setText("¡Atención! Vas a comenzar la captura para modelo 3D")
            msg.setInformativeText(
                "Se iniciará una cuenta regresiva de 10 segundos.\n"
                "Prepara tu objeto y asegúrate de que esté bien iluminado."
            )
            msg.setStandardButtons(QMessageBox.Ok | QMessageBox.Cancel)
            msg.setDefaultButton(QMessageBox.Ok)
            
            if msg.exec_() != QMessageBox.Ok:
                return
            
            # Iniciar cuenta regresiva
            self.start_countdown_capture()
            
        except Exception as e:
            self.log_message(f"Error iniciando captura 3D: {e}", "ERROR")
            QMessageBox.critical(self, "Error", f"Error durante captura 3D:\n{e}")
    
    def start_countdown_capture(self):
        """Iniciar cuenta regresiva para captura"""
        self.log_message("Iniciando cuenta regresiva para captura...")
        
        # Deshabilitar controles
        self.btn_capture_3d.setEnabled(False)
        self.btn_calibrate.setEnabled(False)
        self.btn_cancel.setVisible(True)
        
        # Iniciar cuenta regresiva
        self.countdown_thread = CountdownThread(10)
        self.countdown_thread.countdown_update.connect(self.update_countdown)
        self.countdown_thread.countdown_finished.connect(self.capture_stereo_pair)
        self.countdown_thread.start()
    
    def update_countdown(self, seconds):
        """Actualizar display de cuenta regresiva"""
        self.countdown_label.setText(f"Captura en: {seconds}")
        self.countdown_label.setStyleSheet(f"""
            background-color: {'#FFCDD2' if seconds <= 3 else '#FFF9C4'};
            padding: 15px;
            border-radius: 5px;
            border: 2px solid {'#F44336' if seconds <= 3 else '#FF9800'};
            font-size: 24px;
            font-weight: bold;
            color: {'#D32F2F' if seconds <= 3 else '#F57C00'};
        """)
    
    def capture_stereo_pair(self):
        """Ejecutar captura del par estéreo"""
        preview_was_active = False
        try:
            # CRÍTICO: Detener vista previa si está activa
            if self.preview_active:
                preview_was_active = True
                self.log_message("Deteniendo vista previa para captura...")
                self.stop_preview()
                # Dar tiempo para que los procesos de vista previa se cierren
                import time
                time.sleep(1.0)

            self.countdown_label.setText("📸 CAPTURANDO...")
            self.countdown_label.setStyleSheet("""
                background-color: #C8E6C9;
                padding: 15px;
                border-radius: 5px;
                border: 2px solid #4CAF50;
                font-size: 20px;
                font-weight: bold;
                color: #2E7D32;
            """)

            QApplication.processEvents()  # Actualizar UI

            # Realizar captura
            if self.stereo_camera:
                capture_result = self.stereo_camera.capture_stereo_pair()

                if capture_result.get('success', False):
                    self.log_message("Par estéreo capturado exitosamente")
                    self.countdown_label.setText("✅ Captura Exitosa")
                    self.btn_process_3d.setEnabled(True)
                else:
                    error_msg = capture_result.get('error', 'Error desconocido')
                    self.log_message(f"Error capturando par estéreo: {error_msg}", "ERROR")
                    self.countdown_label.setText("❌ Error en Captura")

            self.cleanup_after_capture(preview_was_active)

        except Exception as e:
            self.log_message(f"Error durante captura: {e}", "ERROR")
            self.countdown_label.setText("❌ Error en Captura")
            self.cleanup_after_capture(preview_was_active)
    
    def cleanup_after_capture(self, restart_preview=False):
        """Limpiar después de captura"""
        # Restaurar controles
        self.btn_capture_3d.setEnabled(True)
        self.btn_calibrate.setEnabled(True)
        self.btn_cancel.setVisible(False)

        # Reiniciar vista previa si estaba activa
        if restart_preview:
            def delayed_restart():
                self.log_message("Reiniciando vista previa...")
                self.start_preview()
            QTimer.singleShot(2000, delayed_restart)

        # Restaurar estado normal después de 3 segundos
        QTimer.singleShot(3000, self.restore_normal_state)
    
    def restore_normal_state(self):
        """Restaurar estado normal de la interfaz"""
        self.countdown_label.setText("Listo para captura")
        self.countdown_label.setStyleSheet("""
            background-color: #E3F2FD;
            padding: 15px;
            border-radius: 5px;
            border: 2px solid #2196F3;
            font-size: 16px;
            font-weight: bold;
            color: #1976D2;
        """)
    
    def cancel_operation(self):
        """Cancelar operación en curso"""
        if self.countdown_thread and self.countdown_thread.isRunning():
            self.countdown_thread.stop()
            self.countdown_thread.wait()
        
        self.log_message("Operación cancelada por el usuario")
        self.cleanup_after_capture()
        self.restore_normal_state()
    
    def process_last_captures(self):
        """Procesar últimas capturas para generar modelo 3D"""
        try:
            dialog = ProcessingDialog(self.camera_config, self)
            dialog.exec_()
        except Exception as e:
            self.log_message(f"Error en procesamiento: {e}", "ERROR")
            QMessageBox.critical(self, "Error", f"Error durante procesamiento:\n{e}")
    
    def on_left_frame_ready(self, frame):
        """Callback para frame de cámara izquierda"""
        pass  # Implementar si se necesita procesamiento adicional
    
    def on_right_frame_ready(self, frame):
        """Callback para frame de cámara derecha"""
        pass  # Implementar si se necesita procesamiento adicional
    
    def setup_log_panel(self, parent_splitter):
        """Configurar panel de registro de actividades"""
        log_frame = QFrame()
        log_frame.setFrameStyle(QFrame.StyledPanel)
        parent_splitter.addWidget(log_frame)
        
        log_layout = QVBoxLayout(log_frame)
        
        # Título
        log_title = QLabel("Registro de Actividades")
        log_title.setFont(QFont("Arial", 12, QFont.Bold))
        log_title.setAlignment(Qt.AlignCenter)
        log_layout.addWidget(log_title)
        
        # Log text
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setStyleSheet("""
            QTextEdit {
                background-color: #F5F5F5;
                font-family: 'Courier New', monospace;
                font-size: 10px;
                border: 1px solid #CCCCCC;
            }
        """)
        log_layout.addWidget(self.log_text)

    def closeEvent(self, event):
        """Manejar cierre de ventana"""
        try:
            self.log_message("Cerrando aplicación...")
            
            # Detener vista previa
            if self.preview_active:
                self.stop_preview()
            
            # Detener hilos
            if self.countdown_thread and self.countdown_thread.isRunning():
                self.countdown_thread.stop()
                self.countdown_thread.wait()
            
            # Cerrar sistema de cámaras
            if self.stereo_camera:
                self.stereo_camera.cleanup()
            
            logger.info("Aplicación cerrada correctamente")
            event.accept()
            
        except Exception as e:
            logger.error(f"Error durante cierre: {e}")
            event.accept()

if __name__ == "__main__":
    # Test de la ventana principal
    from config.camera_config import CameraConfig
    
    app = QApplication(sys.argv)
    
    try:
        config = CameraConfig()
        window = MainWindow(config)
        window.show()
        
        sys.exit(app.exec_())
    except Exception as e:
        print(f"Error: {e}")
        QMessageBox.critical(None, "Error", f"Error iniciando aplicación:\n{e}")
        sys.exit(1)