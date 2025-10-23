# config/__init__.py
"""
Módulo de configuración para el sistema de fotogrametría estéreo CM5
"""

from .camera_config import CameraConfig, create_default_config

__version__ = "1.0.0"
__all__ = ['CameraConfig', 'create_default_config']

