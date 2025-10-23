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
    
    # Verificar libcamera
    if os.system("which libcamera-hello > /dev/null 2>&1") != 0:
        requirements.append("libcamera-hello no encontrado. Instala libcamera-apps")
    
    # Verificar Python OpenCV
    try:
        import cv2
        logging.info(f"OpenCV version: {cv2.__version__}")
    except ImportError:
        requirements.append("OpenCV no instalado. Instala python3-opencv")
    
    # Verificar PyQt5
    try:
        from PyQt5 import QtCore
        logging.info(f"PyQt5 version: {QtCore.PYQT_VERSION_STR}")
    except ImportError:
        requirements.append("PyQt5 no instalado. Instala python3-pyqt5")
    
    # Verificar numpy
    try:
        import numpy
        logging.info(f"NumPy version: {numpy.__version__}")
    except ImportError:
        requirements.append("NumPy no instalado. Instala python3-numpy")
    
    return requirements

def check_cameras():
    """Verificar que las cámaras estén conectadas"""
    try:
        # Verificar listado de cámaras con libcamera
        result = os.popen("libcamera-hello --list-cameras 2>/dev/null").read()
        
        if "No cameras available" in result:
            return ["No se detectaron cámaras"]
        
        # Contar cámaras disponibles
        camera_count = result.count(": imx477")  # CORRECTO
        if camera_count == 0:
            # Método alternativo de conteo
            camera_count = result.count(": imx477") + result.count(": IMX477")
        
        if camera_count < 2:
            return [f"Solo se detectaron {camera_count} cámaras. Se necesitan 2 para estéreo"]
        
        logging.info(f"Cámaras detectadas: {camera_count}")
        return []
        
    except Exception as e:
        return [f"Error verificando cámaras: {str(e)}"]

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
    missing_req = check_system_requirements()
    if missing_req:
        msg = QMessageBox()
        msg.setIcon(QMessageBox.Critical)
        msg.setWindowTitle("Requisitos Faltantes")
        msg.setText("Faltan los siguientes requisitos del sistema:")
        msg.setDetailedText("\n".join(missing_req))
        msg.exec_()
        logger.error(f"Requisitos faltantes: {missing_req}")
        return 1
    
    # Verificar cámaras
    camera_issues = check_cameras()
    if camera_issues:
        msg = QMessageBox()
        msg.setIcon(QMessageBox.Warning)
        msg.setWindowTitle("Problemas con Cámaras")
        msg.setText("Se detectaron problemas con las cámaras:")
        msg.setDetailedText("\n".join(camera_issues))
        msg.setStandardButtons(QMessageBox.Ok | QMessageBox.Cancel)
        msg.setDefaultButton(QMessageBox.Cancel)
        
        if msg.exec_() == QMessageBox.Cancel:
            logger.error(f"Problemas con cámaras: {camera_issues}")
            return 1
    
    logger.info("Verificaciones del sistema completadas")
    
    # Cargar configuración de cámaras
    try:
        camera_config = CameraConfig()
        logger.info("Configuración de cámaras cargada")
    except Exception as e:
        msg = QMessageBox()
        msg.setIcon(QMessageBox.Critical)
        msg.setWindowTitle("Error de Configuración")
        msg.setText(f"Error cargando configuración: {str(e)}")
        msg.exec_()
        logger.error(f"Error configuración: {str(e)}")
        return 1
    
    # Crear ventana principal
    try:
        main_window = MainWindow(camera_config)
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