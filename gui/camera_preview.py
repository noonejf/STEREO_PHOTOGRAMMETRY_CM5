#!/usr/bin/env python3
"""
Widget de vista previa para cámaras Arducam HQ 477
Muestra feed en vivo usando libcamera y PyQt5
"""

import os
import cv2
import numpy as np
import subprocess
import threading
import time
from pathlib import Path

from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QLabel, QPushButton, 
                           QHBoxLayout, QFrame, QSizePolicy)
from PyQt5.QtCore import QThread, pyqtSignal, QTimer, Qt, QSize
from PyQt5.QtGui import QPixmap, QImage, QFont, QPainter, QPen

from utils.logger import get_logger

logger = get_logger(__name__)

class LibcameraPreviewThread(QThread):
    """Hilo para capturar frames de libcamera usando subprocess"""
    frame_ready = pyqtSignal(np.ndarray)
    error_occurred = pyqtSignal(str)
    
    def __init__(self, camera_id, resolution=(640, 480)):
        super().__init__()
        self.camera_id = camera_id
        self.resolution = resolution
        self.running = False
        self.fps = 15
        self.process = None
        
        # Archivo temporal para el pipe
        self.pipe_file = f"/tmp/camera_{camera_id}_preview.raw"
    
    def run(self):
        """Ejecutar captura continua usando libcamera"""
        self.running = True
        
        try:
            # Comando libcamera para streaming continuo
            cmd = [
                "rpicam-vid",
                "--camera", str(self.camera_id),
                "--width", str(self.resolution[0]),
                "--height", str(self.resolution[1]),
                "--framerate", str(self.fps),
                "--timeout", "0",
                "--nopreview",
                "--codec", "mjpeg",    # ← CAMBIAR A MJPEG
                "--output", "-"
            ]
            
            logger.info(f"Iniciando captura cam{self.camera_id}: {' '.join(cmd)}")
            
            self.process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                bufsize=0
            )
            
            # Buffer para acumular datos MJPEG
            buffer = b''
            start_marker = b'\xff\xd8'  # Inicio JPEG
            end_marker = b'\xff\xd9'    # Fin JPEG
            
            while self.running and self.process.poll() is None:
                try:
                    # Leer datos en chunks
                    chunk = self.process.stdout.read(4096)
                    if not chunk:
                        continue
                        
                    buffer += chunk
                    
                    # Buscar frames JPEG completos
                    while True:
                        start_pos = buffer.find(start_marker)
                        if start_pos == -1:
                            break
                            
                        end_pos = buffer.find(end_marker, start_pos + 2)
                        if end_pos == -1:
                            break
                            
                        # Extraer frame JPEG completo
                        jpeg_data = buffer[start_pos:end_pos + 2]
                        buffer = buffer[end_pos + 2:]
                        
                        # Decodificar JPEG a imagen
                        np_array = np.frombuffer(jpeg_data, dtype=np.uint8)
                        rgb_frame = cv2.imdecode(np_array, cv2.IMREAD_COLOR)
                        
                        if rgb_frame is not None:
                            # Convertir BGR a RGB
                            rgb_frame = cv2.cvtColor(rgb_frame, cv2.COLOR_BGR2RGB)
                            
                            if self.running:
                                self.frame_ready.emit(rgb_frame)
                        
                except Exception as e:
                    if self.running:
                        logger.warning(f"Error procesando frame cam{self.camera_id}: {e}")
                    continue
                    
        except Exception as e:
            self.error_occurred.emit(f"Error iniciando captura cam{self.camera_id}: {e}")
            logger.error(f"Error en LibcameraPreviewThread cam{self.camera_id}: {e}")
        
        finally:
            self.cleanup()
    
    def stop(self):
        """Detener captura"""
        self.running = False
        
    def cleanup(self):
        """Limpiar recursos"""
        if self.process:
            try:
                self.process.terminate()
                self.process.wait(timeout=5)
            except:
                try:
                    self.process.kill()
                    self.process.wait(timeout=2)
                except:
                    pass
            self.process = None
        
        # Limpiar archivo temporal si existe
        if Path(self.pipe_file).exists():
            try:
                os.unlink(self.pipe_file)
            except:
                pass

