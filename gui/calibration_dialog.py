#!/usr/bin/env python3
"""
Diálogo de calibración para sistema estéreo
Implementa un bucle de captura interactivo: [Preview -> Captura] x N
"""

import os
import cv2
import numpy as np
import time
from datetime import datetime
from pathlib import Path

from PyQt5.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, 
                           QPushButton, QProgressBar, QTextEdit, QGroupBox,
                           QGridLayout, QMessageBox, QCheckBox, QSpinBox,
                           QDoubleSpinBox, QFrame, QApplication)
from PyQt5.QtCore import QThread, pyqtSignal, QTimer, Qt
from PyQt5.QtGui import QPixmap, QImage, QFont

from camera.camera_calibration import CameraCalibrator
from utils.logger import get_logger

logger = get_logger(__name__)

# Hilo solo para PROCESAR, no para capturar
class CalibrationProcessingThread(QThread):
    """Hilo para ejecutar el procesamiento de calibración sin bloquear UI"""
    progress_update = pyqtSignal(int, str)
    calibration_complete = pyqtSignal(bool, dict)
    log_message = pyqtSignal(str, str)  # message, level
    
    def __init__(self, camera_config, session_dir):
        super().__init__()
        self.camera_config = camera_config
        self.session_dir = session_dir
        self.should_stop = False
        
    def run(self):
        """Ejecutar solo el procesamiento de calibración"""
        try:
            self.log_message.emit("Iniciando procesamiento de imágenes...", "INFO")
            calibrator = CameraCalibrator(self.camera_config)
            
            calibration_result = calibrator.calibrate_from_session(
                self.session_dir,
                progress_callback=self.progress_callback
            )
            
            if calibration_result['success']:
                self.log_message.emit("Procesamiento completado exitosamente", "INFO")
            else:
                self.log_message.emit(f"Error en procesamiento: {calibration_result.get('error')}", "ERROR")
            
            self.calibration_complete.emit(calibration_result['success'], calibration_result)
            
        except Exception as e:
            self.log_message.emit(f"Error fatal durante procesamiento: {e}", "ERROR")
            self.calibration_complete.emit(False, {'error': str(e)})
    
    def progress_callback(self, progress, message):
        """Callback para actualizar progreso desde el calibrador"""
        if not self.should_stop:
            # Mapear el progreso del 0-100 (del calibrador) al 50-100 (de la UI)
            mapped_progress = 50 + int(progress * 0.5)
            self.progress_update.emit(mapped_progress, message)
    
    def stop(self):
        """Detener proceso de procesamiento"""
        self.should_stop = True

