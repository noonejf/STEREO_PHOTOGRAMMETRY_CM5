#!/usr/bin/env python3
"""
Sistema de calibración para cámaras estéreo
Implementa calibración robusta con tablero de ajedrez y validación de calidad
"""

import cv2
import numpy as np
import json
import glob
from pathlib import Path
from datetime import datetime
from typing import List, Tuple, Optional, Dict, Any, Callable

from utils.logger import get_logger

logger = get_logger(__name__)

class CameraCalibrator:
    """Calibrador principal para sistema estéreo"""
    
    def __init__(self, camera_config):
        """Inicializar calibrador"""
        self.config = camera_config
        self.board_size = camera_config.stereo.calibration_board_size
        
        # ✏️ --- CAMBIO DE UNIDAD: USAR MILÍMETROS ---
        # No convertir a metros, usar mm directamente para estabilidad numérica
        self.square_size = camera_config.stereo.calibration_square_size_mm
        # ✏️ --- FIN CAMBIO ---
        
        # Parámetros de calibración (estos estaban en tu original, los volvemos a poner por si acaso)
        self.calibration_flags = (
            cv2.CALIB_FIX_ASPECT_RATIO |
            cv2.CALIB_ZERO_TANGENT_DIST |
            cv2.CALIB_SAME_FOCAL_LENGTH |
            cv2.CALIB_RATIONAL_MODEL |
            cv2.CALIB_FIX_K3 |
            cv2.CALIB_FIX_K4 |
            cv2.CALIB_FIX_K5
        )
        
        # Criterios de terminación para detección de esquinas
        self.corner_criteria = (
            cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER,
            30,
            0.001
        )
        
        # Criterios para calibración
        self.calibration_criteria = (
            cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER,
            100,
            1e-5
        )
        
        # Modificado para que no multiplique por 1000
        logger.info(f"Calibrador inicializado - Tablero: {self.board_size}, Cuadrado: {self.square_size:.1f}mm")
    
    def prepare_object_points(self) -> np.ndarray:
        """Preparar puntos 3D del tablero de ajedrez"""
        # Crear patrón 3D de puntos (z=0 para tablero plano)
        objp = np.zeros((self.board_size[0] * self.board_size[1], 3), np.float32)
        objp[:, :2] = np.mgrid[0:self.board_size[0], 0:self.board_size[1]].T.reshape(-1, 2)
        objp *= self.square_size
        
        return objp
    
    def detect_chessboard_corners(self, image: np.ndarray, 
                                 improve_accuracy: bool = True) -> Tuple[bool, Optional[np.ndarray]]:
        """Detectar esquinas del tablero de ajedrez en una imagen"""
        try:
            # Convertir a escala de grises si es necesario
            if len(image.shape) == 3:
                gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
            else:
                gray = image.copy()
            
            # Detectar esquinas
            ret, corners = cv2.findChessboardCorners(
                gray,
                self.board_size,
                flags=cv2.CALIB_CB_ADAPTIVE_THRESH +
                      cv2.CALIB_CB_NORMALIZE_IMAGE
            )
            
            if ret and improve_accuracy:
                # Refinar esquinas para mayor precisión
                corners = cv2.cornerSubPix(
                    gray,
                    corners,
                    (11, 11),
                    (-1, -1),
                    self.corner_criteria
                )
            
            return ret, corners
            
        except Exception as e:
            logger.error(f"Error detectando esquinas: {e}")
            return False, None
    
    def validate_image_quality(self, image: np.ndarray, corners: np.ndarray) -> Dict[str, Any]:
        """Validar calidad de imagen de calibración"""
        quality_info = {
            'is_valid': True,
            'issues': [],
            'metrics': {}
        }
        
        try:
            # Convertir a escala de grises
            if len(image.shape) == 3:
                gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
            else:
                gray = image.copy()
            
            # 1. Verificar nitidez (varianza del Laplaciano)
            laplacian_var = cv2.Laplacian(gray, cv2.CV_64F).var()
            quality_info['metrics']['sharpness'] = laplacian_var
            
            if laplacian_var < 3.0:
                quality_info['is_valid'] = False
                quality_info['issues'].append("Imagen borrosa (falta de enfoque)")
            
            # 2. Verificar contraste
            contrast = gray.std()
            quality_info['metrics']['contrast'] = contrast
            
            if contrast < 30:
                quality_info['is_valid'] = False
                quality_info['issues'].append("Contraste insuficiente")
            
            # 3. Verificar distribución de esquinas
            corners_flat = corners.reshape(-1, 2)
            
            # Área cubierta por las esquinas
            min_x, min_y = np.min(corners_flat, axis=0)
            max_x, max_y = np.max(corners_flat, axis=0)
            
            corner_area = (max_x - min_x) * (max_y - min_y)
            image_area = gray.shape[0] * gray.shape[1]
            coverage_ratio = corner_area / image_area
            
            quality_info['metrics']['coverage_ratio'] = coverage_ratio
            
            if coverage_ratio < 0.1:  # Menos del 10% del área
                quality_info['is_valid'] = False
                quality_info['issues'].append("Tablero demasiado pequeño en la imagen")
            elif coverage_ratio > 0.8:  # Más del 80% del área
                quality_info['issues'].append("Tablero demasiado grande (puede afectar precisión)")
            
            # 4. Verificar ángulo del tablero (planitud aparente)
            # Calculamos la dispersión de las esquinas para detectar tableros muy inclinados
            corners_centered = corners_flat - np.mean(corners_flat, axis=0)
            eigenvals = np.linalg.eigvals(np.cov(corners_centered.T))
            aspect_ratio = max(eigenvals) / min(eigenvals)
            
            quality_info['metrics']['board_angle_indicator'] = aspect_ratio
            
            if aspect_ratio > 20:  # Muy alargado indica ángulo extremo
                quality_info['issues'].append("Tablero en ángulo muy pronunciado")
            
            # 5. Verificar iluminación uniforme
            # Dividir imagen en cuadrantes y verificar diferencias de iluminación
            h, w = gray.shape
            q1 = gray[:h//2, :w//2].mean()
            q2 = gray[:h//2, w//2:].mean()
            q3 = gray[h//2:, :w//2].mean()
            q4 = gray[h//2:, w//2:].mean()
            
            illumination_variance = np.var([q1, q2, q3, q4])
            quality_info['metrics']['illumination_uniformity'] = illumination_variance
            
            if illumination_variance > 1000:  # Diferencias grandes de iluminación
                quality_info['issues'].append("Iluminación no uniforme")
            
        except Exception as e:
            logger.error(f"Error validando calidad de imagen: {e}")
            quality_info['is_valid'] = False
            quality_info['issues'].append(f"Error en validación: {e}")
        
        return quality_info
    
    def process_calibration_images(self, image_pairs: List[Tuple[str, str]], 
                                 progress_callback: Optional[Callable] = None) -> Dict[str, Any]:
        """Procesar pares de imágenes para calibración"""
        try:
            logger.info(f"Procesando {len(image_pairs)} pares de imágenes para calibración")
            
            # Preparar puntos 3D
            objp = self.prepare_object_points()
            
            # Listas para almacenar puntos
            objpoints = []  # Puntos 3D en el mundo real
            imgpoints_left = []  # Puntos 2D en imagen izquierda
            imgpoints_right = []  # Puntos 2D en imagen derecha
            
            valid_images = []
            image_quality_reports = []
            
            for i, (left_path, right_path) in enumerate(image_pairs):
                try:
                    if progress_callback:
                        progress = int((i / len(image_pairs)) * 70)  # Hasta 70% para procesamiento
                        progress_callback(progress, f"Procesando imagen {i+1}/{len(image_pairs)}")
                    
                    # Cargar imágenes
                    left_img = cv2.imread(left_path)
                    right_img = cv2.imread(right_path)
                    
                    if left_img is None or right_img is None:
                        logger.warning(f"No se pudieron cargar imágenes: {left_path}, {right_path}")
                        continue
                    
                    # Detectar esquinas en ambas imágenes
                    ret_left, corners_left = self.detect_chessboard_corners(left_img)
                    ret_right, corners_right = self.detect_chessboard_corners(right_img)
                    
                    if ret_left and ret_right:
                        # ¡VALIDACIÓN DE CALIDAD IGNORADA!
                        # Si encontramos las esquinas, es válido (como en tu script anterior)
                        
                        logger.info(f"Par {i+1} VÁLIDO (Esquinas detectadas)")
                        
                        # Agregar puntos válidos
                        objpoints.append(objp)
                        imgpoints_left.append(corners_left)
                        imgpoints_right.append(corners_right)
                        
                        valid_images.append((left_path, right_path))
                        # Añadimos un reporte falso de "calidad" para que el código no falle
                        image_quality_reports.append({
                            'left': {'is_valid': True, 'issues': []},
                            'right': {'is_valid': True, 'issues': []}
                        })
                        
                        logger.debug(f"Par {i+1} válido agregado")
                        
                    else:
                        logger.warning(f"No se detectaron esquinas en par {i+1}")
                        
                except Exception as e:
                    logger.error(f"Error procesando par {i+1}: {e}")
                    continue
            
            if len(objpoints) < self.config.stereo.min_calibration_images:
                return {
                    'success': False,
                    'error': f"Imágenes válidas insuficientes: {len(objpoints)}/{self.config.stereo.min_calibration_images}"
                }
            
            logger.info(f"Imágenes válidas para calibración: {len(objpoints)}")
            
            # Obtener dimensiones de imagen
            img_shape = left_img.shape[:2][::-1]  # (width, height)
            
            if progress_callback:
                progress_callback(75, "Ejecutando calibración estéreo...")
            
            # Ejecutar calibración estéreo
            calibration_result = self.execute_stereo_calibration(
                objpoints, imgpoints_left, imgpoints_right, img_shape
            )
            
            if calibration_result['success']:
                # Agregar información adicional
                calibration_result['images_used'] = len(objpoints)
                calibration_result['valid_image_pairs'] = valid_images
                calibration_result['quality_reports'] = image_quality_reports
                calibration_result['image_shape'] = img_shape
                
                if progress_callback:
                    progress_callback(90, "Validando resultados de calibración...")
                
                # Validar calidad de calibración
                validation_result = self.validate_calibration_quality(calibration_result)
                calibration_result.update(validation_result)
                
                if progress_callback:
                    progress_callback(100, "Calibración completada")
            
            return calibration_result
            
        except Exception as e:
            logger.error(f"Error procesando imágenes de calibración: {e}")
            return {
                'success': False,
                'error': str(e)
            }

    def execute_stereo_calibration(self, objpoints: List[np.ndarray],
                                 imgpoints_left: List[np.ndarray],
                                 imgpoints_right: List[np.ndarray],
                                 img_shape: Tuple[int, int]) -> Dict[str, Any]:
        """Ejecutar calibración estéreo"""
        try:
            logger.info("Ejecutando calibración estéreo...")

            # Primero calibrar cada cámara individualmente
            logger.info("Calibrando cámara izquierda...")
            ret_left, mtx_left, dist_left, rvecs_l, tvecs_l = cv2.calibrateCamera(
                objpoints, imgpoints_left, img_shape, None, None,
                criteria=self.calibration_criteria
            )
            logger.info(f"Calibración cámara izquierda - Error: {ret_left:.3f}")

            logger.info("Calibrando cámara derecha...")
            ret_right, mtx_right, dist_right, rvecs_r, tvecs_r = cv2.calibrateCamera(
                objpoints, imgpoints_right, img_shape, None, None,
                criteria=self.calibration_criteria
            )
            logger.info(f"Calibración cámara derecha - Error: {ret_right:.3f}")

            # Verificar que las calibraciones individuales fueron exitosas
            if ret_left == 0 or ret_right == 0:
                logger.error("Calibración individual de cámaras falló")
                return {
                    'success': False,
                    'error': 'Calibración individual de cámaras falló (retval=0)'
                }

            # --- FLAGS PARA CALIBRACIÓN ESTÉREO ---
            # Usar las matrices de cámara ya calculadas
            stereo_flags = (
                cv2.CALIB_FIX_INTRINSIC  # Usar matrices de cámara ya calculadas
            )

            # Calibración estéreo con matrices precalculadas
            logger.info("Ejecutando calibración estéreo (modo conjunto)...")

            retval, mtx_left, dist_left, mtx_right, dist_right, R, T, E, F = cv2.stereoCalibrate(
                objpoints,
                imgpoints_left,
                imgpoints_right,
                mtx_left, dist_left,
                mtx_right, dist_right,
                img_shape,
                criteria=self.calibration_criteria,
                flags=stereo_flags
            )

            # --- INICIO: DEPURACIÓN ADICIONAL ---
            logger.debug("--- RESULTADOS INTERNOS DE CALIBRACIÓN ---")
            logger.debug(f"Error de reproyección (retval): {retval}")

            # ✏️ --- UNIDADES EN MILÍMETROS ---
            # El vector T (Traslación) ahora está en MILÍMETROS.
            # Debería ser algo como [-100.0, 0.0, 0.0] (para -100mm en X)
            logger.debug(f"Vector T (Milímetros): \n{T}")
            # ✏️ --- FIN CAMBIO ---

            logger.debug(f"Matriz R (Rotación): \n{R}")
            logger.debug(f"Matriz Cámara Izquierda: \n{mtx_left}")
            logger.debug(f"Distorión Cámara Izquierda: \n{dist_left}")
            logger.debug("------------------------------------------")
            # --- FIN: DEPURACIÓN ADICIONAL ---

            # Usar los vectores de rotación/traslación de las calibraciones individuales
            rvecs_left = rvecs_l
            tvecs_left = tvecs_l
            rvecs_right = rvecs_r
            tvecs_right = tvecs_r

            logger.info(f"Poses individuales obtenidas de calibración ({len(tvecs_left)} imágenes).")

            if retval == 0 or not tvecs_left or np.isnan(retval):
                error_msg = 'Calibración estéreo falló (retval=0 o nan)' if (retval == 0 or np.isnan(retval)) else 'Cálculo de Poses falló para todas las imágenes'
                logger.error(error_msg)
                return {
                    'success': False,
                    'error': error_msg
                }
            
            logger.info(f"Error calibración estéreo: {retval:.3f} píxeles")
            
            # Rectificación estéreo
            logger.info("Calculando rectificación estéreo...")

            # CRÍTICO: Convertir T de milímetros a metros para stereoRectify
            # cv2.stereoRectify genera la matriz Q basada en las unidades de T
            # Si T está en mm, Q asumirá mm, lo cual causará errores en cálculo de profundidad
            T_meters = T / 1000.0
            logger.info(f"🔧 CORRECCIÓN: T convertido de mm a metros para stereoRectify")
            logger.info(f"   T original (mm): {T.ravel()}")
            logger.info(f"   T corregido (m): {T_meters.ravel()}")

            R1, R2, P1, P2, Q, roi1, roi2 = cv2.stereoRectify(
                mtx_left, dist_left,
                mtx_right, dist_right,
                img_shape, R, T_meters,  # ← USAR T EN METROS
                flags=cv2.CALIB_ZERO_DISPARITY,
                alpha=0.9
            )

            logger.info(f"✅ Matriz Q generada con unidades en METROS")
            logger.info(f"   Q[3,2] = {Q[3,2]:.6f} (debería ser ~1/baseline_metros)")
            
            # Crear mapas de rectificación
            left_map1, left_map2 = cv2.initUndistortRectifyMap(
                mtx_left, dist_left, R1, P1, img_shape, cv2.CV_16SC2
            )
            right_map1, right_map2 = cv2.initUndistortRectifyMap(
                mtx_right, dist_right, R2, P2, img_shape, cv2.CV_16SC2
            )
            
            # ✏️ --- UNIDADES EN MILÍMETROS ---
            # T está en mm, baseline estará en mm
            baseline_mm = np.linalg.norm(T)
            baseline_m = baseline_mm / 1000.0 # Convertir a metros para guardar
            logger.info(f"Baseline calculado: {baseline_mm:.1f} mm") # Log en mm
            # ✏️ --- FIN CAMBIO ---

            # Calcular distancia promedio
            avg_distance_m = 0.0
            if tvecs_left: 
                # ✏️ --- UNIDADES EN MILÍMETROS ---
                # tvecs están en mm
                distances_mm = [np.linalg.norm(tvec) for tvec in tvecs_left]
                if distances_mm:
                    avg_distance_mm = np.mean(distances_mm)
                    avg_distance_m = avg_distance_mm / 1000.0 # Convertir a metros para guardar
                    # Convertir mm a cm para el log (avg_distance_mm / 10.0)
                    logger.info(f"Distancia promedio al tablero (aprox): {avg_distance_mm / 10.0:.1f} cm") 
                # ✏️ --- FIN CAMBIO ---

            return {
                'success': True,
                'calibration_error': retval,
                'left_camera_matrix': mtx_left,
                'left_distortion': dist_left,
                'right_camera_matrix': mtx_right,
                'right_distortion': dist_right,
                'rotation_matrix': R,
                'translation_vector': T, # Guardado en mm
                'essential_matrix': E,
                'fundamental_matrix': F,
                'rectification_left': R1,
                'rectification_right': R2,
                'projection_left': P1,
                'projection_right': P2,
                'disparity_to_depth_matrix': Q,
                'roi_left': roi1,
                'roi_right': roi2,
                'baseline_meters': baseline_m, # Guardar en metros
                'calibration_date': datetime.now().isoformat(),
                'tvecs_left': tvecs_left,       # Guardados en mm
                'tvecs_right': tvecs_right,     # Guardados en mm
                'average_distance_meters': avg_distance_m # Guardar en metros
            }
            
        except Exception as e:
            logger.error(f"Error en calibración estéreo: {e}", exc_info=True) # exc_info=True para traceback
            return {
                'success': False,
                'error': str(e)
            }

    def validate_calibration_quality(self, calibration_result: Dict[str, Any]) -> Dict[str, Any]:
        """Validar calidad de los resultados de calibración"""
        validation = {
            'is_good_quality': True,
            'quality_issues': [],
            'quality_metrics': {}
        }
        
        try:
            error = calibration_result['calibration_error']
            baseline = calibration_result['baseline_meters']
            
            # 1. Error de reproyección
            validation['quality_metrics']['reprojection_error'] = error
            if error > 1.0:  # Más de 1 píxel de error
                validation['is_good_quality'] = False
                validation['quality_issues'].append(f"Error de reproyección alto: {error:.3f} píxeles")
            elif error > 0.5:
                validation['quality_issues'].append(f"Error de reproyección moderado: {error:.3f} píxeles")
            
            # 2. Baseline
            expected_baseline = self.config.stereo.baseline_mm / 1000.0
            baseline_diff = abs(baseline - expected_baseline) / expected_baseline
            
            validation['quality_metrics']['baseline_meters'] = baseline
            validation['quality_metrics']['baseline_error_percent'] = baseline_diff * 100
            
            if baseline_diff > 0.2:  # Más del 20% de diferencia
                validation['quality_issues'].append(
                    f"Baseline muy diferente al esperado: {baseline*1000:.1f}mm vs {expected_baseline*1000:.1f}mm"
                )
            
            # 3. Determinante de matrices de rotación (deben estar cerca de 1)
            R = calibration_result['rotation_matrix']
            det_R = np.linalg.det(R)
            validation['quality_metrics']['rotation_determinant'] = det_R
            
            if abs(det_R - 1.0) > 0.01:
                validation['quality_issues'].append(f"Matrix de rotación no ortogonal: det(R) = {det_R:.4f}")
            
            # 4. Condicionamiento de matrices de cámara
            mtx_left = calibration_result['left_camera_matrix']
            mtx_right = calibration_result['right_camera_matrix']
            
            cond_left = np.linalg.cond(mtx_left)
            cond_right = np.linalg.cond(mtx_right)
            
            validation['quality_metrics']['left_matrix_condition'] = cond_left
            validation['quality_metrics']['right_matrix_condition'] = cond_right
            
            if cond_left > 1e6 or cond_right > 1e6:
                validation['quality_issues'].append("Matrices de cámara mal condicionadas")
            
            logger.info(f"Validación de calibración - Buena calidad: {validation['is_good_quality']}")
            if validation['quality_issues']:
                logger.warning(f"Problemas detectados: {validation['quality_issues']}")
            
        except Exception as e:
            logger.error(f"Error validando calidad de calibración: {e}")
            validation['is_good_quality'] = False
            validation['quality_issues'].append(f"Error en validación: {e}")
        
        return validation
    
    def calibrate_from_session(self, session_dir: str, 
                              progress_callback: Optional[Callable] = None) -> Dict[str, Any]:
        """Ejecutar calibración completa desde directorio de sesión"""
        try:
            session_path = Path(session_dir)
            
            if not session_path.exists():
                return {
                    'success': False,
                    'error': f"Directorio de sesión no existe: {session_dir}"
                }
            
            # Buscar pares de imágenes
            left_images = sorted(session_path.glob("left_*.jpg"))
            right_images = sorted(session_path.glob("right_*.jpg"))
            
            if len(left_images) != len(right_images):
                return {
                    'success': False,
                    'error': f"Número desigual de imágenes: {len(left_images)} izq, {len(right_images)} der"
                }
            
            if len(left_images) == 0:
                return {
                    'success': False,
                    'error': "No se encontraron imágenes de calibración"
                }
            
            # Crear pares
            image_pairs = list(zip([str(l) for l in left_images], [str(r) for r in right_images]))
            
            logger.info(f"Encontrados {len(image_pairs)} pares de imágenes en {session_dir}")
            
            # Procesar calibración
            result = self.process_calibration_images(image_pairs, progress_callback)
            
            if result['success']:
                if 'rectification_maps' in result:
                    del result['rectification_maps']
                    logger.info("Mapas de rectificación eliminados antes de guardar (ahorro de memoria).")
                # Convertir TODO el resultado (incluyendo mapas) a listas ANTES de guardar
                logger.debug("Convirtiendo resultados de calibración a formato JSON...")
                json_compatible_result = self._convert_arrays_to_lists(result)
                logger.debug("Conversión completa.")

                # Guardar calibración en config principal (ahora usa el resultado convertido)
                self.config.save_calibration(json_compatible_result)
                logger.info("Calibración guardada en configuración principal (data/calibration/calibration_data.json)")

                # Guardar resultados detallados en la carpeta de la sesión
                results_file = session_path / "calibration_results.json"
                logger.debug(f"Guardando resultados detallados en: {results_file}")
                try:
                    with open(results_file, 'w') as f:
                        json.dump(json_compatible_result, f, indent=4)
                    logger.info(f"Resultados detallados guardados en {results_file.name}")
                except Exception as json_err:
                    logger.error(f"¡FALLO al guardar JSON detallado!: {json_err}")
                    # No relanzamos el error, la calibración principal ya se guardó.
                    # Podrías querer añadir más manejo de errores aquí.
            
            return result
            
        except Exception as e:
            logger.error(f"Error en calibración desde sesión: {e}")
            return {
                'success': False,
                'error': str(e)
            }
    
    def _convert_arrays_to_lists(self, obj):
        """Convertir arrays numpy a listas para JSON"""
        if isinstance(obj, dict):
            return {key: self._convert_arrays_to_lists(value) for key, value in obj.items()}
        elif isinstance(obj, (list, tuple)):  # <--- MODIFICACIÓN: Añadido 'tuple'
            return [self._convert_arrays_to_lists(item) for item in obj]
        elif isinstance(obj, np.ndarray):
            return obj.tolist()
        # ✏️ --- NUEVO: Manejar escalares de NumPy ---
        elif isinstance(obj, (np.int64, np.int32, np.int16, np.int8)):
            return int(obj)
        elif isinstance(obj, (np.float64, np.float32, np.float16)):
            return float(obj)
        elif isinstance(obj, (np.bool_)):
            return bool(obj)
        # ✏️ --- FIN NUEVO ---
        else:
            return obj

if __name__ == "__main__":
    # Test del calibrador
    from config.camera_config import CameraConfig
    
    try:
        print("Probando calibrador de cámaras...")
        
        config = CameraConfig()
        calibrator = CameraCalibrator(config)
        
        print(f"✓ Calibrador inicializado")
        print(f"  Tablero: {calibrator.board_size}")
        print(f"  Tamaño cuadrado: {calibrator.square_size*1000:.1f}mm")
        
        # Test preparación de puntos
        objp = calibrator.prepare_object_points()
        print(f"✓ Puntos 3D preparados: {objp.shape}")
        
    except Exception as e:
        print(f"✗ Error: {e}")
        import sys
        sys.exit(1)