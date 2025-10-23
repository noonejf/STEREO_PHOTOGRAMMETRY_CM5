# processing/__init__.py
"""
Módulo de procesamiento 3D para el sistema de fotogrametría estéreo CM5
Implementa algoritmos de visión estéreo y generación de nubes de puntos
"""

from .stereo_processor import StereoProcessor
from .point_cloud_generator import PointCloudExporter, PointCloudProcessor

__version__ = "1.0.0" 
__all__ = ['StereoProcessor', 'PointCloudExporter', 'PointCloudProcessor']