class CameraPreviewWidget(QWidget):
    """Widget de vista previa para una cámara individual"""
    
    frame_ready = pyqtSignal(np.ndarray)
    
    def __init__(self, camera_name, camera_id, camera_config, parent=None):
        super().__init__(parent)
        self.camera_name = camera_name
        self.camera_id = camera_id
        self.preview_thread = None
        self.current_frame = None
        self.is_previewing = False
        self.config = camera_config
        
        self.init_ui()
        
    def init_ui(self):
        """Inicializar interfaz de usuario"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)
        
        # Título de la cámara
        title_layout = QHBoxLayout()
        
        self.title_label = QLabel(self.camera_name)
        self.title_label.setFont(QFont("Arial", 11, QFont.Bold))
        self.title_label.setAlignment(Qt.AlignLeft)
        title_layout.addWidget(self.title_label)
        
        # Indicador de estado
        self.status_indicator = QLabel("●")
        self.status_indicator.setFont(QFont("Arial", 16, QFont.Bold))
        self.status_indicator.setStyleSheet("color: #F44336;")  # Rojo por defecto
        self.status_indicator.setAlignment(Qt.AlignRight)
        title_layout.addWidget(self.status_indicator)
        
        layout.addLayout(title_layout)
        
        # Frame de video con borde
        video_frame = QFrame()
        video_frame.setFrameStyle(QFrame.StyledPanel | QFrame.Raised)
        video_frame.setLineWidth(2)
        video_frame.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        
        video_layout = QVBoxLayout(video_frame)
        video_layout.setContentsMargins(2, 2, 2, 2)
        
        # Label para mostrar video
        self.video_label = QLabel()
        self.video_label.setMinimumSize(300, 300)  # Más cuadrado
        self.video_label.setMaximumSize(500, 400)  # Mejor proporción
        self.video_label.setScaledContents(False)  # ← NO ESTIRAR
        self.video_label.setAlignment(Qt.AlignCenter)
        self.video_label.setStyleSheet("""
            QLabel {
                background-color: #000000;
                border: 1px solid #CCCCCC;
                color: white;
                font-size: 14px;
            }
        """)
        
        # Mostrar texto por defecto
        self.show_no_signal()
        
        video_layout.addWidget(self.video_label)
        layout.addWidget(video_frame)
        
        # Información de la cámara
        info_layout = QHBoxLayout()
        
        self.info_label = QLabel(f"CAM{self.camera_id} - Desconectada")
        self.info_label.setFont(QFont("Arial", 9))
        self.info_label.setStyleSheet("color: #666666;")
        info_layout.addWidget(self.info_label)
        
        info_layout.addStretch()
        
        self.fps_label = QLabel("0 FPS")
        self.fps_label.setFont(QFont("Arial", 9))
        self.fps_label.setStyleSheet("color: #666666;")
        info_layout.addWidget(self.fps_label)
        
        layout.addLayout(info_layout)
        
        # Variables para cálculo de FPS
        self.frame_count = 0
        self.last_fps_time = time.time()
        self.current_fps = 0
        
        # Timer para actualizar FPS
        self.fps_timer = QTimer()
        self.fps_timer.timeout.connect(self.update_fps_display)
        self.fps_timer.start(1000)  # Actualizar cada segundo
    
    def show_no_signal(self):
        """Mostrar mensaje de sin señal"""
        self.video_label.clear()
        self.video_label.setText(f"Sin señal\n{self.camera_name}")
        self.video_label.setStyleSheet("""
            QLabel {
                background-color: #263238;
                color: #90A4AE;
                font-size: 14px;
                border: 2px dashed #546E7A;
            }
        """)
    
    def show_connecting(self):
        """Mostrar mensaje de conectando"""
        self.video_label.clear()
        self.video_label.setText(f"Conectando...\n{self.camera_name}")
        self.video_label.setStyleSheet("""
            QLabel {
                background-color: #1A237E;
                color: #7986CB;
                font-size: 14px;
                border: 2px solid #3F51B5;
            }
        """)
    
    def start_preview(self):
        """Iniciar vista previa de la cámara"""
        if self.is_previewing:
            return
            
        try:
            self.show_connecting()
            self.status_indicator.setStyleSheet("color: #FF9800;")  # Naranja
            self.info_label.setText(f"CAM{self.camera_id} - Conectando...")
            
            # Determinar qué cámara es para obtener su config de preview
            cam_settings = self.config.left_camera if self.camera_id == self.config.left_camera.camera_id else self.config.right_camera
            preview_res = cam_settings.preview_resolution # <-- Obtener de config (1920x1440)

            self.preview_thread = LibcameraPreviewThread(
                self.camera_id,
                resolution=preview_res # <-- ¡USA LA RESOLUCIÓN CORRECTA!
            )
            
            # Conectar señales
            self.preview_thread.frame_ready.connect(self.on_frame_ready)
            self.preview_thread.error_occurred.connect(self.on_error)
            self.preview_thread.finished.connect(self.on_preview_finished)
            
            # Iniciar captura
            self.preview_thread.start()
            self.is_previewing = True
            
            logger.info(f"Vista previa iniciada para {self.camera_name}")
            
        except Exception as e:
            self.on_error(f"Error iniciando vista previa: {e}")
    
    def stop_preview(self):
        """Detener vista previa de la cámara"""
        if not self.is_previewing:
            return
            
        self.is_previewing = False
        
        if self.preview_thread:
            self.preview_thread.stop()
            
            # Esperar a que termine el hilo
            if self.preview_thread.isRunning():
                self.preview_thread.wait(3000)  # Esperar máximo 3 segundos
                
                # Si no termina, forzar terminación
                if self.preview_thread.isRunning():
                    self.preview_thread.terminate()
                    self.preview_thread.wait(1000)
            
            self.preview_thread = None
        
        self.show_no_signal()
        self.status_indicator.setStyleSheet("color: #F44336;")  # Rojo
        self.info_label.setText(f"CAM{self.camera_id} - Desconectada")
        self.fps_label.setText("0 FPS")
        
        logger.info(f"Vista previa detenida para {self.camera_name}")
    
    def on_frame_ready(self, frame):
        """Callback cuando un frame está listo"""
        try:
            self.current_frame = frame
            
            # Convertir numpy array a QImage
            height, width, channel = frame.shape
            bytes_per_line = 3 * width
            
            q_image = QImage(
                frame.data,
                width,
                height,
                bytes_per_line,
                QImage.Format_RGB888
            )
            
            # Convertir a QPixmap y mostrar
            pixmap = QPixmap.fromImage(q_image)
            scaled_pixmap = pixmap.scaled(
                self.video_label.size(),
                Qt.KeepAspectRatio,  # ← MANTENER ASPECTO
                Qt.SmoothTransformation
            )
            self.video_label.setPixmap(scaled_pixmap)
            
            # Actualizar estado
            if not self.is_previewing:  # Primer frame recibido
                self.status_indicator.setStyleSheet("color: #4CAF50;")  # Verde
                self.info_label.setText(f"CAM{self.camera_id} - Activa")
                self.is_previewing = True
            
            # Incrementar contador de frames
            self.frame_count += 1
            
            # Emitir señal para otros componentes
            self.frame_ready.emit(frame)
            
        except Exception as e:
            logger.error(f"Error procesando frame {self.camera_name}: {e}")
    
    def on_error(self, error_message):
        """Callback cuando ocurre un error"""
        logger.error(f"Error en {self.camera_name}: {error_message}")
        
        self.show_no_signal()
        self.video_label.setText(f"Error\n{self.camera_name}\n{error_message}")
        self.video_label.setStyleSheet("""
            QLabel {
                background-color: #B71C1C;
                color: #FFCDD2;
                font-size: 12px;
                border: 2px solid #F44336;
            }
        """)
        
        self.status_indicator.setStyleSheet("color: #F44336;")  # Rojo
        self.info_label.setText(f"CAM{self.camera_id} - Error")
    
    def on_preview_finished(self):
        """Callback cuando termina la vista previa"""
        self.is_previewing = False
        logger.info(f"Hilo de vista previa terminado para {self.camera_name}")
    
    def update_fps_display(self):
        """Actualizar display de FPS"""
        current_time = time.time()
        time_diff = current_time - self.last_fps_time
        
        if time_diff >= 1.0:
            self.current_fps = self.frame_count / time_diff
            self.fps_label.setText(f"{self.current_fps:.1f} FPS")
            
            self.frame_count = 0
            self.last_fps_time = current_time
    
    def get_current_frame(self):
        """Obtener frame actual para captura"""
        return self.current_frame.copy() if self.current_frame is not None else None
    
    def capture_frame(self, output_file):
        """Capturar frame actual a archivo"""
        if self.current_frame is None:
            raise RuntimeError("No hay frame disponible para captura")
        
        # Convertir RGB a BGR para OpenCV
        bgr_frame = cv2.cvtColor(self.current_frame, cv2.COLOR_RGB2BGR)
        
        # Guardar imagen
        success = cv2.imwrite(output_file, bgr_frame)
        if not success:
            raise RuntimeError(f"Error guardando frame a {output_file}")
        
        return output_file
    
    def closeEvent(self, event):
        """Limpiar al cerrar"""
        self.stop_preview()
        event.accept()
    
    def __del__(self):
        """Destructor - asegurar limpieza"""
        try:
            self.stop_preview()
        except:
            pass

if __name__ == "__main__":
    # Test del widget de preview
    import sys
    from PyQt5.QtWidgets import QApplication, QMainWindow, QVBoxLayout, QWidget
    
    app = QApplication(sys.argv)
    
    # Crear ventana de test
    window = QMainWindow()
    window.setWindowTitle("Test Camera Preview")
    window.resize(800, 600)
    
    central_widget = QWidget()
    window.setCentralWidget(central_widget)
    layout = QVBoxLayout(central_widget)
    
    # Crear widgets de preview
    left_preview = CameraPreviewWidget("Test Camera 0", 0)
    right_preview = CameraPreviewWidget("Test Camera 1", 1)
    
    layout.addWidget(left_preview)
    layout.addWidget(right_preview)
    
    # Iniciar previews
    left_preview.start_preview()
    right_preview.start_preview()
    
    window.show()
    
    try:
        sys.exit(app.exec_())
    finally:
        left_preview.stop_preview()
        right_preview.stop_preview()