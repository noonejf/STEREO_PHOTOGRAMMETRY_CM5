#!/usr/bin/env python3
"""
Procesador estéreo para generar mapas de disparidad y profundidad
Implementa algoritmos robustos para reconstrucción 3D
"""

import cv2
import numpy as np
import json
from pathlib import Path
from typing import Dict, Any, Optional, Tuple, Callable
from datetime import datetime

from utils.logger import get_logger, PerformanceLogger

logger = get_logger(__name__)

class StereoProcessor:
    """Procesador principal para visión estéreo"""
    
    def __init__(self, camera_config):
        """Inicializar procesador estéreo"""
        self.config = camera_config
        self.calibration_data = camera_config.calibration_data

        # Verificar que el sistema esté calibrado
        if not camera_config.is_calibrated():
            raise RuntimeError("Sistema no calibrado. Ejecuta calibración primero.")

        # Configurar algoritmos de matching estéreo
        self.setup_stereo_algorithms()

        # Cargar mapas de rectificación
        self.rectification_maps = self.calibration_data.get('rectification_maps')
        if not self.rectification_maps:
            logger.warning("Mapas de rectificación no disponibles, se calcularán dinámicamente")

        # Máscara de región válida (se calcula en rectificación)
        self.valid_roi_mask = None

        logger.info("Procesador estéreo inicializado")
    
    def _create_roi_mask(self, img_shape: Tuple[int, int], roi1: Tuple, roi2: Tuple) -> np.ndarray:
        """
        Crear máscara que combina las regiones válidas de ambas cámaras

        Args:
            img_shape: (height, width) de la imagen
            roi1: (x, y, w, h) región válida de cámara izquierda
            roi2: (x, y, w, h) región válida de cámara derecha

        Returns:
            Máscara booleana donde True = región válida
        """
        height, width = img_shape
        mask = np.zeros((height, width), dtype=bool)

        # Extraer ROIs
        x1, y1, w1, h1 = roi1
        x2, y2, w2, h2 = roi2

        # Si ROI es inválido (ancho o alto = 0), usar imagen completa con margen
        if w1 <= 0 or h1 <= 0 or w2 <= 0 or h2 <= 0:
            logger.warning("⚠️ ROI inválido detectado, usando máscara con margen de bordes")
            # Excluir 5% de los bordes para evitar artefactos
            margin_x = int(width * 0.05)
            margin_y = int(height * 0.05)
            mask[margin_y:height-margin_y, margin_x:width-margin_x] = True
            return mask

        # Calcular intersección de ambos ROIs (región válida para ambas cámaras)
        x_start = max(x1, x2)
        y_start = max(y1, y2)
        x_end = min(x1 + w1, x2 + w2)
        y_end = min(y1 + h1, y2 + h2)

        # Verificar que la intersección sea válida
        if x_end > x_start and y_end > y_start:
            # Aplicar un margen adicional de seguridad (2% interno)
            margin_x = int((x_end - x_start) * 0.02)
            margin_y = int((y_end - y_start) * 0.02)

            x_safe = max(0, x_start + margin_x)
            y_safe = max(0, y_start + margin_y)
            x_end_safe = min(width, x_end - margin_x)
            y_end_safe = min(height, y_end - margin_y)

            mask[y_safe:y_end_safe, x_safe:x_end_safe] = True
        else:
            logger.warning("⚠️ ROIs no se superponen, usando máscara conservadora")
            # Usar región central como fallback
            margin_x = int(width * 0.1)
            margin_y = int(height * 0.1)
            mask[margin_y:height-margin_y, margin_x:width-margin_x] = True

        return mask

    def _save_correspondence_debug(self, left_img, right_img, disparity, debug_path):
        """
        Guardar visualización de correspondencias de puntos entre imágenes
        Muestra cómo se matchean los puntos entre left y right
        """
        # Crear imagen combinada
        h, w = left_img.shape[:2]
        combined = np.zeros((h, w*2, 3), dtype=np.uint8)

        if len(left_img.shape) == 2:
            combined[:, :w] = cv2.cvtColor(left_img, cv2.COLOR_GRAY2BGR)
            combined[:, w:] = cv2.cvtColor(right_img, cv2.COLOR_GRAY2BGR)
        else:
            combined[:, :w] = left_img
            combined[:, w:] = right_img

        # Tomar puntos de muestra (grid espaciado)
        step = 80  # Espaciado entre puntos
        colors = [(0, 255, 0), (255, 0, 0), (0, 0, 255), (255, 255, 0), (255, 0, 255), (0, 255, 255)]

        points_drawn = 0
        for y in range(step, h-step, step):
            for x in range(step, w-step, step):
                d = disparity[y, x]
                if d > 10.0:  # Solo puntos con disparidad válida
                    # Punto en imagen izquierda
                    cv2.circle(combined, (x, y), 4, colors[points_drawn % len(colors)], -1)

                    # Punto correspondiente en imagen derecha (desplazado por disparidad)
                    x_right = int(x - d) + w  # -d porque la disparidad es negativa en right
                    if 0 <= x_right - w < w:
                        cv2.circle(combined, (x_right, y), 4, colors[points_drawn % len(colors)], -1)

                        # Dibujar línea conectando correspondencias
                        cv2.line(combined, (x, y), (x_right, y), colors[points_drawn % len(colors)], 1)

                        points_drawn += 1
                        if points_drawn >= 50:  # Limitar a 50 puntos para no saturar
                            break
            if points_drawn >= 50:
                break

        cv2.imwrite(str(debug_path / "15_correspondences.jpg"), combined)
        logger.info(f"🔍 DEBUG Correspondencias guardadas: {points_drawn} puntos")

    def setup_stereo_algorithms(self):
        """Configurar algoritmos de matching estéreo"""

        # Algoritmo SGBM (Semi-Global Block Matching) - Recomendado
        # OPTIMIZADO: Para superficies con poca textura (piel, paredes lisas)
        self.sgbm = cv2.StereoSGBM_create(
            minDisparity=0,
            numDisparities=160,       # Aumentado para capturar objetos cercanos (0.3m-5m)
            blockSize=11,             # AUMENTADO: 7→11 para ventanas más grandes (mejor en superficies lisas)
            P1=8 * 3 * 11**2,        # Ajustado para blockSize=11
            P2=32 * 3 * 11**2,       # Ajustado para blockSize=11 (penaliza discontinuidades)
            disp12MaxDiff=1,          # REDUCIDO: 2→1 para verificación más estricta
            uniquenessRatio=5,        # REDUCIDO: 15→5 para permitir más matches en superficies lisas
            speckleWindowSize=200,    # AUMENTADO: 150→200 para filtrar regiones ruidosas más grandes
            speckleRange=2,           # MUY REDUCIDO: 16→2 (solo tolera variación de 2 píxeles en speckles)
            preFilterCap=31,          # REDUCIDO: 63→31 para pre-filtro más suave
            mode=cv2.STEREO_SGBM_MODE_SGBM_3WAY  # Modo de cálculo
        )
        
        # Algoritmo BM (Block Matching) - Más rápido pero menos preciso
        self.bm = cv2.StereoBM_create(
            numDisparities=96,
            blockSize=15
        )
        
        # Filtro WLS para post-procesamiento
        self.wls_filter = cv2.ximgproc.createDisparityWLSFilter(self.sgbm)
        self.wls_filter.setLambda(8000.0)
        self.wls_filter.setSigmaColor(1.2)
        
        # Crear matcher derecho para verificación cruzada
        self.right_matcher = cv2.ximgproc.createRightMatcher(self.sgbm)
        
        logger.info("Algoritmos de matching estéreo configurados")
    
    def preprocess_images(self, left_img: np.ndarray, right_img: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
        """Preprocesar imágenes para matching estéreo"""
        
        # Convertir a escala de grises si es necesario
        if len(left_img.shape) == 3:
            left_gray = cv2.cvtColor(left_img, cv2.COLOR_BGR2GRAY)
        else:
            left_gray = left_img.copy()
            
        if len(right_img.shape) == 3:
            right_gray = cv2.cvtColor(right_img, cv2.COLOR_BGR2GRAY)
        else:
            right_gray = right_img.copy()
        
        # Ecualización de histograma adaptativa para mejorar contraste
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        left_enhanced = clahe.apply(left_gray)
        right_enhanced = clahe.apply(right_gray)
        
        # Suavizado ligero para reducir ruido
        left_smooth = cv2.bilateralFilter(left_enhanced, 5, 50, 50)
        right_smooth = cv2.bilateralFilter(right_enhanced, 5, 50, 50)
        
        return left_smooth, right_smooth
    
    def rectify_images(self, left_img: np.ndarray, right_img: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
        """Rectificar imágenes usando calibración estéreo"""
        
        if self.rectification_maps:
            # Usar mapas precalculados
            left_rectified = cv2.remap(
                left_img,
                self.rectification_maps['left_map1'],
                self.rectification_maps['left_map2'],
                cv2.INTER_LINEAR
            )
            right_rectified = cv2.remap(
                right_img,
                self.rectification_maps['right_map1'],
                self.rectification_maps['right_map2'],
                cv2.INTER_LINEAR
            )
        else:
            # Calcular rectificación dinámicamente
            logger.info("Calculando rectificación dinámica...")
            
            # Obtener parámetros de calibración
            mtx_left = self.calibration_data['left_camera_matrix']
            dist_left = self.calibration_data['left_distortion']
            mtx_right = self.calibration_data['right_camera_matrix']
            dist_right = self.calibration_data['right_distortion']
            R = self.calibration_data['rotation_matrix']
            T = self.calibration_data['translation_vector']
            
            img_shape = left_img.shape[:2][::-1]  # (width, height)
            
            # Calcular rectificación (capturando ROIs válidos)
            R1, R2, P1, P2, Q, roi1, roi2 = cv2.stereoRectify(
                mtx_left, dist_left,
                mtx_right, dist_right,
                img_shape, R, T,
                flags=cv2.CALIB_ZERO_DISPARITY,
                alpha=0.0  # CAMBIADO: 0.9 -> 0.0 para maximizar área válida y minimizar bordes
            )

            logger.info(f"🔍 DEBUG ROI válido izquierdo: {roi1}")
            logger.info(f"🔍 DEBUG ROI válido derecho: {roi2}")

            # Crear máscara de región válida
            self.valid_roi_mask = self._create_roi_mask(img_shape[::-1], roi1, roi2)
            logger.info(f"🔍 DEBUG Máscara ROI creada - Píxeles válidos: {np.sum(self.valid_roi_mask)}/{self.valid_roi_mask.size}")

            # Crear mapas
            left_map1, left_map2 = cv2.initUndistortRectifyMap(
                mtx_left, dist_left, R1, P1, img_shape, cv2.CV_16SC2
            )
            right_map1, right_map2 = cv2.initUndistortRectifyMap(
                mtx_right, dist_right, R2, P2, img_shape, cv2.CV_16SC2
            )

            # Aplicar rectificación
            left_rectified = cv2.remap(left_img, left_map1, left_map2, cv2.INTER_LINEAR)
            right_rectified = cv2.remap(right_img, right_map1, right_map2, cv2.INTER_LINEAR)
        
        return left_rectified, right_rectified
    
    def compute_disparity(self, left_img: np.ndarray, right_img: np.ndarray, 
                         algorithm: str = "SGBM", use_wls_filter: bool = True) -> Dict[str, Any]:
        """Calcular mapa de disparidad"""
        
        with PerformanceLogger(f"Cálculo de disparidad ({algorithm})", logger):
            
            # Preprocesar imágenes
            left_processed, right_processed = self.preprocess_images(left_img, right_img)
            
            # Seleccionar algoritmo
            if algorithm.upper() == "SGBM":
                matcher = self.sgbm
            elif algorithm.upper() == "BM":
                matcher = self.bm
            else:
                raise ValueError(f"Algoritmo desconocido: {algorithm}")
            
            # Calcular disparidad
            logger.info(f"Calculando disparidad con algoritmo {algorithm}")
            disparity_left = matcher.compute(left_processed, right_processed).astype(np.float32) / 16.0

            # CRÍTICO: Limpiar valores inválidos (negativos e infinitos)
            disparity_left = np.clip(disparity_left, 0, 1000)  # Limitar a rango razonable
            disparity_left[~np.isfinite(disparity_left)] = 0  # Reemplazar inf/nan con 0

            # CRÍTICO: Aplicar máscara de región válida (elimina bordes con artefactos)
            if self.valid_roi_mask is not None:
                logger.info("🔍 DEBUG Aplicando máscara ROI a disparidad sin filtrar...")
                disparity_left[~self.valid_roi_mask] = 0
                logger.info(f"   Píxeles enmascarados: {np.sum(~self.valid_roi_mask)}")

            # Calcular estadísticas solo sobre píxeles válidos
            valid_mask = disparity_left > 0
            valid_disp = disparity_left[valid_mask]

            disparity_result = {
                'disparity_map': disparity_left,
                'algorithm': algorithm,
                'shape': disparity_left.shape,
                'min_disparity': float(np.min(valid_disp)) if len(valid_disp) > 0 else 0.0,
                'max_disparity': float(np.max(valid_disp)) if len(valid_disp) > 0 else 0.0,
                'mean_disparity': float(np.mean(valid_disp)) if len(valid_disp) > 0 else 0.0,
                'valid_pixels': int(np.sum(valid_mask))
            }
            
            # Aplicar filtro WLS si se solicita
            if use_wls_filter and algorithm.upper() == "SGBM":
                logger.info("Aplicando filtro WLS para suavizado")
                
                # Calcular disparidad derecha para verificación cruzada
                disparity_right = self.right_matcher.compute(right_processed, left_processed).astype(np.float32) / 16.0
                
                # Aplicar filtro
                disparity_filtered = self.wls_filter.filter(
                    disparity_left, left_processed, None, disparity_right
                )

                # CRÍTICO: Limpiar valores inválidos del filtrado
                disparity_filtered = np.clip(disparity_filtered, 0, 1000)
                disparity_filtered[~np.isfinite(disparity_filtered)] = 0

                # CRÍTICO: Aplicar máscara ROI también al resultado filtrado
                if self.valid_roi_mask is not None:
                    logger.info("🔍 DEBUG Aplicando máscara ROI a disparidad filtrada...")
                    disparity_filtered[~self.valid_roi_mask] = 0

                # === POST-PROCESAMIENTO: Suavizado adicional ===
                # Aplicar filtro bilateral para suavizar preservando bordes
                logger.info("🔍 DEBUG Aplicando suavizado bilateral para reducir ruido...")
                disparity_smooth = cv2.bilateralFilter(
                    disparity_filtered.astype(np.float32),
                    d=9,           # Diámetro de vecindario
                    sigmaColor=75, # Filtro en espacio de color
                    sigmaSpace=75  # Filtro en espacio de coordenadas
                )

                # Preservar máscara de píxeles válidos
                disparity_smooth[disparity_filtered <= 0] = 0

                disparity_result['disparity_map'] = disparity_smooth
                disparity_result['disparity_before_smoothing'] = disparity_filtered
                disparity_result['filtered'] = True
                disparity_result['disparity_raw'] = disparity_left

                # Actualizar estadísticas con disparidad suavizada
                valid_mask_smooth = disparity_smooth > 0
                valid_disp_smooth = disparity_smooth[valid_mask_smooth]

                disparity_result.update({
                    'min_disparity': float(np.min(valid_disp_smooth)) if len(valid_disp_smooth) > 0 else 0.0,
                    'max_disparity': float(np.max(valid_disp_smooth)) if len(valid_disp_smooth) > 0 else 0.0,
                    'mean_disparity': float(np.mean(valid_disp_smooth)) if len(valid_disp_smooth) > 0 else 0.0,
                    'valid_pixels': int(np.sum(valid_mask_smooth))
                })
            
            # Crear mapa de confianza
            confidence_map = self.compute_confidence_map(disparity_result['disparity_map'])
            disparity_result['confidence_map'] = confidence_map
            
            logger.info(f"Disparidad calculada - Píxeles válidos: {disparity_result['valid_pixels']}/{disparity_left.size}")
            
            return disparity_result
    
    def compute_confidence_map(self, disparity: np.ndarray) -> np.ndarray:
        """
        Calcular mapa de confianza para la disparidad

        Penaliza:
        - Píxeles sin vecinos válidos (aislados)
        - Cambios abruptos de disparidad (ruido)
        - Regiones con alta varianza local (inconsistencia)
        """

        # Inicializar mapa de confianza
        confidence = np.zeros(disparity.shape, dtype=np.float32)

        # Confianza basada en validez de píxeles
        valid_mask = disparity > 0
        confidence[valid_mask] = 1.0

        # === FILTRO 1: Densidad de vecinos válidos ===
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 7))  # Aumentado de 5 a 7

        # Contar vecinos válidos
        valid_count = cv2.morphologyEx(valid_mask.astype(np.uint8), cv2.MORPH_CLOSE, kernel)
        valid_count = cv2.filter2D(valid_count.astype(np.float32), -1, np.ones((7, 7)) / 49)

        # Ajustar confianza basada en densidad local
        confidence *= valid_count

        # === FILTRO 2: Gradiente de disparidad (cambios abruptos) ===
        disparity_grad = np.abs(cv2.Sobel(disparity, cv2.CV_32F, 1, 0, ksize=3)) + \
                        np.abs(cv2.Sobel(disparity, cv2.CV_32F, 0, 1, ksize=3))

        # CRÍTICO: Limpiar infinitos antes de normalizar
        disparity_grad[~np.isfinite(disparity_grad)] = 0

        # Normalizar gradiente solo si hay valores válidos
        max_grad = np.max(disparity_grad)
        if max_grad > 0 and np.isfinite(max_grad):
            grad_normalized = disparity_grad / max_grad
        else:
            grad_normalized = np.zeros_like(disparity_grad)

        # AUMENTADO: Penalización más agresiva de gradientes altos (reduce "vitiligo")
        confidence *= (1.0 - grad_normalized * 0.8)  # Cambiado de 0.5 a 0.8

        # === FILTRO 3: Varianza local (consistencia) ===
        # Calcular desviación estándar local en ventana 7x7
        mean_local = cv2.boxFilter(disparity, cv2.CV_32F, (7, 7))
        mean_sq_local = cv2.boxFilter(disparity**2, cv2.CV_32F, (7, 7))
        variance_local = mean_sq_local - mean_local**2
        variance_local = np.maximum(variance_local, 0)  # Evitar negativos por errores numéricos
        std_local = np.sqrt(variance_local)

        # Normalizar varianza (0-1)
        max_std = np.max(std_local[valid_mask]) if np.any(valid_mask) else 1.0
        if max_std > 0:
            std_normalized = std_local / max_std
        else:
            std_normalized = np.zeros_like(std_local)

        # Penalizar alta varianza local (regiones ruidosas)
        confidence *= (1.0 - std_normalized * 0.5)

        # Asegurar rango [0, 1]
        confidence = np.clip(confidence, 0.0, 1.0)

        return confidence
    
    def disparity_to_depth(self, disparity: np.ndarray,
                          mask_invalid: bool = True) -> Dict[str, Any]:
        """Convertir mapa de disparidad a profundidad"""

        with PerformanceLogger("Conversión disparidad a profundidad", logger):

            # Obtener matriz Q de calibración
            Q = self.calibration_data.get('disparity_to_depth_matrix')
            if Q is None:
                raise RuntimeError("Matriz Q no disponible en calibración")

            # CRÍTICO: Asegurar que Q es un numpy array
            if not isinstance(Q, np.ndarray):
                logger.warning(f"Matriz Q es tipo {type(Q)}, convirtiendo a numpy array...")
                Q = np.array(Q)

            # Validar forma de Q
            if Q.shape != (4, 4):
                raise RuntimeError(f"Matriz Q tiene forma incorrecta: {Q.shape}, se esperaba (4, 4)")

            # DEBUG: Mostrar matriz Q
            logger.info(f"🔍 DEBUG Matriz Q:")
            logger.info(f"   Q[3,2] = {Q[3, 2]:.6f} (usado para baseline)")
            logger.info(f"   Q[2,3] = {Q[2, 3]:.6f} (focal length)")

            # Obtener baseline y focal length de Q
            baseline = abs(1.0 / Q[3, 2])  # Baseline en metros
            focal_length = Q[2, 3]         # Focal length en píxeles

            logger.info(f"🔍 DEBUG Parámetros de profundidad:")
            logger.info(f"   Baseline: {baseline:.4f} m")
            logger.info(f"   Focal length: {focal_length:.2f} px")

            # DEBUG: Estadísticas de disparidad (solo píxeles válidos)
            valid_disp_debug = disparity[disparity > 0]
            logger.info(f"🔍 DEBUG Disparidad de entrada:")
            logger.info(f"   Shape: {disparity.shape}")
            if len(valid_disp_debug) > 0:
                logger.info(f"   Min (válido): {np.min(valid_disp_debug):.2f}, Max (válido): {np.max(valid_disp_debug):.2f}")
                logger.info(f"   Mean (válido): {np.mean(valid_disp_debug):.2f}, Median (válido): {np.median(valid_disp_debug):.2f}")
            logger.info(f"   Píxeles > 0: {np.sum(disparity > 0)}")
            logger.info(f"   Píxeles > 0.1: {np.sum(disparity > 0.1)}")

            # Crear máscara para píxeles válidos
            valid_mask = disparity > 0.1  # Evitar división por cerca de cero
            logger.info(f"🔍 DEBUG Máscara válida: {np.sum(valid_mask)} píxeles válidos")

            # Inicializar mapa de profundidad
            depth_map = np.zeros_like(disparity, dtype=np.float32)

            # Calcular profundidad: Z = (baseline * focal_length) / disparidad
            if np.sum(valid_mask) > 0:
                depth_map[valid_mask] = (baseline * focal_length) / disparity[valid_mask]
                logger.info(f"🔍 DEBUG Profundidad calculada (antes de filtros):")
                logger.info(f"   Min: {np.min(depth_map[valid_mask]):.2f}m")
                logger.info(f"   Max: {np.max(depth_map[valid_mask]):.2f}m")
                logger.info(f"   Mean: {np.mean(depth_map[valid_mask]):.2f}m")
            else:
                logger.error("❌ No hay píxeles válidos en disparidad!")

            # Filtrar profundidades fuera de rango razonable
            # AJUSTADO: Rango realista para entorno interior pequeño
            min_depth = 0.3   # 30cm mínimo (evita puntos muy cercanos inestables)
            max_depth = 5.0   # 5m máximo (adecuado para cuarto pequeño)

            range_mask = (depth_map >= min_depth) & (depth_map <= max_depth)
            final_mask = valid_mask & range_mask

            logger.info(f"🔍 DEBUG Después de filtro de rango [{min_depth}m - {max_depth}m]:")
            logger.info(f"   Píxeles válidos: {np.sum(final_mask)}")
            
            if mask_invalid:
                depth_map[~final_mask] = 0.0
            
            depth_result = {
                'depth_map': depth_map,
                'valid_mask': final_mask,
                'baseline_meters': baseline,
                'focal_length_pixels': focal_length,
                'min_depth': float(np.min(depth_map[final_mask])) if np.any(final_mask) else 0.0,
                'max_depth': float(np.max(depth_map[final_mask])) if np.any(final_mask) else 0.0,
                'mean_depth': float(np.mean(depth_map[final_mask])) if np.any(final_mask) else 0.0,
                'valid_pixels': int(np.sum(final_mask)),
                'depth_range_meters': [min_depth, max_depth]
            }
            
            logger.info(f"Profundidad calculada - Rango: {depth_result['min_depth']:.2f}m - {depth_result['max_depth']:.2f}m")
            
            return depth_result
    
    def generate_point_cloud(self, left_img: np.ndarray, disparity: np.ndarray,
                           depth_map: np.ndarray, confidence_map: np.ndarray = None,
                           min_confidence: float = 0.5) -> Dict[str, Any]:
        """Generar nube de puntos 3D"""

        with PerformanceLogger("Generación de nube de puntos", logger):

            # Obtener matriz Q
            Q = self.calibration_data.get('disparity_to_depth_matrix')
            if Q is None:
                raise RuntimeError("Matriz Q no disponible")

            # CRÍTICO: Asegurar que Q es un numpy array
            if not isinstance(Q, np.ndarray):
                logger.warning(f"Matriz Q es tipo {type(Q)}, convirtiendo a numpy array...")
                Q = np.array(Q)

            height, width = disparity.shape
            logger.info(f"🔍 DEBUG Nube de puntos - Tamaño imagen: {height}x{width} = {height*width} píxeles")

            # Máscara de píxeles válidos - AUMENTADO umbral para evitar disparidades muy bajas
            # Disparidades < 5 píxeles generan profundidades > 40m (absurdas para indoor)
            # Con baseline=103mm y focal=2010px: Z = (baseline*focal)/disparity
            # disparity=5 → Z≈4m, disparity=10 → Z≈2m
            valid_mask = disparity > 10.0  # Aumentado de 0.1 a 10 para evitar outliers
            logger.info(f"🔍 DEBUG Píxeles con disparidad > 10.0: {np.sum(valid_mask)}")

            # Aplicar filtro de confianza si está disponible
            if confidence_map is not None:
                confidence_mask = confidence_map >= min_confidence
                valid_mask = valid_mask & confidence_mask
                logger.info(f"🔍 DEBUG Píxeles después de filtro confianza: {np.sum(valid_mask)}")

            num_valid = np.sum(valid_mask)
            if num_valid == 0:
                logger.error("❌ No hay píxeles válidos para generar nube de puntos!")
                return {
                    'points': np.array([]),
                    'colors': np.array([]),
                    'confidence': None,
                    'num_points': 0,
                    'bounds': {},
                    'density': 0.0
                }

            # Estimación de memoria requerida
            memory_mb = (num_valid * 4 * 7 * 4) / (1024 * 1024)  # 7 arrays de float32
            logger.info(f"🔍 DEBUG Memoria estimada: {memory_mb:.1f} MB para {num_valid} puntos")

            # OPTIMIZACIÓN: Crear grilla solo para píxeles válidos (ahorra memoria)
            logger.info(f"🔍 DEBUG Extrayendo coordenadas válidas...")
            y_indices, x_indices = np.where(valid_mask)

            # Extraer píxeles válidos
            valid_disp = disparity[valid_mask]
            valid_depth = depth_map[valid_mask]

            logger.info(f"🔍 DEBUG Creando puntos homogéneos...")
            # Calcular coordenadas 3D usando Q
            # Crear puntos homogéneos (evitar crear array gigante innecesario)
            points_2d = np.column_stack([x_indices, y_indices, valid_disp, np.ones(num_valid, dtype=np.float32)])

            logger.info(f"🔍 DEBUG Transformando a 3D con matriz Q...")
            # Transformar a 3D
            points_3d_h = np.dot(Q, points_2d.T)

            logger.info(f"🔍 DEBUG Convirtiendo de homogéneo a cartesiano...")
            # Convertir de homogéneo a cartesiano
            points_3d = points_3d_h[:3] / points_3d_h[3]
            points_3d = points_3d.T

            # Liberar memoria
            del points_2d, points_3d_h
            
            logger.info(f"🔍 DEBUG Extrayendo colores...")
            # Extraer colores de la imagen izquierda
            if len(left_img.shape) == 3:
                colors = left_img[valid_mask] / 255.0  # Normalizar a [0, 1]
            else:
                # Imagen en escala de grises, convertir a RGB
                gray_colors = left_img[valid_mask] / 255.0
                colors = np.column_stack([gray_colors, gray_colors, gray_colors])

            logger.info(f"🔍 DEBUG Filtrando puntos por profundidad y límites espaciales...")

            # DEBUG: Mostrar estadísticas de coordenadas 3D
            logger.info(f"🔍 DEBUG Estadísticas de points_3d (antes de filtros):")
            logger.info(f"   X - Min: {np.min(points_3d[:, 0]):.2f}m, Max: {np.max(points_3d[:, 0]):.2f}m")
            logger.info(f"   Y - Min: {np.min(points_3d[:, 1]):.2f}m, Max: {np.max(points_3d[:, 1]):.2f}m")
            logger.info(f"   Z - Min: {np.min(points_3d[:, 2]):.2f}m, Max: {np.max(points_3d[:, 2]):.2f}m")

            # Filtrar usando valid_depth (profundidad real calculada)
            depth_filter = (valid_depth > 0.3) & (valid_depth < 5.0)

            # Filtrar coordenadas 3D absurdas (causadas por disparidades muy bajas)
            # Para escenas indoor a 1-5m, las coordenadas X,Y deben estar en rango razonable
            # Con FOV de ~60°, a 5m de profundidad, X,Y máximo ≈ ±3m desde el centro
            x_abs = np.abs(points_3d[:, 0])
            y_abs = np.abs(points_3d[:, 1])
            z_abs = np.abs(points_3d[:, 2])

            # Filtro conservador: eliminar solo outliers extremos
            x_filter = x_abs < 50.0  # Más restrictivo que antes
            y_filter = y_abs < 50.0
            z_filter = z_abs < 50.0  # Eliminar puntos a >50m en cualquier eje

            # Combinar todos los filtros
            combined_filter = depth_filter & x_filter & y_filter & z_filter
            num_after_filter = np.sum(combined_filter)
            logger.info(f"🔍 DEBUG Puntos después de filtros: {num_after_filter}/{len(points_3d)}")
            logger.info(f"   - Filtro profundidad (0.3-5.0m): {np.sum(depth_filter)} puntos")
            logger.info(f"   - Filtro X (±50m): {np.sum(x_filter)} puntos")
            logger.info(f"   - Filtro Y (±50m): {np.sum(y_filter)} puntos")
            logger.info(f"   - Filtro Z (±50m): {np.sum(z_filter)} puntos")

            final_points = points_3d[combined_filter]
            final_colors = colors[combined_filter]
            final_confidence = confidence_map[valid_mask][combined_filter] if confidence_map is not None else None

            # Liberar memoria
            del points_3d, colors, valid_mask, y_indices, x_indices
            
            point_cloud_result = {
                'points': final_points,
                'colors': final_colors,
                'confidence': final_confidence,
                'num_points': len(final_points),
                'bounds': {
                    'x_min': float(np.min(final_points[:, 0])) if len(final_points) > 0 else 0.0,
                    'x_max': float(np.max(final_points[:, 0])) if len(final_points) > 0 else 0.0,
                    'y_min': float(np.min(final_points[:, 1])) if len(final_points) > 0 else 0.0,
                    'y_max': float(np.max(final_points[:, 1])) if len(final_points) > 0 else 0.0,
                    'z_min': float(np.min(final_points[:, 2])) if len(final_points) > 0 else 0.0,
                    'z_max': float(np.max(final_points[:, 2])) if len(final_points) > 0 else 0.0,
                },
                'density': len(final_points) / (height * width) if height * width > 0 else 0.0
            }
            
            logger.info(f"Nube de puntos generada: {point_cloud_result['num_points']} puntos")
            logger.info(f"Densidad: {point_cloud_result['density']:.4f}")
            
            return point_cloud_result
    
    def process_stereo_pair(self, left_img: np.ndarray, right_img: np.ndarray,
                           algorithm: str = "SGBM", progress_callback: Callable = None,
                           save_debug_images: bool = False) -> Dict[str, Any]:
        """Procesar par estéreo completo"""
        
        processing_start = datetime.now()
        
        try:
            logger.info(f"Iniciando procesamiento estéreo - Algoritmo: {algorithm}")
            
            if progress_callback:
                progress_callback(10, "Rectificando imágenes...")
            
            # 1. Rectificar imágenes
            left_rect, right_rect = self.rectify_images(left_img, right_img)

            # Guardar imágenes de depuración si se solicita
            if save_debug_images:
                debug_path = Path("data/results/debug")
                debug_path.mkdir(parents=True, exist_ok=True)

                # PASO 1: Guardar imágenes ORIGINALES
                cv2.imwrite(str(debug_path / "01_left_original.jpg"), left_img)
                cv2.imwrite(str(debug_path / "02_right_original.jpg"), right_img)

                # PASO 2: Guardar imágenes RECTIFICADAS
                cv2.imwrite(str(debug_path / "03_left_rectified.jpg"), left_rect)
                cv2.imwrite(str(debug_path / "04_right_rectified.jpg"), right_rect)

                # PASO 3: Dibujar líneas epipolares para verificar rectificación
                left_epi = left_rect.copy()
                right_epi = right_rect.copy()
                for y in range(0, left_rect.shape[0], 100):  # Cada 100 píxeles
                    cv2.line(left_epi, (0, y), (left_rect.shape[1], y), (0, 255, 0), 1)
                    cv2.line(right_epi, (0, y), (right_rect.shape[1], y), (0, 255, 0), 1)
                cv2.imwrite(str(debug_path / "05_left_epipolar_lines.jpg"), left_epi)
                cv2.imwrite(str(debug_path / "06_right_epipolar_lines.jpg"), right_epi)

                # PASO 4: Crear imagen side-by-side para comparar
                side_by_side = np.hstack([left_rect, right_rect])
                for y in range(0, side_by_side.shape[0], 100):
                    cv2.line(side_by_side, (0, y), (side_by_side.shape[1], y), (0, 255, 0), 1)
                cv2.imwrite(str(debug_path / "07_side_by_side_epipolar.jpg"), side_by_side)

                # PASO 5: Guardar máscara ROI
                if self.valid_roi_mask is not None:
                    mask_vis = (self.valid_roi_mask.astype(np.uint8) * 255)
                    cv2.imwrite(str(debug_path / "08_roi_mask.png"), mask_vis)

                logger.info(f"🔍 DEBUG Imágenes de rectificación guardadas en {debug_path}")

            if progress_callback:
                progress_callback(30, "Calculando disparidad...")
            
            # 2. Calcular disparidad
            disparity_result = self.compute_disparity(left_rect, right_rect, algorithm, use_wls_filter=True)
            
            if progress_callback:
                progress_callback(60, "Convirtiendo a profundidad...")
            
            # 3. Convertir a profundidad
            depth_result = self.disparity_to_depth(disparity_result['disparity_map'])
            
            if progress_callback:
                progress_callback(80, "Generando nube de puntos...")
            
            # 4. Generar nube de puntos
            point_cloud_result = self.generate_point_cloud(
                left_rect,
                disparity_result['disparity_map'],
                depth_result['depth_map'],
                disparity_result.get('confidence_map'),
                min_confidence=0.5  # AUMENTADO: de 0.3 a 0.5 para filtrar más ruido
            )

            # Guardar mapas de depuración adicionales
            if save_debug_images:
                debug_path = Path("data/results/debug")

                # PASO 9: MAPA DE DISPARIDAD RAW (sin filtrar)
                disp_map_raw = disparity_result.get('disparity_before_smoothing', disparity_result['disparity_map'])
                disp_raw_vis = cv2.normalize(disp_map_raw, None, 0, 255, cv2.NORM_MINMAX, dtype=cv2.CV_8U)
                disp_raw_color = cv2.applyColorMap(disp_raw_vis, cv2.COLORMAP_JET)
                disp_raw_color[disp_map_raw <= 0] = [0, 0, 0]
                cv2.imwrite(str(debug_path / "09_disparity_raw.png"), disp_raw_color)

                # PASO 10: MAPA DE DISPARIDAD FINAL (suavizado)
                disp_map = disparity_result['disparity_map']
                disp_vis = cv2.normalize(disp_map, None, 0, 255, cv2.NORM_MINMAX, dtype=cv2.CV_8U)
                disp_color = cv2.applyColorMap(disp_vis, cv2.COLORMAP_JET)
                disp_color[disp_map <= 0] = [0, 0, 0]
                cv2.imwrite(str(debug_path / "10_disparity_final.png"), disp_color)

                # PASO 11: OVERLAY de disparidad sobre imagen original
                # Redimensionar disparidad a escala de grises
                disp_overlay = cv2.addWeighted(left_rect, 0.5, cv2.cvtColor(disp_color, cv2.COLOR_BGR2RGB), 0.5, 0)
                cv2.imwrite(str(debug_path / "11_disparity_overlay.jpg"), disp_overlay)

                # PASO 12: MAPA DE CONFIANZA
                conf_map = disparity_result.get('confidence_map')
                if conf_map is not None:
                    conf_vis = (conf_map * 255).astype(np.uint8)
                    conf_color = cv2.applyColorMap(conf_vis, cv2.COLORMAP_HOT)
                    cv2.imwrite(str(debug_path / "12_confidence_map.png"), conf_color)

                # PASO 13: MAPA DE PROFUNDIDAD (depth en metros)
                depth_map = depth_result['depth_map']
                # Crear visualización con valores reales
                depth_for_vis = depth_map.copy()
                depth_for_vis[depth_map <= 0] = 0
                depth_for_vis[depth_map > 5.0] = 0  # Limitar para visualización
                depth_vis = cv2.normalize(depth_for_vis, None, 0, 255, cv2.NORM_MINMAX, dtype=cv2.CV_8U)
                depth_color = cv2.applyColorMap(depth_vis, cv2.COLORMAP_TURBO)
                depth_color[depth_map <= 0] = [0, 0, 0]
                cv2.imwrite(str(debug_path / "13_depth_map.png"), depth_color)

                # PASO 14: HISTOGRAMA de disparidad
                import matplotlib.pyplot as plt
                plt.figure(figsize=(10, 6))
                valid_disp = disp_map[disp_map > 0]
                plt.hist(valid_disp, bins=100, color='blue', alpha=0.7)
                plt.xlabel('Disparidad (píxeles)')
                plt.ylabel('Frecuencia')
                plt.title(f'Histograma de Disparidad\nMin: {np.min(valid_disp):.2f}, Max: {np.max(valid_disp):.2f}, Mean: {np.mean(valid_disp):.2f}')
                plt.grid(True, alpha=0.3)
                plt.savefig(str(debug_path / "14_disparity_histogram.png"))
                plt.close()

                # PASO 15: VISUALIZACIÓN de correspondencias (sample)
                # Tomar algunos puntos de la mano y mostrar correspondencias
                self._save_correspondence_debug(left_rect, right_rect, disp_map, debug_path)

                # Crear README explicando cada imagen
                readme_content = """# DEBUG - Proceso de Reconstrucción 3D Paso a Paso

## Orden de Procesamiento:

01_left_original.jpg       - Imagen original IZQUIERDA (sin rectificar)
02_right_original.jpg      - Imagen original DERECHA (sin rectificar)

03_left_rectified.jpg      - Imagen izquierda RECTIFICADA (distorsión corregida)
04_right_rectified.jpg     - Imagen derecha RECTIFICADA (distorsión corregida)

05_left_epipolar_lines.jpg - Imagen izquierda con LÍNEAS EPIPOLARES
06_right_epipolar_lines.jpg- Imagen derecha con LÍNEAS EPIPOLARES
                             (Las líneas verdes deben estar a la misma altura en ambas)

07_side_by_side_epipolar.jpg - Comparación lado a lado con líneas epipolares
                                (Verifica que objetos están a la misma altura)

08_roi_mask.png             - MÁSCARA DE REGIÓN VÁLIDA
                              (Blanco=válido, Negro=bordes descartados)

09_disparity_raw.png        - MAPA DE DISPARIDAD SIN FILTRAR
                              (Rojo=cerca, Azul=lejos, Negro=sin dato)

10_disparity_final.png      - MAPA DE DISPARIDAD FINAL (suavizado)
                              (Rojo=cerca, Azul=lejos, Negro=sin dato)

11_disparity_overlay.jpg    - OVERLAY: Disparidad sobre imagen original
                              (Ayuda a ver qué objeto tiene qué profundidad)

12_confidence_map.png       - MAPA DE CONFIANZA
                              (Amarillo/Blanco=alta confianza, Negro=baja)

13_depth_map.png            - MAPA DE PROFUNDIDAD en metros
                              (Colores representan distancia real en metros)

14_disparity_histogram.png  - HISTOGRAMA DE DISPARIDAD
                              (Distribución de valores de disparidad)

15_correspondences.jpg      - CORRESPONDENCIAS ENTRE IMÁGENES
                              (Muestra cómo se matchean puntos entre left/right)
                              Las líneas conectan el MISMO punto en ambas imágenes.
                              La longitud de la línea = disparidad

## Cómo Interpretar:

- Si las líneas epipolares NO están alineadas → Problema de rectificación
- Si el mapa de disparidad es muy ruidoso → Problema de matching/textura
- Si las correspondencias no tienen sentido → Problema de calibración
- Si la profundidad está invertida → Problema con matriz Q o baseline
"""
                with open(debug_path / "README.txt", "w", encoding='utf-8') as f:
                    f.write(readme_content)

                logger.info(f"🔍 DEBUG Todos los mapas guardados en {debug_path}")
                logger.info(f"🔍 DEBUG Lee {debug_path / 'README.txt'} para entender cada imagen")

            if progress_callback:
                progress_callback(100, "Procesamiento completado")
            
            # Compilar resultados
            processing_time = (datetime.now() - processing_start).total_seconds()
            
            complete_result = {
                'success': True,
                'processing_time_seconds': processing_time,
                'timestamp': processing_start.isoformat(),
                'input_shape': left_img.shape,
                'algorithm_used': algorithm,
                'rectified_images': {
                    'left': left_rect,
                    'right': right_rect
                },
                'disparity': disparity_result,
                'depth': depth_result,
                'point_cloud': point_cloud_result,
                'quality_metrics': {
                    'valid_pixel_ratio': disparity_result['valid_pixels'] / (left_img.shape[0] * left_img.shape[1]),
                    'mean_confidence': float(np.mean(disparity_result['confidence_map'])),
                    'point_density': point_cloud_result['density']
                }
            }
            
            logger.info(f"Procesamiento estéreo completado en {processing_time:.2f}s")
            logger.info(f"Píxeles válidos: {complete_result['quality_metrics']['valid_pixel_ratio']:.1%}")
            
            return complete_result
            
        except Exception as e:
            logger.error(f"Error en procesamiento estéreo: {e}")
            return {
                'success': False,
                'error': str(e),
                'processing_time_seconds': (datetime.now() - processing_start).total_seconds()
            }

if __name__ == "__main__":
    # Test del procesador estéreo
    from config.camera_config import CameraConfig
    
    try:
        print("Probando procesador estéreo...")
        
        # Crear configuración mock para testing
        config = CameraConfig()
        
        # Simular que está calibrado
        config.calibration_data['is_calibrated'] = True
        config.calibration_data['disparity_to_depth_matrix'] = np.eye(4, dtype=np.float32)
        
        processor = StereoProcessor(config)
        print("✓ Procesador inicializado")
        
        # Test con imágenes sintéticas
        left_test = np.random.randint(0, 255, (480, 640, 3), dtype=np.uint8)
        right_test = np.random.randint(0, 255, (480, 640, 3), dtype=np.uint8)
        
        left_proc, right_proc = processor.preprocess_images(left_test, right_test)
        print(f"✓ Preprocesamiento - Forma: {left_proc.shape}")
        
    except Exception as e:
        print(f"✗ Error: {e}")
        import sys
        sys.exit(1)