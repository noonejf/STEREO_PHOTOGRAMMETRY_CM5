#!/usr/bin/env python3
"""
Sistema de calibración para cámaras estéreo
Soporta tableros ChArUco (recomendado) y ajedrez clásico (legacy)
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

        # === CONFIGURACIÓN DE TABLERO ===
        self.use_charuco = camera_config.stereo.use_charuco

        if self.use_charuco:
            # Configuración ChArUco
            self.charuco_squares_x = camera_config.stereo.charuco_squares_x
            self.charuco_squares_y = camera_config.stereo.charuco_squares_y
            self.square_size = camera_config.stereo.charuco_square_size_mm  # mm
            self.marker_size = camera_config.stereo.charuco_marker_size_mm  # mm

            # Crear diccionario ArUco
            dict_name = camera_config.stereo.charuco_dict_name
            aruco_dict_id = getattr(cv2.aruco, dict_name)
            self.aruco_dict = cv2.aruco.getPredefinedDictionary(aruco_dict_id)

            # Crear tablero ChArUco
            self.charuco_board = cv2.aruco.CharucoBoard(
                (self.charuco_squares_x, self.charuco_squares_y),
                self.square_size / 1000.0,  # Convertir mm a metros para OpenCV
                self.marker_size / 1000.0,   # Convertir mm a metros para OpenCV
                self.aruco_dict
            )

            # Parámetros de detección ArUco
            self.aruco_params = cv2.aruco.DetectorParameters()

            logger.info(f"Calibrador ChArUco inicializado - {self.charuco_squares_x}x{self.charuco_squares_y}, "
                       f"Square: {self.square_size:.1f}mm, Marker: {self.marker_size:.1f}mm")
        else:
            # Configuración ajedrez clásico (legacy)
            self.board_size = camera_config.stereo.calibration_board_size
            self.square_size = camera_config.stereo.calibration_square_size_mm  # mm
            logger.info(f"Calibrador Ajedrez inicializado - Tablero: {self.board_size}, "
                       f"Cuadrado: {self.square_size:.1f}mm")

        # === PARÁMETROS DE CALIBRACIÓN ===
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
    
    def prepare_object_points(self) -> np.ndarray:
        """Preparar puntos 3D del tablero (ChArUco o Ajedrez)"""
        if self.use_charuco:
            # Para ChArUco, los puntos 3D son generados dinámicamente por el tablero
            # No se necesita un array fijo como en ajedrez
            # Este método no se usa con ChArUco, pero lo mantenemos por compatibilidad
            return None
        else:
            # Ajedrez clásico: Crear patrón 3D de puntos (z=0 para tablero plano)
            objp = np.zeros((self.board_size[0] * self.board_size[1], 3), np.float32)
            objp[:, :2] = np.mgrid[0:self.board_size[0], 0:self.board_size[1]].T.reshape(-1, 2)
            objp *= self.square_size  # Multiplicar por tamaño en mm

            return objp
    
    def detect_charuco_corners(self, image: np.ndarray) -> Tuple[bool, Optional[np.ndarray], Optional[np.ndarray]]:
        """
        Detectar esquinas ChArUco en una imagen

        Returns:
            success (bool): True si se detectaron esquinas válidas
            charuco_corners (np.ndarray): Coordenadas 2D de las esquinas ChArUco detectadas
            charuco_ids (np.ndarray): IDs de las esquinas detectadas
        """
        try:
            # Convertir a escala de grises si es necesario
            if len(image.shape) == 3:
                gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
            else:
                gray = image.copy()

            # 1. Detectar marcadores ArUco
            corners, ids, _ = cv2.aruco.detectMarkers(
                gray,
                self.aruco_dict,
                parameters=self.aruco_params
            )

            # Verificar que se detectaron marcadores
            if ids is None or len(ids) == 0:
                logger.debug("No se detectaron marcadores ArUco")
                return False, None, None

            # 2. Interpolar esquinas ChArUco a partir de los marcadores
            num_corners, charuco_corners, charuco_ids = cv2.aruco.interpolateCornersCharuco(
                corners,
                ids,
                gray,
                self.charuco_board
            )

            # 3. Validar que se detectaron suficientes esquinas
            # Mínimo 4 esquinas para calibración robusta
            if num_corners is None or num_corners < 4:
                logger.debug(f"Esquinas ChArUco insuficientes: {num_corners}")
                return False, None, None

            logger.debug(f"✓ ChArUco detectado: {num_corners} esquinas, {len(ids)} marcadores")
            return True, charuco_corners, charuco_ids

        except Exception as e:
            logger.error(f"Error detectando ChArUco: {e}")
            return False, None, None

    def detect_chessboard_corners(self, image: np.ndarray,
                                 improve_accuracy: bool = True) -> Tuple[bool, Optional[np.ndarray]]:
        """Detectar esquinas del tablero de ajedrez en una imagen (legacy)"""
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
        """Procesar pares de imágenes para calibración (ChArUco o Ajedrez)"""
        try:
            board_type = "ChArUco" if self.use_charuco else "Ajedrez"
            logger.info(f"Procesando {len(image_pairs)} pares con tablero {board_type}")

            if self.use_charuco:
                return self._process_charuco_calibration(image_pairs, progress_callback)
            else:
                return self._process_chessboard_calibration(image_pairs, progress_callback)

        except Exception as e:
            logger.error(f"Error procesando imágenes de calibración: {e}")
            return {
                'success': False,
                'error': str(e)
            }

    def _process_charuco_calibration(self, image_pairs: List[Tuple[str, str]],
                                    progress_callback: Optional[Callable] = None) -> Dict[str, Any]:
        """Procesar calibración con tablero ChArUco"""
        # Listas para almacenar esquinas ChArUco detectadas
        all_charuco_corners_left = []
        all_charuco_corners_right = []
        all_charuco_ids_left = []
        all_charuco_ids_right = []

        valid_images = []
        image_quality_reports = []

        for i, (left_path, right_path) in enumerate(image_pairs):
            try:
                if progress_callback:
                    progress = int((i / len(image_pairs)) * 70)
                    progress_callback(progress, f"Procesando imagen {i+1}/{len(image_pairs)}")

                # Cargar imágenes
                left_img = cv2.imread(left_path)
                right_img = cv2.imread(right_path)

                if left_img is None or right_img is None:
                    logger.warning(f"No se pudieron cargar imágenes: {left_path}, {right_path}")
                    continue

                # Detectar ChArUco en ambas imágenes
                ret_left, corners_left, ids_left = self.detect_charuco_corners(left_img)
                ret_right, corners_right, ids_right = self.detect_charuco_corners(right_img)

                if ret_left and ret_right:
                    # CRÍTICO: Filtrar solo IDs comunes entre ambas imágenes
                    common_ids = np.intersect1d(ids_left.flatten(), ids_right.flatten())

                    if len(common_ids) < 4:
                        logger.warning(f"Par {i+1}: Solo {len(common_ids)} IDs comunes (mínimo 4)")
                        continue

                    # Filtrar esquinas para mantener solo IDs comunes
                    left_mask = np.isin(ids_left.flatten(), common_ids)
                    right_mask = np.isin(ids_right.flatten(), common_ids)

                    filtered_corners_left = corners_left[left_mask]
                    filtered_corners_right = corners_right[right_mask]
                    filtered_ids_left = ids_left[left_mask]
                    filtered_ids_right = ids_right[right_mask]

                    # Verificar que los IDs estén en el mismo orden
                    sort_left = np.argsort(filtered_ids_left.flatten())
                    sort_right = np.argsort(filtered_ids_right.flatten())

                    filtered_corners_left = filtered_corners_left[sort_left]
                    filtered_corners_right = filtered_corners_right[sort_right]
                    filtered_ids_left = filtered_ids_left[sort_left]
                    filtered_ids_right = filtered_ids_right[sort_right]

                    logger.info(f"Par {i+1} VÁLIDO: {len(common_ids)} esquinas comunes")

                    # Agregar a las listas
                    all_charuco_corners_left.append(filtered_corners_left)
                    all_charuco_corners_right.append(filtered_corners_right)
                    all_charuco_ids_left.append(filtered_ids_left)
                    all_charuco_ids_right.append(filtered_ids_right)

                    valid_images.append((left_path, right_path))
                    image_quality_reports.append({
                        'left': {'is_valid': True, 'issues': []},
                        'right': {'is_valid': True, 'issues': []}
                    })

                else:
                    logger.warning(f"No se detectó ChArUco en par {i+1}")

            except Exception as e:
                logger.error(f"Error procesando par {i+1}: {e}")
                continue

        if len(all_charuco_corners_left) < self.config.stereo.min_calibration_images:
            return {
                'success': False,
                'error': f"Imágenes válidas insuficientes: {len(all_charuco_corners_left)}/{self.config.stereo.min_calibration_images}"
            }

        logger.info(f"Imágenes ChArUco válidas: {len(all_charuco_corners_left)}")

        # Obtener dimensiones de imagen
        img_shape = left_img.shape[:2][::-1]  # (width, height)

        if progress_callback:
            progress_callback(75, "Ejecutando calibración estéreo ChArUco...")

        # Ejecutar calibración estéreo ChArUco
        calibration_result = self.execute_stereo_calibration_charuco(
            all_charuco_corners_left, all_charuco_corners_right,
            all_charuco_ids_left, all_charuco_ids_right,
            img_shape
        )

        if calibration_result['success']:
            calibration_result['images_used'] = len(all_charuco_corners_left)
            calibration_result['valid_image_pairs'] = valid_images
            calibration_result['quality_reports'] = image_quality_reports
            calibration_result['image_shape'] = img_shape

            if progress_callback:
                progress_callback(90, "Validando resultados de calibración...")

            validation_result = self.validate_calibration_quality(calibration_result)
            calibration_result.update(validation_result)

            if progress_callback:
                progress_callback(100, "Calibración completada")

        return calibration_result

    def _process_chessboard_calibration(self, image_pairs: List[Tuple[str, str]],
                                       progress_callback: Optional[Callable] = None) -> Dict[str, Any]:
        """Procesar calibración con tablero de ajedrez (legacy)"""
        # Preparar puntos 3D
        objp = self.prepare_object_points()

        # Listas para almacenar puntos
        objpoints = []
        imgpoints_left = []
        imgpoints_right = []

        valid_images = []
        image_quality_reports = []

        for i, (left_path, right_path) in enumerate(image_pairs):
            try:
                if progress_callback:
                    progress = int((i / len(image_pairs)) * 70)
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
                    logger.info(f"Par {i+1} VÁLIDO (Ajedrez detectado)")

                    objpoints.append(objp)
                    imgpoints_left.append(corners_left)
                    imgpoints_right.append(corners_right)

                    valid_images.append((left_path, right_path))
                    image_quality_reports.append({
                        'left': {'is_valid': True, 'issues': []},
                        'right': {'is_valid': True, 'issues': []}
                    })

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
            calibration_result['images_used'] = len(objpoints)
            calibration_result['valid_image_pairs'] = valid_images
            calibration_result['quality_reports'] = image_quality_reports
            calibration_result['image_shape'] = img_shape

            if progress_callback:
                progress_callback(90, "Validando resultados de calibración...")

            validation_result = self.validate_calibration_quality(calibration_result)
            calibration_result.update(validation_result)

            if progress_callback:
                progress_callback(100, "Calibración completada")

        return calibration_result

    def execute_stereo_calibration_charuco(self, charuco_corners_left: List[np.ndarray],
                                          charuco_corners_right: List[np.ndarray],
                                          charuco_ids_left: List[np.ndarray],
                                          charuco_ids_right: List[np.ndarray],
                                          img_shape: Tuple[int, int]) -> Dict[str, Any]:
        """Ejecutar calibración estéreo con tablero ChArUco"""
        try:
            logger.info("Ejecutando calibración estéreo ChArUco...")

            # === CALIBRACIÓN INDIVIDUAL DE CADA CÁMARA CON ChArUco ===
            logger.info("Calibrando cámara izquierda (ChArUco)...")
            ret_left, mtx_left, dist_left, rvecs_l, tvecs_l = cv2.aruco.calibrateCameraCharuco(
                charuco_corners_left,
                charuco_ids_left,
                self.charuco_board,
                img_shape,
                None,
                None,
                criteria=self.calibration_criteria
            )
            logger.info(f"Calibración cámara izquierda - Error: {ret_left:.3f}")

            logger.info("Calibrando cámara derecha (ChArUco)...")
            ret_right, mtx_right, dist_right, rvecs_r, tvecs_r = cv2.aruco.calibrateCameraCharuco(
                charuco_corners_right,
                charuco_ids_right,
                self.charuco_board,
                img_shape,
                None,
                None,
                criteria=self.calibration_criteria
            )
            logger.info(f"Calibración cámara derecha - Error: {ret_right:.3f}")

            if ret_left == 0 or ret_right == 0:
                logger.error("Calibración individual ChArUco falló")
                return {
                    'success': False,
                    'error': 'Calibración individual ChArUco falló (retval=0)'
                }

            # === CALIBRACIÓN ESTÉREO ===
            # IMPORTANTE: Para ChArUco, necesitamos crear objPoints comunes
            # Usamos el board para obtener las coordenadas 3D de cada ID
            objpoints = []
            imgpoints_left = []
            imgpoints_right = []

            for corners_l, ids_l, corners_r, ids_r in zip(
                charuco_corners_left, charuco_ids_left,
                charuco_corners_right, charuco_ids_right
            ):
                # Obtener puntos 3D del tablero ChArUco
                # NOTA: chessboardCorners está en METROS (porque así creamos el board)
                obj_pts = self.charuco_board.getChessboardCorners()

                # Filtrar solo los IDs detectados (ya están filtrados por IDs comunes)
                obj_pts_filtered = obj_pts[ids_l.flatten()]

                # Convertir de metros a milímetros para consistencia interna
                obj_pts_filtered = obj_pts_filtered * 1000.0

                objpoints.append(obj_pts_filtered)
                imgpoints_left.append(corners_l)
                imgpoints_right.append(corners_r)

            # Flags para calibración estéreo (usar matrices ya calculadas)
            stereo_flags = cv2.CALIB_FIX_INTRINSIC

            logger.info("Ejecutando calibración estéreo conjunta...")
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

            logger.debug("--- RESULTADOS ChArUco ---")
            logger.debug(f"Error de reproyección (retval): {retval:.4f}")
            logger.debug(f"Vector T (mm): {T.ravel()}")  # En mm porque objpoints están en mm

            if retval == 0 or np.isnan(retval):
                logger.error('Calibración estéreo ChArUco falló (retval=0 o nan)')
                return {
                    'success': False,
                    'error': 'Calibración estéreo ChArUco falló'
                }

            logger.info(f"Error calibración estéreo: {retval:.3f} píxeles")

            # === RECTIFICACIÓN ESTÉREO ===
            logger.info("Calculando rectificación estéreo...")

            # CRÍTICO: Convertir T de mm a metros para stereoRectify
            T_meters = T / 1000.0
            logger.info(f"🔧 T convertido: {T.ravel()} mm → {T_meters.ravel()} m")

            R1, R2, P1, P2, Q, roi1, roi2 = cv2.stereoRectify(
                mtx_left, dist_left,
                mtx_right, dist_right,
                img_shape, R, T_meters,  # T en METROS
                flags=cv2.CALIB_ZERO_DISPARITY,
                alpha=0.0
            )

            logger.info(f"✅ Matriz Q generada (unidades: metros)")
            logger.info(f"   Q[3,2] = {Q[3,2]:.6f}")

            # Crear mapas de rectificación
            left_map1, left_map2 = cv2.initUndistortRectifyMap(
                mtx_left, dist_left, R1, P1, img_shape, cv2.CV_16SC2
            )
            right_map1, right_map2 = cv2.initUndistortRectifyMap(
                mtx_right, dist_right, R2, P2, img_shape, cv2.CV_16SC2
            )

            # === CALCULAR MÉTRICAS ===
            baseline_mm = np.linalg.norm(T)  # T está en mm
            baseline_m = baseline_mm / 1000.0
            logger.info(f"Baseline: {baseline_mm:.1f} mm")

            # Distancia promedio al tablero
            avg_distance_m = 0.0
            if tvecs_l:
                distances_mm = [np.linalg.norm(tvec) for tvec in tvecs_l]
                if distances_mm:
                    avg_distance_mm = np.mean(distances_mm)
                    avg_distance_m = avg_distance_mm / 1000.0
                    logger.info(f"Distancia promedio al tablero: {avg_distance_mm / 10.0:.1f} cm")

            return {
                'success': True,
                'calibration_error': retval,
                'left_camera_matrix': mtx_left,
                'left_distortion': dist_left,
                'right_camera_matrix': mtx_right,
                'right_distortion': dist_right,
                'rotation_matrix': R,
                'translation_vector': T,  # En mm
                'essential_matrix': E,
                'fundamental_matrix': F,
                'rectification_left': R1,
                'rectification_right': R2,
                'projection_left': P1,
                'projection_right': P2,
                'disparity_to_depth_matrix': Q,
                'roi_left': roi1,
                'roi_right': roi2,
                'baseline_meters': baseline_m,  # En metros
                'calibration_date': datetime.now().isoformat(),
                'tvecs_left': tvecs_l,  # En mm
                'tvecs_right': tvecs_r,  # En mm
                'average_distance_meters': avg_distance_m  # En metros
            }

        except Exception as e:
            logger.error(f"Error en calibración estéreo ChArUco: {e}", exc_info=True)
            return {
                'success': False,
                'error': str(e)
            }

    def execute_stereo_calibration(self, objpoints: List[np.ndarray],
                                 imgpoints_left: List[np.ndarray],
                                 imgpoints_right: List[np.ndarray],
                                 img_shape: Tuple[int, int]) -> Dict[str, Any]:
        """Ejecutar calibración estéreo con tablero de ajedrez (legacy)"""
        try:
            logger.info("Ejecutando calibración estéreo (Ajedrez)...")

            # === CALIBRACIÓN INDIVIDUAL DE CADA CÁMARA ===
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

            if ret_left == 0 or ret_right == 0:
                logger.error("Calibración individual de cámaras falló")
                return {
                    'success': False,
                    'error': 'Calibración individual de cámaras falló (retval=0)'
                }

            # === CALIBRACIÓN ESTÉREO CONJUNTA ===
            stereo_flags = cv2.CALIB_FIX_INTRINSIC  # Usar matrices ya calculadas

            logger.info("Ejecutando calibración estéreo conjunta...")
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

            # === UNIDADES: T está en MILÍMETROS (porque objpoints están en mm) ===
            logger.debug("--- RESULTADOS DE CALIBRACIÓN ---")
            logger.debug(f"Error de reproyección: {retval:.4f} px")
            logger.debug(f"Vector T (mm): {T.ravel()}")

            # Guardar poses individuales
            tvecs_left = tvecs_l
            tvecs_right = tvecs_r

            if retval == 0 or np.isnan(retval):
                logger.error('Calibración estéreo falló (retval=0 o nan)')
                return {
                    'success': False,
                    'error': 'Calibración estéreo falló'
                }

            logger.info(f"Error calibración estéreo: {retval:.3f} píxeles")

            # === RECTIFICACIÓN ESTÉREO ===
            logger.info("Calculando rectificación estéreo...")

            # ⚠️ CRÍTICO: stereoRectify espera T en METROS para generar Q correctamente
            # Si pasamos T en mm, la matriz Q asumirá mm y el cálculo de profundidad fallará
            T_meters = T / 1000.0
            logger.info(f"🔧 T convertido: {T.ravel()} mm → {T_meters.ravel()} m")

            R1, R2, P1, P2, Q, roi1, roi2 = cv2.stereoRectify(
                mtx_left, dist_left,
                mtx_right, dist_right,
                img_shape, R, T_meters,  # ← T en METROS
                flags=cv2.CALIB_ZERO_DISPARITY,
                alpha=0.0  # 0.0 = recortar bordes negros
            )

            logger.info(f"✅ Matriz Q generada (unidades: metros)")
            logger.info(f"   Q[3,2] = {Q[3,2]:.6f}")

            # Crear mapas de rectificación
            left_map1, left_map2 = cv2.initUndistortRectifyMap(
                mtx_left, dist_left, R1, P1, img_shape, cv2.CV_16SC2
            )
            right_map1, right_map2 = cv2.initUndistortRectifyMap(
                mtx_right, dist_right, R2, P2, img_shape, cv2.CV_16SC2
            )

            # === CALCULAR MÉTRICAS ===
            baseline_mm = np.linalg.norm(T)  # T está en mm
            baseline_m = baseline_mm / 1000.0  # Convertir a metros para guardar
            logger.info(f"Baseline: {baseline_mm:.1f} mm")

            # Distancia promedio al tablero
            avg_distance_m = 0.0
            if tvecs_left:
                distances_mm = [np.linalg.norm(tvec) for tvec in tvecs_left]
                if distances_mm:
                    avg_distance_mm = np.mean(distances_mm)
                    avg_distance_m = avg_distance_mm / 1000.0
                    logger.info(f"Distancia promedio al tablero: {avg_distance_mm / 10.0:.1f} cm")

            return {
                'success': True,
                'calibration_error': retval,
                'left_camera_matrix': mtx_left,
                'left_distortion': dist_left,
                'right_camera_matrix': mtx_right,
                'right_distortion': dist_right,
                'rotation_matrix': R,
                'translation_vector': T,  # En mm
                'essential_matrix': E,
                'fundamental_matrix': F,
                'rectification_left': R1,
                'rectification_right': R2,
                'projection_left': P1,
                'projection_right': P2,
                'disparity_to_depth_matrix': Q,
                'roi_left': roi1,
                'roi_right': roi2,
                'baseline_meters': baseline_m,  # En metros
                'calibration_date': datetime.now().isoformat(),
                'tvecs_left': tvecs_left,  # En mm
                'tvecs_right': tvecs_right,  # En mm
                'average_distance_meters': avg_distance_m  # En metros
            }

        except Exception as e:
            logger.error(f"Error en calibración estéreo: {e}", exc_info=True)
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