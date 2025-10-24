#!/usr/bin/env python3
"""
Configuración específica para cámaras Arducam HQ 477 (IMX477 12MP)
en Raspberry Pi CM5 para aplicaciones de fotogrametría estéreo
"""

import os
import json
from pathlib import Path
from dataclasses import dataclass
from typing import Tuple, Dict, Any
from utils.logger import get_logger

logger = get_logger(__name__)

@dataclass
class CameraSettings:
    """Configuración de una sola cámara"""
    camera_id: int
    name: str
    sensor_type: str = "IMX477"
    max_resolution: Tuple[int, int] = (4056, 3040)  # 12.3MP máximo
    preview_resolution: Tuple[int, int] = (1920, 1440)  # Para vista previa
    capture_resolution: Tuple[int, int] = (3840, 2880)  # Para captura estéreo
    framerate: int = 15
    exposure_mode: str = "auto"
    awb_mode: str = "auto"
    iso: int = 0  # Auto
    shutter_speed: int = 0  # Auto en microsegundos
    brightness: int = 50
    contrast: int = 50
    saturation: int = 50
    
@dataclass
class StereoConfig:
    """Configuración del sistema estéreo"""
    baseline_mm: float = 100.0  # Separación entre cámaras en mm
    convergence_angle: float = 0.0  # Ángulo de convergencia en grados  
    sync_tolerance_ms: int = 50  # Tolerancia de sincronización
    calibration_board_size: Tuple[int, int] = (9, 6)  # Esquinas internas del tablero
    calibration_square_size_mm: float = 24.0  # Tamaño del cuadrado en mm
    min_calibration_images: int = 10
    max_calibration_images: int = 30
    calibration_data_path: str = "data/calibration"

