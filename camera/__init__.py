# camera/__init__.py
"""
Módulo de manejo de cámaras para el sistema de fotogrametría estéreo CM5
Soporta cámaras Arducam HQ 477 (IMX477) en Raspberry Pi CM5
"""

from .stereo_camera import StereoCamera
from .camera_calibration import CameraCalibrator

__version__ = "1.0.0"
__all__ = ['StereoCamera', 'CameraCalibrator']