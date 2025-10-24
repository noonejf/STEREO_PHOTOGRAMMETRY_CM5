#!/usr/bin/env python3
"""
Sistema de Fotogrametría Estéreo para Raspberry Pi CM5
Cámaras: Arducam HQ 477 (IMX477 12MP) x2
Autor: Tu Proyecto Espacial
"""

import sys
import os
import logging
from pathlib import Path

# Agregar directorio del proyecto al path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from PyQt5.QtWidgets import QApplication, QMessageBox
from PyQt5.QtCore import Qt, QDir
from PyQt5.QtGui import QIcon

# Imports locales
from gui.main_window import MainWindow
from utils.logger import setup_logger
from config.camera_config import CameraConfig

def check_system_requirements():
    """Verificar que el sistema tiene todos los requisitos"""
    requirements = []
    warnings = []

    # Verificar libcamera (opcional - solo para captura)
    if os.system("which libcamera-hello > /dev/null 2>&1") != 0:
        if sys.platform != "win32":  # En Linux/Raspberry Pi es importante
            warnings.append("libcamera-hello no encontrado. Las funciones de captura estarán deshabilitadas.")
        # En Windows, no es un problema - solo procesaremos

    # Verificar Python OpenCV (REQUERIDO)
    try:
        import cv2
        logging.info(f"OpenCV version: {cv2.__version__}")
    except ImportError:
        requirements.append("OpenCV no instalado. Instala python3-opencv o opencv-python")

    # Verificar PyQt5 (REQUERIDO)
    try:
        from PyQt5 import QtCore
        logging.info(f"PyQt5 version: {QtCore.PYQT_VERSION_STR}")
    except ImportError:
        requirements.append("PyQt5 no instalado. Instala python3-pyqt5 o PyQt5")

    # Verificar numpy (REQUERIDO)
    try:
        import numpy
        logging.info(f"NumPy version: {numpy.__version__}")
    except ImportError:
        requirements.append("NumPy no instalado. Instala python3-numpy o numpy")

    return requirements, warnings


def create_directories():
    """Crear directorios necesarios"""
    dirs = [
        "data/calibration",
        "data/captures", 
        "data/results",
        "logs"
    ]
    
    for dir_path in dirs:
        Path(dir_path).mkdir(parents=True, exist_ok=True)

def main():
    """Función principal"""
    # Configurar logging
    setup_logger()
    logger = logging.getLogger(__name__)
    logger.info("=== Iniciando Sistema de Fotogrametría Estéreo CM5 ===")
    
    # Crear directorios necesarios
    create_directories()
    
    # Crear aplicación Qt
    app = QApplication(sys.argv)
    app.setApplicationName("Stereo Photogrammetry CM5")
    app.setApplicationVersion("1.0")
    app.setOrganizationName("Tu Proyecto Espacial")
    
    # Configurar estilo de aplicación
    app.setStyle("Fusion")
    
    # Verificar requisitos del sistema
    missing_req, warnings = check_system_requirements()

    # Mostrar errores críticos (OpenCV, PyQt5, NumPy)
    if missing_req:
        msg = QMessageBox()
        msg.setIcon(QMessageBox.Critical)
        msg.setWindowTitle("Requisitos Faltantes")
        msg.setText("Faltan los siguientes requisitos críticos del sistema:")
        msg.setDetailedText("\n".join(missing_req))
        msg.exec_()
        logger.error(f"Requisitos faltantes: {missing_req}")
        return 1

    # Mostrar advertencias (libcamera) pero continuar
    if warnings:
        logger.warning(f"Advertencias del sistema: {warnings}")

    logger.info("Verificaciones del sistema completadas")

    # Cargar configuración de cámaras
    try:
        camera_config = CameraConfig()
        cameras_available = camera_config.cameras_available
        logger.info(f"Configuración cargada (Cámaras: {'Disponibles' if cameras_available else 'No disponibles'})")

        # Mostrar diálogo si no hay cámaras disponibles
        if not cameras_available:
            msg = QMessageBox()
            msg.setIcon(QMessageBox.Information)
            msg.setWindowTitle("Modo de Solo Procesamiento")
            msg.setText("Sistema iniciado en modo de solo procesamiento")
            msg.setInformativeText(
                "No se detectaron cámaras. Podrás procesar capturas existentes pero no realizar nuevas capturas.\n\n"
                "Este modo es ideal para procesar fotos tomadas en Raspberry Pi desde una computadora más potente."
            )
            msg.exec_()

    except Exception as e:
        msg = QMessageBox()
        msg.setIcon(QMessageBox.Critical)
        msg.setWindowTitle("Error de Configuración")
        msg.setText(f"Error crítico cargando configuración: {str(e)}")
        msg.exec_()
        logger.error(f"Error configuración: {str(e)}")
        return 1
    
    # Crear ventana principal
    try:
        main_window = MainWindow(camera_config, cameras_available=cameras_available)
        main_window.show()
        logger.info("Ventana principal creada y mostrada")
    except Exception as e:
        msg = QMessageBox()
        msg.setIcon(QMessageBox.Critical)
        msg.setWindowTitle("Error de Inicialización")
        msg.setText(f"Error creando ventana principal: {str(e)}")
        msg.exec_()
        logger.error(f"Error ventana principal: {str(e)}")
        return 1
    
    # Ejecutar aplicación
    logger.info("Iniciando bucle principal de aplicación")
    try:
        exit_code = app.exec_()
        logger.info(f"Aplicación terminada con código: {exit_code}")
        return exit_code
    except KeyboardInterrupt:
        logger.info("Aplicación interrumpida por usuario")
        return 0
    except Exception as e:
        logger.error(f"Error en bucle principal: {str(e)}")
        return 1

if __name__ == "__main__":
    sys.exit(main())