class CalibrationDialog(QDialog):
    """Diálogo principal de calibración (Lógica de bucle interactivo)"""
    
    def __init__(self, camera_config, stereo_camera, parent=None):
        super().__init__(parent)
        self.camera_config = camera_config
        self.stereo_camera = stereo_camera
        self.processing_thread = None
        self.countdown_timer = QTimer(self)
        self.countdown_seconds = 0
        
        self.images_to_capture = 0
        self.images_captured = 0
        self.capture_session_dir = None
        self.is_capturing = False
        
        self.init_ui()
        self.load_current_calibration_status()
        
    def init_ui(self):
        """Inicializar interfaz de usuario"""
        self.setWindowTitle("Calibración de Cámaras Estéreo")
        # ✅ FIX: No modal, para poder ver la ventana principal
        self.setModal(False) 
        self.resize(800, 600)
        
        layout = QVBoxLayout(self)
        
        # ... (El resto de la UI es igual) ...
        title = QLabel("🎯 Calibración de Cámaras Estéreo")
        title.setFont(QFont("Arial", 18, QFont.Bold))
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet("color: #1976D2; margin: 10px;")
        layout.addWidget(title)
        
        board_info = self.create_board_info_group()
        layout.addWidget(board_info)
        
        capture_config = self.create_capture_config_group()
        layout.addWidget(capture_config)
        
        current_status = self.create_current_status_group()
        layout.addWidget(current_status)
        
        progress_group = self.create_progress_group()
        layout.addWidget(progress_group)
        
        log_group = self.create_log_group()
        layout.addWidget(log_group)
        
        buttons = self.create_buttons()
        layout.addLayout(buttons)
        
        self.apply_styles()
    
    def create_board_info_group(self):
        group = QGroupBox("📋 Requisitos del Tablero de Ajedrez")
        layout = QVBoxLayout(group)
        board_size = self.camera_config.stereo.calibration_board_size
        square_size = self.camera_config.stereo.calibration_square_size_mm
        info_text = f"""
        <b>Configuración del tablero:</b><br>
        • Esquinas internas: {board_size[0]} x {board_size[1]} ({board_size[0] * board_size[1]} esquinas)<br>
        • Tamaño de cuadrado: {square_size} mm<br><br>
        <b>Instrucciones:</b><br>
        • Mueve el diálogo para ver la vista previa de las cámaras.<br>
        • Posiciona el tablero hasta que se vea bien en AMBAS cámaras.<br>
        • El sistema te dará tiempo para re-acomodarte entre cada foto.
        """
        info_label = QLabel(info_text)
        info_label.setWordWrap(True)
        info_label.setStyleSheet("background-color: #E3F2FD; padding: 10px; border-radius: 5px; border: 1px solid #2196F3;")
        layout.addWidget(info_label)
        return group
    
    def create_capture_config_group(self):
        group = QGroupBox("⚙️ Configuración de Captura")
        layout = QGridLayout(group)
        
        layout.addWidget(QLabel("Número de imágenes:"), 0, 0)
        self.num_images_spin = QSpinBox()
        self.num_images_spin.setRange(15, 50)
        self.num_images_spin.setValue(self.camera_config.stereo.min_calibration_images)
        self.num_images_spin.setSuffix(" imágenes")
        layout.addWidget(self.num_images_spin, 0, 1)
        
        # ✅ LÓGICA CAMBIADA: Este es el tiempo de preview ENTRE FOTOS
        layout.addWidget(QLabel("Tiempo de acomodación:"), 1, 0)
        self.delay_spin = QDoubleSpinBox()
        self.delay_spin.setRange(5.0, 30.0)
        self.delay_spin.setValue(8.0) # 8 segundos para acomodar
        self.delay_spin.setSuffix(" segundos")
        self.delay_spin.setDecimals(1)
        layout.addWidget(self.delay_spin, 1, 1)
        
        layout.addWidget(QLabel("Countdown inicial:"), 2, 0)
        self.countdown_spin = QSpinBox()
        self.countdown_spin.setRange(5, 30)
        self.countdown_spin.setValue(10)
        self.countdown_spin.setSuffix(" segundos")
        layout.addWidget(self.countdown_spin, 2, 1)
        
        return group
    
    def create_current_status_group(self):
        group = QGroupBox("📊 Estado Actual de Calibración")
        layout = QVBoxLayout(group)
        self.status_label = QLabel()
        self.status_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.status_label)
        self.details_label = QLabel()
        self.details_label.setWordWrap(True)
        self.details_label.setVisible(False)
        layout.addWidget(self.details_label)
        return group
    
    def create_progress_group(self):
        group = QGroupBox("📈 Progreso de Calibración")
        layout = QVBoxLayout(group)
        self.countdown_label = QLabel("Mueve este diálogo para ver la vista previa")
        self.countdown_label.setFont(QFont("Arial", 16, QFont.Bold))
        self.countdown_label.setAlignment(Qt.AlignCenter)
        self.countdown_label.setStyleSheet("background-color: #F5F5F5; padding: 15px; border-radius: 5px; border: 2px solid #CCCCCC;")
        layout.addWidget(self.countdown_label)
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)
        self.progress_message = QLabel("")
        self.progress_message.setAlignment(Qt.AlignCenter)
        self.progress_message.setVisible(False)
        layout.addWidget(self.progress_message)
        return group
    
    def create_log_group(self):
        group = QGroupBox("📝 Registro de Actividades")
        layout = QVBoxLayout(group)
        self.log_text = QTextEdit()
        self.log_text.setMaximumHeight(120)
        self.log_text.setReadOnly(True)
        self.log_text.setStyleSheet("QTextEdit { background-color: #FAFAFA; font-family: 'Courier New', monospace; font-size: 10px; }")
        layout.addWidget(self.log_text)
        return group
    
    def create_buttons(self):
        layout = QHBoxLayout()
        self.btn_start = QPushButton("🚀 Iniciar Calibración")
        self.btn_start.setFixedHeight(45)
        self.btn_start.setStyleSheet("QPushButton { font-size: 14px; font-weight: bold; background-color: #4CAF50; color: white; border: none; border-radius: 5px; } QPushButton:hover { background-color: #45a049; } QPushButton:disabled { background-color: #CCCCCC; color: #666666; }")
        self.btn_start.clicked.connect(self.start_calibration)
        layout.addWidget(self.btn_start)
        
        self.btn_cancel = QPushButton("❌ Cancelar")
        self.btn_cancel.setFixedHeight(45)
        self.btn_cancel.clicked.connect(self.cancel_calibration)
        self.btn_cancel.setEnabled(False)
        layout.addWidget(self.btn_cancel)
        
        layout.addStretch()
        
        self.btn_close = QPushButton("✅ Cerrar")
        self.btn_close.setFixedHeight(45)
        self.btn_close.clicked.connect(self.close)
        layout.addWidget(self.btn_close)
        return layout
    
    def apply_styles(self):
        self.setStyleSheet("QGroupBox { font-weight: bold; border: 2px solid #CCCCCC; border-radius: 8px; margin: 5px; padding-top: 15px; } QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 8px 0 8px; color: #333333; } QPushButton { padding: 8px 15px; border: none; border-radius: 4px; font-weight: bold; } QSpinBox, QDoubleSpinBox { padding: 5px; border: 1px solid #CCCCCC; border-radius: 3px; }")
    
    def load_current_calibration_status(self):
        if self.camera_config.is_calibrated():
            self.status_label.setText("✅ SISTEMA CALIBRADO")
            self.status_label.setStyleSheet("color: green; font-weight: bold; font-size: 14px;")
            if hasattr(self.camera_config, 'calibration_data'):
                calib_data = self.camera_config.calibration_data
                details_text = f"<b>Detalles:</b> Fecha: {calib_data.get('calibration_date', 'N/A')}, Error: {calib_data.get('calibration_error', 'N/A'):.3f} píxeles"
                self.details_label.setText(details_text)
                self.details_label.setVisible(True)
        else:
            self.status_label.setText("❌ CALIBRACIÓN REQUERIDA")
            self.status_label.setStyleSheet("color: red; font-weight: bold; font-size: 14px;")
            self.details_label.setVisible(False)
    
    def add_log_message(self, message, level="INFO"):
        timestamp = datetime.now().strftime("%H:%M:%S")
        formatted_message = f"[{timestamp}] {level}: {message}"
        self.log_text.append(formatted_message)
        self.log_text.verticalScrollBar().setValue(self.log_text.verticalScrollBar().maximum())
    
    # --- Lógica de Captura Interactiva ---
    
    def start_calibration(self):
        """Inicia el proceso. Muestra advertencia y luego el countdown inicial."""
        msg = QMessageBox.question(
            self, "Confirmar Calibración",
            f"Se capturarán {self.num_images_spin.value()} pares de imágenes.\n\n"
            "Asegúrate de poder ver la vista previa de la ventana principal.\n"
            "¡Mueve este diálogo si es necesario!\n\n"
            "¿Comenzar?",
            QMessageBox.Yes | QMessageBox.No
        )
        
        if msg != QMessageBox.Yes:
            return
        
        # Preparar UI para captura
        self.btn_start.setEnabled(False)
        self.btn_cancel.setEnabled(True)
        self.progress_bar.setVisible(True)
        self.progress_message.setVisible(True)
        
        # Iniciar estado de captura
        self.is_capturing = True
        self.images_to_capture = self.num_images_spin.value()
        self.images_captured = 0
        
        # Crear el directorio de sesión AHORA
        try:
            self.capture_session_dir = self.stereo_camera.create_calibration_session_dir()
            self.add_log_message(f"Sesión creada en: {self.capture_session_dir}", "INFO")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"No se pudo crear el directorio de sesión: {e}")
            self.cancel_calibration()
            return
        
        # Iniciar el primer countdown
        self.start_countdown(self.countdown_spin.value(), self.update_initial_countdown)

    def start_countdown(self, seconds, tick_function_callback):
        """Función genérica para iniciar un countdown."""
        self.countdown_seconds = seconds
        try:
            self.countdown_timer.timeout.disconnect()
        except TypeError:
            pass  # No había nada conectado
        
        self.countdown_timer.timeout.connect(tick_function_callback)
        self.countdown_timer.start(1000)
        tick_function_callback() # Llamar una vez para setear el '0'

    def update_initial_countdown(self):
        """Tick del countdown ANTES de la primera foto."""
        if self.countdown_seconds > 0:
            self.set_countdown_style("🎯 ¡PREPARA EL TABLERO!", f"Captura inicial en: {self.countdown_seconds}", self.countdown_seconds)
            self.countdown_seconds -= 1
        else:
            self.countdown_timer.stop()
            self.capture_one_image_pair() # Capturar la primera imagen

    def update_next_shot_countdown(self):
        """Tick del countdown ENTRE fotos."""
        if self.countdown_seconds > 0:
            self.set_countdown_style("👀 ¡RE-ACOMODA EL TABLERO!", f"Próxima captura en: {self.countdown_seconds}", self.countdown_seconds)
            self.countdown_seconds -= 1
        else:
            self.countdown_timer.stop()
            self.capture_one_image_pair() # Capturar la siguiente imagen

    def capture_one_image_pair(self):
        """Pausa el preview, captura una foto, y decide si seguir o procesar."""
        if not self.is_capturing:
            return

        self.progress_message.setText(f"Capturando imagen {self.images_captured + 1} / {self.images_to_capture}...")
        self.add_log_message(f"Capturando par {self.images_captured + 1}", "INFO")

        # 1. Pausar preview
        self.stop_preview_for_capture()
        
        # 2. Capturar (esto es rápido, pero damos 0.5s para que la cámara pare)
        # Usamos un timer para no bloquear el hilo de la GUI
        QTimer.singleShot(500, self.execute_capture_and_resume)
        
    def execute_capture_and_resume(self):
        """Función llamada por el timer para hacer la captura y decidir el próximo paso."""
        try:
            self.stereo_camera.capture_single_calibration_pair(
                self.capture_session_dir,
                self.images_captured
            )
            self.images_captured += 1
            
            progress = int((self.images_captured / self.images_to_capture) * 50)  # 50% para captura
            self.progress_bar.setValue(progress)

        except Exception as e:
            self.add_log_message(f"Error fatal en captura: {e}", "ERROR")
            QMessageBox.critical(self, "Error de Captura", f"Falló la captura: {e}")
            self.cancel_calibration()  # Abortar
            return

        # 3. Verificar si terminamos
        if self.images_captured >= self.images_to_capture:
            # Terminamos de capturar, ahora procesamos
            self.add_log_message("Captura de imágenes completada.", "INFO")
            self.process_calibration_images()
        else:
            # No hemos terminado, reiniciar preview e iniciar el *siguiente* countdown
            self.start_preview_for_positioning()
            self.start_countdown(int(self.delay_spin.value()), self.update_next_shot_countdown)

    def process_calibration_images(self):
        """Inicia el hilo de procesamiento de imágenes."""
        self.add_log_message("Iniciando procesamiento de calibración...", "INFO")
        self.set_countdown_style("⌛ PROCESANDO", "Calculando parámetros de calibración...", -1)
        self.progress_message.setText("Procesando imágenes...")
        
        # Iniciar el hilo de procesamiento
        self.processing_thread = CalibrationProcessingThread(
            self.camera_config,
            self.capture_session_dir
        )
        
        self.processing_thread.progress_update.connect(self.update_progress)
        self.processing_thread.log_message.connect(self.add_log_message)
        self.processing_thread.calibration_complete.connect(self.on_calibration_complete)
        
        self.processing_thread.start()

    def on_calibration_complete(self, success, result):
        """Maneja el resultado del hilo de procesamiento."""
        self.is_capturing = False
        
        if success:
            self.add_log_message("✅ Calibración completada exitosamente", "INFO")
            self.set_countdown_style("✅ CALIBRACIÓN EXITOSA", "¡Sistema listo!", -2)
            self.progress_bar.setValue(100)
            
            avg_dist = result.get('average_distance_meters', 0) * 100 # Convertir a cm
            dist_msg = f"Distancia promedio al tablero: {avg_dist:.1f} cm"
            self.add_log_message(dist_msg, "INFO")

            # Actualizar estado de calibración en ventana principal
            if hasattr(self.parent(), 'is_calibrated'):
                self.parent().is_calibrated = True
                self.parent().update_calibration_status()
            
            QMessageBox.information(self, "Éxito", f"Calibración completada y guardada.\n\n{dist_msg}")
            self.accept() # Cerrar el diálogo
            
        else:
            error_details = result.get('error', 'Error desconocido')
            self.add_log_message(f"❌ Calibración falló: {error_details}", "ERROR")
            self.set_countdown_style("❌ ERROR EN CALIBRACIÓN", "Revisa el log e intenta de nuevo", -3)
            QMessageBox.critical(self, "Error en Calibración", f"La calibración falló:\n\n{error_details}")
            self.reset_ui_after_calibration()

    # --- Funciones de Ayuda (Preview y UI) ---

    def start_preview_for_positioning(self):
        """Inicia el preview en la ventana principal."""
        try:
            main_window = self.parent()
            if hasattr(main_window, 'start_preview'):
                main_window.start_preview()
        except Exception as e:
            self.add_log_message(f"Error iniciando preview: {e}", "WARNING")

    def stop_preview_for_capture(self):
        """Detiene el preview en la ventana principal."""
        try:
            main_window = self.parent()
            if hasattr(main_window, 'stop_preview'):
                main_window.stop_preview()
        except Exception as e:
            self.add_log_message(f"Error deteniendo preview: {e}", "WARNING")

    def set_countdown_style(self, title, subtitle, seconds):
        """Helper para cambiar el estilo del label de countdown."""
        self.countdown_label.setText(f"{title}\n{subtitle}")
        
        if seconds > 3: # Normal
            color, bg_color = ("#2196F3", "#E3F2FD")
        elif seconds > 0: # Apunto de capturar
            color, bg_color = ("#F44336", "#FFCDD2")
        elif seconds == -1: # Procesando
            color, bg_color = ("#FF9800", "#FFF9C4")
        elif seconds == -2: # Éxito
            color, bg_color = ("#2E7D32", "#C8E6C9")
        elif seconds == -3: # Error
            color, bg_color = ("#D32F2F", "#FFCDD2")
        else: # Standby
            color, bg_color = ("#333333", "#F5F5F5")
            
        self.countdown_label.setStyleSheet(f"background-color: {bg_color}; color: {color}; padding: 15px; border-radius: 5px; border: 2px solid {color}; font-size: 16px; font-weight: bold;")

    def update_progress(self, progress, message):
        """Actualizar progreso (conectado al hilo)"""
        self.progress_bar.setValue(progress)
        self.progress_message.setText(message)
    
    def reset_ui_after_calibration(self):
        """Restaurar UI después de un fallo o cancelación."""
        self.btn_start.setEnabled(True)
        self.btn_cancel.setEnabled(False)
        self.is_capturing = False
        
        self.progress_bar.setVisible(False)
        self.progress_message.setVisible(False)
        self.set_countdown_style("Listo para (re)iniciar", "Mueve este diálogo para ver la vista previa", 0)
        
        # --- CORRECCIÓN ---
        # Vuelve a iniciar el preview para que la app no se quede congelada
        self.start_preview_for_positioning()
        # --- FIN CORRECCIÓN ---
    
    def cancel_calibration(self):
        """Cancelar todo el proceso."""
        self.add_log_message("Calibración cancelada por usuario", "WARNING")
        self.is_capturing = False
        
        # Detener timers
        if self.countdown_timer.isActive():
            self.countdown_timer.stop()
        
        # Detener hilo de procesamiento si está activo
        if self.processing_thread and self.processing_thread.isRunning():
            self.processing_thread.stop()
            self.processing_thread.wait(2000) # Esperar 2s
        
        self.reset_ui_after_calibration()
        
        # Asegurarse de que el preview se restaure
        self.start_preview_for_positioning()

    def closeEvent(self, event):
        """Manejar cierre del diálogo."""
        if self.is_capturing:
            msg = QMessageBox.question(
                self, "Calibración en Progreso",
                "La calibración está en progreso. ¿Deseas cancelarla y cerrar?",
                QMessageBox.Yes | QMessageBox.No
            )
            if msg == QMessageBox.Yes:
                self.cancel_calibration()
                event.accept()
            else:
                event.ignore()
        else:
            self.start_preview_for_positioning() # Asegurarse de que el preview corra al cerrar
            event.accept()

if __name__ == "__main__":
    # Test del diálogo (requiere una app y mocks)
    print("Este diálogo debe ser lanzado desde main.py")