class CameraConfig:
    """Clase principal de configuración de cámaras"""
    
    def __init__(self, config_file: str = None):
        """Inicializar configuración"""
        self.config_file = config_file or "config/camera_settings.json"
        self.config_dir = Path("data/calibration")
        
        # Configuraciones por defecto para Arducam HQ 477
        self.left_camera = CameraSettings(
            camera_id=0,
            name="Left Camera (CAM0)",
            sensor_type="IMX477"
        )
        
        self.right_camera = CameraSettings(
            camera_id=1, 
            name="Right Camera (CAM1)",
            sensor_type="IMX477"
        )
        
        self.stereo = StereoConfig()
        
        # Parámetros de calibración (se cargan/guardan automáticamente)
        self.calibration_data = {
            "left_camera_matrix": None,
            "left_distortion": None,
            "right_camera_matrix": None,
            "right_distortion": None,
            "rotation_matrix": None,
            "translation_vector": None,
            "essential_matrix": None,
            "fundamental_matrix": None,
            "calibration_date": None,
            "calibration_error": None,
            "is_calibrated": False
        }

        # Cargar configuración si existe
        self.load_config()

        # NUEVO: Cargar calibración automáticamente si existe
        calibration_loaded = self.load_calibration()
        if calibration_loaded:
            logger.info(f"✅ Calibración cargada automáticamente desde {self.config_dir / 'calibration_data.json'}")
            calib_info = self.get_calibration_info()
            logger.info(f"   📊 Error: {calib_info['error']:.3f} px | Imágenes: {calib_info['num_images']} | Fecha: {calib_info['date']}")
        else:
            logger.warning("⚠️ No se encontró calibración previa. Se requiere calibración.")

        # Verificar disponibilidad de libcamera (opcional - no falla si no hay cámaras)
        self.cameras_available = self._verify_libcamera()
    
    def _verify_libcamera(self) -> bool:
        """Verificar que libcamera funciona y detecta las cámaras.
        Retorna True si las cámaras están disponibles, False si no."""
        try:
            result = os.popen("libcamera-hello --list-cameras 2>/dev/null").read()

            if "No cameras available" in result or len(result.strip()) == 0:
                logger.warning("No se detectaron cámaras con libcamera (modo de solo procesamiento)")
                return False

            # Verificar que hay al menos 2 cámaras
            camera_count = result.count(": imx477") + result.count(": IMX477")
            if camera_count < 2:
                logger.warning(f"Solo se detectaron {camera_count} cámaras. Se necesitan 2 para captura estéreo.")
                return False

            logger.info(f"✅ {camera_count} cámaras detectadas y listas")
            return True

        except Exception as e:
            logger.warning(f"No se pudo verificar libcamera: {e} (modo de solo procesamiento)")
            return False
    
    def get_capture_settings_for_op(self, operation: str) -> Dict[str, Any]:
        """Obtener resolución y framerate según la operación"""
        if operation == "calibration":
            # Usar la resolución de PREVIEW para calibración
            resolution = self.left_camera.preview_resolution # Asume que ambas cámaras usan la misma para preview
            framerate = self.left_camera.framerate # O la que uses para preview
            # Ahora 'logger' está definido gracias a la línea añadida al principio del archivo
            logger.debug(f"get_capture_settings_for_op: Calibration -> Res: {resolution}, FPS: {framerate}")
        elif operation == "capture":
            # Usar la resolución de CAPTURA para el modelo 3D
            resolution = self.left_camera.capture_resolution # Asume que ambas cámaras usan la misma para captura
            framerate = self.left_camera.framerate # O la que uses para captura
            logger.debug(f"get_capture_settings_for_op: Capture -> Res: {resolution}, FPS: {framerate}")
        else:
            # Por defecto, usar configuración de captura (o puedes lanzar un error)
            resolution = self.left_camera.capture_resolution
            framerate = self.left_camera.framerate
            logger.warning(f"get_capture_settings_for_op: Operación desconocida '{operation}', usando config de captura.")

        return {
            "resolution": resolution,
            "framerate": framerate
            # Puedes añadir otros settings si varían por operación
        }

    def get_libcamera_cmd(self, camera_id: int, operation: str = "preview",
                        duration_ms: int = 5000, output_file: str = None) -> str:
        """Generar comando libcamera para operaciones específicas"""

        camera_settings = self.left_camera if camera_id == 0 else self.right_camera

        if operation == "preview":
            # --- LÓGICA DE PREVIEW ---
            # Usa "libcamera-hello" o "rpicam-vid" (tu main_window usa rpicam-vid)
            # PERO usa la preview_resolution (que ahora es 1920x1440)
            # CORRECCIÓN: Usa rpicam-vid para consistencia con CameraPreviewWidget
            cmd = f"rpicam-vid --camera {camera_id} -t 0 --nopreview --codec mjpeg --output -" # Salida a stdout
            cmd += f" --width {camera_settings.preview_resolution[0]}"
            cmd += f" --height {camera_settings.preview_resolution[1]}"

        elif operation == "capture":
            # --- LÓGICA DE CAPTURA (PARA MODELO 3D - ALTA RESOLUCIÓN) ---
            if not output_file:
                output_file = f"capture_cam{camera_id}.jpg"
            cmd = f"libcamera-jpeg --camera {camera_id} -o {output_file}"

            # Asegurarse de que usa capture_resolution (3840x2880)
            cmd += f" --width {camera_settings.capture_resolution[0]}"
            cmd += f" --height {camera_settings.capture_resolution[1]}"
            cmd += f" -t {duration_ms}" # Mantener el timeout aquí

        elif operation == "calibration":
            # --- LÓGICA DE CALIBRACIÓN (USA PREVIEW_RESOLUTION) --- # <--- CAMBIO AQUÍ
            if not output_file:
                output_file = f"calibration_cam{camera_id}.jpg"
            cmd = f"libcamera-jpeg --camera {camera_id} -o {output_file}"

            # ✅ EL ARREGLO ESTÁ AQUÍ:
            # Asegurarse de que usa preview_resolution (1920x1440)
            cmd += f" --width {camera_settings.preview_resolution[0]}"  # <--- CAMBIADO
            cmd += f" --height {camera_settings.preview_resolution[1]}" # <--- CAMBIADO
            cmd += f" -t {duration_ms}" # Mantener el timeout aquí
        else:
            raise ValueError(f"Operación desconocida: {operation}")

        # Agregar configuraciones adicionales (igual para todas)
        cmd += f" --framerate {camera_settings.framerate}"

        if camera_settings.iso > 0:
            cmd += f" --gain {camera_settings.iso / 100.0}" # gain es float

        if camera_settings.shutter_speed > 0:
            cmd += f" --shutter {camera_settings.shutter_speed}" # shutter es microsegundos

        # Añadir enfoque automático si es necesario (puede ayudar)
        # cmd += " --autofocus-mode auto" # Descomenta si quieres probar

        return cmd
    
    def save_config(self):
        """Guardar configuración a archivo JSON"""
        config_data = {
            "left_camera": {
                "camera_id": self.left_camera.camera_id,
                "name": self.left_camera.name,
                "sensor_type": self.left_camera.sensor_type,
                "max_resolution": self.left_camera.max_resolution,
                "preview_resolution": self.left_camera.preview_resolution,
                "capture_resolution": self.left_camera.capture_resolution,
                "framerate": self.left_camera.framerate,
                "exposure_mode": self.left_camera.exposure_mode,
                "awb_mode": self.left_camera.awb_mode,
                "iso": self.left_camera.iso,
                "shutter_speed": self.left_camera.shutter_speed,
                "brightness": self.left_camera.brightness,
                "contrast": self.left_camera.contrast,
                "saturation": self.left_camera.saturation
            },
            "right_camera": {
                "camera_id": self.right_camera.camera_id,
                "name": self.right_camera.name,
                "sensor_type": self.right_camera.sensor_type,
                "max_resolution": self.right_camera.max_resolution,
                "preview_resolution": self.right_camera.preview_resolution,
                "capture_resolution": self.right_camera.capture_resolution,
                "framerate": self.right_camera.framerate,
                "exposure_mode": self.right_camera.exposure_mode,
                "awb_mode": self.right_camera.awb_mode,
                "iso": self.right_camera.iso,
                "shutter_speed": self.right_camera.shutter_speed,
                "brightness": self.right_camera.brightness,
                "contrast": self.right_camera.contrast,
                "saturation": self.right_camera.saturation
            },
            "stereo": {
                "baseline_mm": self.stereo.baseline_mm,
                "convergence_angle": self.stereo.convergence_angle,
                "sync_tolerance_ms": self.stereo.sync_tolerance_ms,
                "calibration_board_size": self.stereo.calibration_board_size,
                "calibration_square_size_mm": self.stereo.calibration_square_size_mm,
                "min_calibration_images": self.stereo.min_calibration_images,
                "max_calibration_images": self.stereo.max_calibration_images
            }
        }
        
        # Crear directorio si no existe
        Path(self.config_file).parent.mkdir(parents=True, exist_ok=True)
        
        with open(self.config_file, 'w') as f:
            json.dump(config_data, f, indent=4)
    
    def load_config(self):
        """Cargar configuración desde archivo JSON"""
        if not Path(self.config_file).exists():
            return  # Usar valores por defecto
        
        try:
            with open(self.config_file, 'r') as f:
                config_data = json.load(f)
            
            # Cargar configuración de cámara izquierda
            if "left_camera" in config_data:
                left_config = config_data["left_camera"]
                self.left_camera = CameraSettings(**left_config)
            
            # Cargar configuración de cámara derecha
            if "right_camera" in config_data:
                right_config = config_data["right_camera"] 
                self.right_camera = CameraSettings(**right_config)
            
            # Cargar configuración estéreo
            if "stereo" in config_data:
                stereo_config = config_data["stereo"]
                self.stereo = StereoConfig(**stereo_config)
                
        except Exception as e:
            print(f"Error cargando configuración: {e}. Usando valores por defecto.")
    
    def save_calibration(self, calibration_data: Dict[str, Any]):
        """Guardar datos de calibración"""
        self.calibration_data.update(calibration_data)
        self.calibration_data["is_calibrated"] = True
        
        calibration_file = self.config_dir / "calibration_data.json"
        calibration_file.parent.mkdir(parents=True, exist_ok=True)
        
        # Convertir arrays numpy a listas para JSON
        json_data = {}
        for key, value in self.calibration_data.items():
            if hasattr(value, 'tolist'):  # Es numpy array
                json_data[key] = value.tolist()
            else:
                json_data[key] = value
        
        with open(calibration_file, 'w') as f:
            json.dump(json_data, f, indent=4)
    
    def load_calibration(self) -> bool:
        """Cargar datos de calibración. Retorna True si se cargó exitosamente"""
        calibration_file = self.config_dir / "calibration_data.json"
        
        if not calibration_file.exists():
            return False
        
        try:
            with open(calibration_file, 'r') as f:
                json_data = json.load(f)
            
            # Convertir listas de vuelta a numpy arrays si es necesario
            import numpy as np

            # Lista completa de matrices que necesitan ser convertidas a numpy arrays
            matrix_keys = [
                'left_camera_matrix', 'left_distortion',
                'right_camera_matrix', 'right_distortion',
                'rotation_matrix', 'translation_vector',
                'essential_matrix', 'fundamental_matrix',
                # CRÍTICO: Agregar las matrices de rectificación
                'rectification_left', 'rectification_right',
                'projection_left', 'projection_right',
                'disparity_to_depth_matrix'  # ← ESTO ES LO QUE FALTABA
            ]

            for key, value in json_data.items():
                if isinstance(value, list) and key in matrix_keys:
                    json_data[key] = np.array(value)

            self.calibration_data.update(json_data)
            return self.calibration_data.get("is_calibrated", False)
            
        except Exception as e:
            print(f"Error cargando calibración: {e}")
            return False
    
    def is_calibrated(self) -> bool:
        """Verificar si el sistema está calibrado"""
        return self.calibration_data.get("is_calibrated", False)

    def get_calibration_info(self) -> Dict[str, Any]:
        """Obtener información detallada de la calibración actual"""
        if not self.is_calibrated():
            return {
                "is_calibrated": False,
                "error": None,
                "num_images": 0,
                "date": None,
                "quality": "No calibrado",
                "baseline_mm": None,
                "issues": ["Sistema no calibrado"]
            }

        from datetime import datetime

        # Extraer información
        error = self.calibration_data.get("calibration_error", 0)
        num_images = self.calibration_data.get("images_used", 0)
        date_str = self.calibration_data.get("calibration_date", "Desconocida")
        baseline_m = self.calibration_data.get("baseline_meters", 0)
        is_good_quality = self.calibration_data.get("is_good_quality", False)
        quality_issues = self.calibration_data.get("quality_issues", [])

        # Parsear fecha
        try:
            date_obj = datetime.fromisoformat(date_str)
            date_formatted = date_obj.strftime("%d/%m/%Y %H:%M")
        except:
            date_formatted = date_str

        # Determinar calidad
        if error < 0.5:
            quality = "Excelente"
        elif error < 1.0:
            quality = "Buena"
        elif error < 2.0:
            quality = "Aceptable"
        else:
            quality = "Pobre"

        return {
            "is_calibrated": True,
            "error": error,
            "num_images": num_images,
            "date": date_formatted,
            "quality": quality,
            "baseline_mm": baseline_m * 1000 if baseline_m else None,
            "is_good_quality": is_good_quality,
            "issues": quality_issues if quality_issues else []
        }

    def get_capture_settings(self) -> Dict[str, Any]:
        """Obtener configuraciones optimizadas para captura estéreo"""
        return {
            "left_resolution": self.left_camera.capture_resolution,
            "right_resolution": self.right_camera.capture_resolution,
            "framerate": min(self.left_camera.framerate, self.right_camera.framerate),
            "sync_tolerance_ms": self.stereo.sync_tolerance_ms,
            "baseline_mm": self.stereo.baseline_mm
        }

# Función de conveniencia para crear configuración por defecto
def create_default_config() -> CameraConfig:
    """Crear configuración por defecto para Arducam HQ 477"""
    config = CameraConfig()
    config.save_config()
    return config

if __name__ == "__main__":
    # Test de configuración
    print("Probando configuración de cámaras Arducam HQ 477...")
    
    try:
        config = create_default_config()
        print("✓ Configuración creada exitosamente")
        
        # Probar comandos libcamera
        preview_cmd = config.get_libcamera_cmd(0, "preview", 1000)
        print(f"✓ Comando preview: {preview_cmd}")
        
        capture_cmd = config.get_libcamera_cmd(0, "capture", 2000, "test.jpg")
        print(f"✓ Comando capture: {capture_cmd}")
        
    except Exception as e:
        print(f"✗ Error: {e}")
        sys.exit(1)
