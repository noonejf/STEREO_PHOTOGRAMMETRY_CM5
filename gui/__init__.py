# gui/__init__.py
"""
Módulo de interfaz gráfica para el sistema de fotogrametría estéreo CM5
Basado en PyQt5 para Raspberry Pi CM5
"""

from .main_window import MainWindow
from .camera_preview import CameraPreviewWidget
from .calibration_dialog import CalibrationDialog
from .processing_dialog import ProcessingDialog

__version__ = "1.0.0"
__all__ = [
    'MainWindow',
    'CameraPreviewWidget', 
    'CalibrationDialog',
    'ProcessingDialog'
]