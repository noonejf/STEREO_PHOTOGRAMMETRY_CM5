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
from processing.wire_matcher import WireMatcher

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

        # Inicializar matcher guiado para cables
        self.wire_matcher = None  # Se inicializa on-demand

        logger.info("Procesador estéreo inicializado")
    
    def _save_correspondence_debug(self, left_img, right_img, disparity, debug_path):
        """
        Guardar visualización de correspondencias de puntos entre imágenes
        Muestra cómo se matchean los puntos entre left y right

        CORREGIDO: Ahora busca puntos en TODA la imagen con disparidad válida,
        no solo en grid hardcodeado.
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

        # NUEVO: Encontrar puntos con MEJOR disparidad (no hardcodeados)
        # Ordenar píxeles por disparidad (de mayor a menor)
        valid_mask = disparity > 1.0  # Umbral mínimo realista
        valid_indices = np.argwhere(valid_mask)

        if len(valid_indices) == 0:
            logger.warning("⚠️ No hay puntos con disparidad válida para visualizar")
            cv2.imwrite(str(debug_path / "15_correspondences.jpg"), combined)
            return

        # Extraer disparidades de puntos válidos
        valid_disparities = disparity[valid_mask]

        # Ordenar índices por disparidad (mayor primero = más cerca)
        sorted_indices = np.argsort(valid_disparities)[::-1]

        # Tomar muestra espaciada de mejores puntos
        # Estrategia: dividir en bins de profundidad y tomar samples de cada bin
        num_bins = 5
        num_per_bin = 10
        max_points = num_bins * num_per_bin

        # Dividir disparidades en bins
        disp_min, disp_max = np.min(valid_disparities), np.max(valid_disparities)
        if disp_max - disp_min < 1e-6:
            # Todas las disparidades son iguales, tomar muestra uniforme
            sample_indices = sorted_indices[::max(1, len(sorted_indices)//max_points)][:max_points]
        else:
            sample_indices = []
            bin_edges = np.linspace(disp_min, disp_max, num_bins + 1)

            for i in range(num_bins):
                bin_mask = (valid_disparities >= bin_edges[i]) & (valid_disparities < bin_edges[i+1])
                bin_indices = sorted_indices[bin_mask]

                if len(bin_indices) > 0:
                    # Tomar muestra espaciada de este bin
                    step = max(1, len(bin_indices) // num_per_bin)
                    sample_indices.extend(bin_indices[::step][:num_per_bin])

            sample_indices = np.array(sample_indices[:max_points])

        colors = [(0, 255, 0), (255, 0, 0), (0, 0, 255), (255, 255, 0), (255, 0, 255), (0, 255, 255)]

        points_drawn = 0
        for idx in sample_indices:
            # CORREGIDO: Acceder directamente a valid_indices
            y, x = valid_indices[idx]
            d = disparity[y, x]

            # Punto en imagen izquierda
            color = colors[points_drawn % len(colors)]
            cv2.circle(combined, (x, y), 5, color, -1)
            cv2.circle(combined, (x, y), 6, (255, 255, 255), 1)  # Borde blanco

            # Punto correspondiente en imagen derecha (desplazado por disparidad)
            x_right = int(x - d) + w  # -d porque búsqueda es hacia la izquierda
            if 0 <= x_right - w < w:
                cv2.circle(combined, (x_right, y), 5, color, -1)
                cv2.circle(combined, (x_right, y), 6, (255, 255, 255), 1)

                # Dibujar línea conectando correspondencias
                cv2.line(combined, (x, y), (x_right, y), color, 2)

                # Etiqueta con disparidad
                text = f"{d:.1f}px"
                cv2.putText(combined, text, (x, y-10), cv2.FONT_HERSHEY_SIMPLEX,
                           0.4, (255, 255, 255), 1, cv2.LINE_AA)

                points_drawn += 1

        # Agregar leyenda
        legend_y = 30
        cv2.putText(combined, f"Correspondencias: {points_drawn} puntos", (10, legend_y),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2, cv2.LINE_AA)
        cv2.putText(combined, f"Disp min: {disp_min:.1f}px, max: {disp_max:.1f}px",
                   (10, legend_y+30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2, cv2.LINE_AA)

        cv2.imwrite(str(debug_path / "15_correspondences.jpg"), combined)
        logger.info(f"🔍 DEBUG Correspondencias guardadas: {points_drawn} puntos (disp: {disp_min:.1f}-{disp_max:.1f}px)")

    def setup_stereo_algorithms(self):
        """Configurar algoritmos de matching estéreo"""

        # Algoritmo SGBM (Semi-Global Block Matching) - Recomendado
        # CONFIGURACIÓN BASE - Sin modificaciones agresivas
        self.sgbm = cv2.StereoSGBM_create(
            minDisparity=0,
            numDisparities=16*32,     # AUMENTADO: 64→512 (permite objetos muy cercanos hasta ~20cm)
            blockSize=17,             # BALANCEADO: 15→17 (compromiso entre contexto y detalle)
            P1=8 * 3 * 17**2,        # Ajustado para blockSize=17
            P2=32 * 3 * 17**2,       # Ajustado para blockSize=17
            disp12MaxDiff=1,          # OK: Verificación izq-der
            uniquenessRatio=5,        # BALANCEADO: 0→5 (permite matches pero con mínima confianza)
            speckleWindowSize=50,     # BALANCEADO: 100→50 (filtra speckles sin ser agresivo)
            speckleRange=16,          # AUMENTADO: 8→16 (más tolerante a variación)
            preFilterCap=61,          # OK: Como TESIS
            mode=cv2.STEREO_SGBM_MODE_SGBM_3WAY  # OK: Modo 3-way
        )

        # CONFIGURACIÓN ESPECIALIZADA para objetos FINOS (cables, hilos)
        # Usar blockSize pequeño para capturar detalles finos
        self.sgbm_fine = cv2.StereoSGBM_create(
            minDisparity=0,
            numDisparities=16*32,     # Mismo rango de disparidad
            blockSize=5,              # PEQUEÑO: 17→5 (crítico para cables finos)
            P1=8 * 3 * 5**2,         # Ajustado para blockSize=5 (penalización pequeña)
            P2=32 * 3 * 5**2,        # Ajustado para blockSize=5 (penalización moderada)
            disp12MaxDiff=1,          # Verificación estricta
            uniquenessRatio=10,       # AUMENTADO: 5→10 (más conservador con matches ambiguos)
            speckleWindowSize=100,    # Filtrar ruido aislado
            speckleRange=32,          # Tolerante a variación en cable
            preFilterCap=63,          # Máximo rango para preservar detalles
            mode=cv2.STEREO_SGBM_MODE_SGBM_3WAY
        )

        # Algoritmo BM (Block Matching) - Más rápido pero menos preciso
        self.bm = cv2.StereoBM_create(
            numDisparities=96,
            blockSize=15
        )

        # Filtro WLS para post-procesamiento (para SGBM estándar)
        self.wls_filter = cv2.ximgproc.createDisparityWLSFilter(self.sgbm)
        self.wls_filter.setLambda(8000.0)  # RESTAURADO: Lambda alto para suavizado efectivo
        self.wls_filter.setSigmaColor(1.5)  # AUMENTADO: 1.2→1.5 (más tolerante a cambios de color)

        # Filtro WLS para algoritmo fino (menos agresivo para preservar detalles)
        self.wls_filter_fine = cv2.ximgproc.createDisparityWLSFilter(self.sgbm_fine)
        self.wls_filter_fine.setLambda(4000.0)  # REDUCIDO: Menos suavizado para cables finos
        self.wls_filter_fine.setSigmaColor(1.0)  # Preservar cambios de intensidad del cable

        # Crear matchers derechos para verificación cruzada
        self.right_matcher = cv2.ximgproc.createRightMatcher(self.sgbm)
        self.right_matcher_fine = cv2.ximgproc.createRightMatcher(self.sgbm_fine)

        # CRÍTICO: NO necesitamos sobrescribir parámetros después de createRightMatcher
        # Los valores ya están correctamente configurados en create() arriba
        # (Eliminado código redundante que causaba inconsistencias)
        
        logger.info("Algoritmos de matching estéreo configurados")
    
    def detect_foreground_object_mask(self, img: np.ndarray, debug_name: str = "") -> np.ndarray:
        """
        Detectar objeto de interés en imagen con fondo uniforme oscuro

        Estrategia para cable blanco en fondo oscuro:
        1. Detección de bordes agresiva (el cable tiene bordes fuertes)
        2. Umbralización por brillo (cable es mucho más brillante que fondo)
        3. Morfología para conectar píxeles del cable
        """

        # Convertir a escala de grises
        if len(img.shape) == 3:
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        else:
            gray = img.copy()

        # === ESTRATEGIA 1: Detección por BRILLO ===
        # El cable blanco es MUCHO más brillante que el fondo morado
        # Calcular umbral adaptativo basado en estadísticas
        mean_intensity = np.mean(gray)
        std_intensity = np.std(gray)

        # Umbral: media + 2 desviaciones estándar (captura solo píxeles brillantes)
        brightness_threshold = mean_intensity + 2.0 * std_intensity
        mask_bright = gray > brightness_threshold

        logger.info(f"🔍 DEBUG Máscara de brillo - Umbral: {brightness_threshold:.1f}, Píxeles: {np.sum(mask_bright)}")

        # === ESTRATEGIA 2: Detección de BORDES ===
        # Aplicar Canny para detectar bordes fuertes
        # Reducir blur para preservar cables finos
        blurred = cv2.GaussianBlur(gray, (3, 3), 0)  # Blur mínimo
        edges = cv2.Canny(blurred, threshold1=30, threshold2=100, apertureSize=3)

        # Dilatar bordes para crear región alrededor del cable
        kernel_edges = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
        edges_dilated = cv2.dilate(edges, kernel_edges, iterations=2)

        logger.info(f"🔍 DEBUG Máscara de bordes - Píxeles: {np.sum(edges_dilated > 0)}")

        # === COMBINAR ESTRATEGIAS ===
        # Union de máscara de brillo + bordes
        mask_combined = (mask_bright | (edges_dilated > 0)).astype(np.uint8)

        # === MORFOLOGÍA: Conectar componentes del cable ===
        # Cerrar gaps pequeños en el cable
        kernel_close = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
        mask_closed = cv2.morphologyEx(mask_combined, cv2.MORPH_CLOSE, kernel_close, iterations=2)

        # Dilatar ligeramente para capturar región alrededor del cable
        kernel_dilate = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 7))
        mask_final = cv2.dilate(mask_closed, kernel_dilate, iterations=1)

        logger.info(f"🔍 DEBUG Máscara final - Píxeles: {np.sum(mask_final > 0)} ({100*np.sum(mask_final)/(mask_final.size):.2f}%)")

        # Guardar máscara de debug si se proporciona nombre
        if debug_name:
            debug_path = Path("data/results/debug")
            debug_path.mkdir(parents=True, exist_ok=True)
            cv2.imwrite(str(debug_path / f"{debug_name}_object_mask.png"), mask_final * 255)

            # Guardar visualización con máscara superpuesta
            vis = img.copy()
            if len(vis.shape) == 2:
                vis = cv2.cvtColor(vis, cv2.COLOR_GRAY2BGR)
            vis[mask_final > 0] = [0, 255, 0]  # Verde para objeto detectado
            cv2.imwrite(str(debug_path / f"{debug_name}_object_overlay.jpg"),
                       cv2.addWeighted(img if len(img.shape) == 3 else cv2.cvtColor(img, cv2.COLOR_GRAY2BGR),
                                     0.7, vis, 0.3, 0))

        return mask_final

    def preprocess_images(self, left_img: np.ndarray, right_img: np.ndarray,
                         use_edge_enhancement: bool = False) -> Tuple[np.ndarray, np.ndarray]:
        """
        Preprocesar imágenes para matching estéreo

        Args:
            use_edge_enhancement: Si True, realza bordes para mejorar matching en objetos finos
        """

        # Convertir a escala de grises si es necesario
        if len(left_img.shape) == 3:
            left_gray = cv2.cvtColor(left_img, cv2.COLOR_BGR2GRAY)
        else:
            left_gray = left_img.copy()

        if len(right_img.shape) == 3:
            right_gray = cv2.cvtColor(right_img, cv2.COLOR_BGR2GRAY)
        else:
            right_gray = right_img.copy()

        if use_edge_enhancement:
            # Realzar bordes usando gradiente morfológico
            kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))

            # Gradiente morfológico = dilatación - erosión (resalta bordes)
            left_grad = cv2.morphologyEx(left_gray, cv2.MORPH_GRADIENT, kernel)
            right_grad = cv2.morphologyEx(right_gray, cv2.MORPH_GRADIENT, kernel)

            # Combinar imagen original + gradiente (50/50)
            left_gray = cv2.addWeighted(left_gray, 0.5, left_grad, 0.5, 0)
            right_gray = cv2.addWeighted(right_gray, 0.5, right_grad, 0.5, 0)

            logger.debug("Pre-procesamiento: Escala de grises + realce de bordes")
        else:
            logger.debug("Pre-procesamiento: Solo conversión a escala de grises")

        return left_gray, right_gray
    
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
            
            R1, R2, P1, P2, Q, roi1, roi2 = cv2.stereoRectify(
                mtx_left, dist_left,
                mtx_right, dist_right,
                img_shape, R, T,
                flags=cv2.CALIB_ZERO_DISPARITY,
                alpha=0.0  
            )

            logger.info(f"🔍 DEBUG ROI válido izquierdo: {roi1}")
            logger.info(f"🔍 DEBUG ROI válido derecho: {roi2}")

            # NO usar máscara ROI restrictiva - las cámaras NO tienen fisheye
            # Solo crear una máscara básica para excluir bordes mínimos (1% máximo)
            height, width = img_shape[::-1]
            self.valid_roi_mask = np.ones((height, width), dtype=bool)

            # Excluir solo un margen MÍNIMO de bordes (1% en cada lado)
            # Esto es suficiente para eliminar artefactos de rectificación sin perder datos útiles
            margin_y = int(height * 0.01)  # REDUCIDO: 5% → 1%
            margin_x = int(width * 0.01)   # REDUCIDO: 5% → 1%

            # Mantener casi toda la imagen
            self.valid_roi_mask[:margin_y, :] = False  # Top
            self.valid_roi_mask[-margin_y:, :] = False  # Bottom
            self.valid_roi_mask[:, :margin_x] = False  # Left
            self.valid_roi_mask[:, -margin_x:] = False  # Right

            logger.info(f"🔍 DEBUG Máscara ROI creada - Píxeles válidos: {np.sum(self.valid_roi_mask)}/{self.valid_roi_mask.size} ({100*np.sum(self.valid_roi_mask)/self.valid_roi_mask.size:.1f}%)")

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
                         algorithm: str = "SGBM", use_wls_filter: bool = True,
                         use_object_mask: bool = False, use_edge_enhancement: bool = False,
                         save_debug: bool = False) -> Dict[str, Any]:
        """
        Calcular mapa de disparidad

        Args:
            use_object_mask: Si True, detecta objetos brillantes y descarta fondo oscuro
            use_edge_enhancement: Si True, realza bordes para objetos finos
            save_debug: Guardar imágenes intermedias de debug
        """

        with PerformanceLogger(f"Cálculo de disparidad ({algorithm})", logger):

            # Detectar máscara de objeto si se solicita
            object_mask = None
            if use_object_mask:
                logger.info("🔍 Detectando objeto de interés en imágenes...")
                left_mask = self.detect_foreground_object_mask(left_img, debug_name="left" if save_debug else "")
                right_mask = self.detect_foreground_object_mask(right_img, debug_name="right" if save_debug else "")

                # Combinar máscaras (intersección para ser conservador)
                object_mask = (left_mask & right_mask).astype(bool)
                logger.info(f"🔍 Máscara combinada: {np.sum(object_mask)} píxeles ({100*np.sum(object_mask)/object_mask.size:.2f}%)")

            # Preprocesar imágenes
            left_processed, right_processed = self.preprocess_images(left_img, right_img,
                                                                     use_edge_enhancement=use_edge_enhancement)

            # Seleccionar algoritmo
            if algorithm.upper() == "SGBM":
                matcher = self.sgbm
                right_matcher = self.right_matcher
                wls_filter = self.wls_filter
            elif algorithm.upper() == "SGBM_FINE":
                # Algoritmo especializado para objetos finos
                matcher = self.sgbm_fine
                right_matcher = self.right_matcher_fine
                wls_filter = self.wls_filter_fine
                logger.info("🔍 Usando SGBM_FINE (optimizado para cables/objetos delgados)")
            elif algorithm.upper() == "BM":
                matcher = self.bm
                right_matcher = None
                wls_filter = None
            else:
                raise ValueError(f"Algoritmo desconocido: {algorithm}")
            
            # Calcular disparidad
            logger.info(f"Calculando disparidad con algoritmo {algorithm}")
            disparity_left = matcher.compute(left_processed, right_processed).astype(np.float32) / 16.0

            # CRÍTICO: Limpiar valores inválidos (negativos e infinitos)
            disparity_left = np.clip(disparity_left, 0, 1000)
            disparity_left[~np.isfinite(disparity_left)] = 0

            # Aplicar máscara de objeto si existe (DESCARTAR FONDO COMPLETAMENTE)
            if object_mask is not None:
                logger.info("🔍 Aplicando máscara de objeto - Descartando fondo...")
                disparity_left[~object_mask] = 0
                logger.info(f"   Píxeles descartados (fondo): {np.sum(~object_mask)}")

            # Calcular estadísticas solo sobre píxeles válidos (umbral mínimo reducido)
            valid_mask = disparity_left > 0.5  # REDUCIDO: 0→0.5 (mantiene más puntos válidos)
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
            if use_wls_filter and algorithm.upper() in ["SGBM", "SGBM_FINE"]:
                logger.info("Aplicando filtro WLS para suavizado")

                # Calcular disparidad derecha para verificación cruzada
                disparity_right = right_matcher.compute(right_processed, left_processed).astype(np.float32) / 16.0

                # Aplicar filtro (usar el filtro apropiado según el algoritmo)
                disparity_filtered = wls_filter.filter(
                    disparity_left, left_processed, None, disparity_right
                )

                # CRÍTICO: Limpiar valores inválidos del filtrado
                disparity_filtered = np.clip(disparity_filtered, 0, 1000)
                disparity_filtered[~np.isfinite(disparity_filtered)] = 0

                # Aplicar máscara de objeto también a disparidad filtrada
                if object_mask is not None:
                    logger.info("🔍 Aplicando máscara de objeto a disparidad filtrada...")
                    disparity_filtered[~object_mask] = 0

                # === POST-PROCESAMIENTO: Suavizado ligero ===
                # CAMBIADO: Reducir parámetros de bilateral para preservar más detalle
                # El filtro WLS ya suavizó bastante, evitar eliminar señal válida
                logger.info("🔍 DEBUG Aplicando suavizado bilateral suave para reducir ruido...")
                disparity_smooth = cv2.bilateralFilter(
                    disparity_filtered.astype(np.float32),
                    d=5,           # REDUCIDO: 9→5 (vecindario más pequeño, preserva más detalle)
                    sigmaColor=50, # REDUCIDO: 75→50 (menos suavizado en valores similares)
                    sigmaSpace=50  # REDUCIDO: 75→50 (menos suavizado espacial)
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

    def compute_disparity_wire_guided(self,
                                     left_img: np.ndarray,
                                     right_img: np.ndarray,
                                     wire_mask: np.ndarray,
                                     patch_size: int = 9,
                                     sample_step: int = 3,
                                     ncc_threshold: float = 0.65,
                                     max_disparity: int = 256,
                                     save_debug: bool = False) -> Dict[str, Any]:
        """
        Calcular disparidad usando matching guiado para cables/objetos finos

        Este método es especializado para objetos uniformes sin textura interna
        (cables, hilos, alambres) donde SGBM falla por falta de features.

        Args:
            left_img: Imagen izquierda rectificada
            right_img: Imagen derecha rectificada
            wire_mask: Máscara binaria del cable (255=cable, 0=fondo)
            patch_size: Tamaño del patch para correlación (debe ser impar)
            sample_step: Muestreo del esqueleto (cada N píxeles)
            ncc_threshold: Umbral de correlación NCC (0-1)
            save_debug: Guardar imágenes de debug

        Returns:
            disparity_result: Dict con disparidad sparse y estadísticas
        """

        with PerformanceLogger("Matching guiado para cable", logger):

            logger.info("🎯 Iniciando matching guiado para cable...")

            # Inicializar WireMatcher si no existe
            if self.wire_matcher is None:
                self.wire_matcher = WireMatcher(
                    patch_size=patch_size,
                    max_disparity=max_disparity,
                    sample_step=sample_step,
                    ncc_threshold=ncc_threshold,
                    cross_check=False  # Deshabilitado por ahora para velocidad
                )
            else:
                # Actualizar parámetros si cambiaron
                self.wire_matcher.patch_size = patch_size
                self.wire_matcher.max_disparity = max_disparity
                self.wire_matcher.sample_step = sample_step
                self.wire_matcher.ncc_threshold = ncc_threshold
                self.wire_matcher.half_patch = patch_size // 2

            # Convertir imágenes a escala de grises
            left_gray, right_gray = self.preprocess_images(left_img, right_img,
                                                           use_edge_enhancement=False)

            # 1. Extraer puntos de bordes del cable (SIN thinning para preservar bordes)
            logger.info("📍 Extrayendo puntos de bordes del cable...")
            skeleton_points = self.wire_matcher.extract_skeleton(wire_mask, sample_step, use_thinning=False)

            if len(skeleton_points) == 0:
                logger.error("❌ No se pudo extraer esqueleto del cable!")
                return {
                    'success': False,
                    'algorithm': 'WIRE_GUIDED',
                    'error': 'No skeleton points extracted'
                }

            # 2. Calcular disparidad sparse
            logger.info("🔍 Buscando correspondencias...")
            matching_result = self.wire_matcher.compute_disparity_sparse(
                left_gray, right_gray, skeleton_points, save_debug=save_debug
            )

            if not matching_result['success']:
                logger.error("❌ Matching guiado falló!")
                return matching_result

            # 3. Crear mapa de disparidad sparse
            height, width = left_gray.shape
            disparity_map_sparse = np.zeros((height, width), dtype=np.float32)

            matches = matching_result['matches']
            disparities = matching_result['disparities']

            # Llenar mapa de disparidad con matches válidos
            for (x_left, y_left, _), disp in zip(matches, disparities):
                disparity_map_sparse[int(y_left), int(x_left)] = disp

            # 4. Estadísticas
            valid_pixels = np.sum(disparity_map_sparse > 0)

            disparity_result = {
                'success': True,
                'algorithm': 'WIRE_GUIDED',
                'disparity_map': disparity_map_sparse,
                'shape': disparity_map_sparse.shape,
                'min_disparity': matching_result['min_disparity'],
                'max_disparity': matching_result['max_disparity'],
                'mean_disparity': matching_result['mean_disparity'],
                'median_disparity': matching_result['median_disparity'],
                'std_disparity': matching_result['std_disparity'],
                'valid_pixels': valid_pixels,
                'num_matches': matching_result['num_matches'],
                'match_ratio': matching_result['match_ratio'],
                'mean_ncc_score': matching_result['mean_score'],
                'matches': matches,
                'disparities': disparities,
                'scores': matching_result['scores'],
                'filtered': False  # Es sparse, no necesita filtros adicionales
            }

            # 5. Crear mapa de confianza basado en scores NCC
            confidence_map = np.zeros((height, width), dtype=np.float32)
            scores = matching_result['scores']

            for (x_left, y_left, _), score in zip(matches, scores):
                confidence_map[int(y_left), int(x_left)] = score

            disparity_result['confidence_map'] = confidence_map

            logger.info(f"✓ Matching guiado completado:")
            logger.info(f"  - Matches válidos: {valid_pixels}")
            logger.info(f"  - Disparidad media: {disparity_result['mean_disparity']:.1f}px")
            logger.info(f"  - Score NCC medio: {disparity_result['mean_ncc_score']:.3f}")

            return disparity_result

    def process_wire_masks(self,
                          mask_left: np.ndarray,
                          mask_right: np.ndarray,
                          save_debug: bool = False) -> Dict[str, Any]:
        """
        Procesa máscaras de cables usando SmartWireTracker para generar paths precisos.
        Detecta automáticamente endpoints y ejecuta tracking en ambas máscaras.

        Args:
            mask_left: Máscara binaria del cable izquierdo (255=cable, 0=fondo)
            mask_right: Máscara binaria del cable derecho (255=cable, 0=fondo)
            save_debug: Guardar imágenes de debug

        Returns:
            Dict con paths, endpoints, máscaras procesadas y cobertura
        """
        from processing.endpoint_detector import detect_wire_endpoints
        from processing.smart_wire_tracker import SmartWireTracker

        logger.info("🎯 Procesando máscaras de cables con SmartWireTracker...")

        # Crear directorio de debug si no existe
        if save_debug:
            debug_dir = Path("data/results/debug")
            debug_dir.mkdir(parents=True, exist_ok=True)

        result = {
            'success': False,
            'left': {},
            'right': {},
            'debug_images': {}
        }

        try:
            # === PASO 1: Detectar endpoints en máscara izquierda ===
            logger.info("  Detectando endpoints en máscara izquierda...")
            start_left, end_left = detect_wire_endpoints(
                mask_left,
                method="skeleton",
                visualize=save_debug,
                vis_output_path="data/results/debug/endpoints_left.png" if save_debug else None
            )
            logger.info(f"    Start LEFT: {start_left}, End LEFT: {end_left}")

            # === PASO 2: Tracking en máscara izquierda ===
            logger.info("  Ejecutando wire tracking en máscara izquierda...")
            tracker_left = SmartWireTracker(mask_left, start_left, end_left)
            track_result_left = tracker_left.track_wire(max_iterations=10000)

            if save_debug:
                tracker_left.visualize('data/results/debug/wire_path_left.png')

            result['left'] = {
                'start': start_left,
                'end': end_left,
                'path': track_result_left['path'],
                'coverage': track_result_left['coverage'],
                'success': track_result_left['success']
            }

            logger.info(f"    ✓ Path LEFT: {len(track_result_left['path'])} puntos, "
                       f"Cobertura: {track_result_left['coverage']*100:.1f}%")

            # === PASO 3: Detectar endpoints en máscara derecha ===
            logger.info("  Detectando endpoints en máscara derecha...")
            start_right, end_right = detect_wire_endpoints(
                mask_right,
                method="skeleton",
                visualize=save_debug,
                vis_output_path="data/results/debug/endpoints_right.png" if save_debug else None
            )
            logger.info(f"    Start RIGHT: {start_right}, End RIGHT: {end_right}")

            # === PASO 4: Tracking en máscara derecha ===
            logger.info("  Ejecutando wire tracking en máscara derecha...")
            tracker_right = SmartWireTracker(mask_right, start_right, end_right)
            track_result_right = tracker_right.track_wire(max_iterations=10000)

            if save_debug:
                tracker_right.visualize('data/results/debug/wire_path_right.png')

            result['right'] = {
                'start': start_right,
                'end': end_right,
                'path': track_result_right['path'],
                'coverage': track_result_right['coverage'],
                'success': track_result_right['success']
            }

            logger.info(f"    ✓ Path RIGHT: {len(track_result_right['path'])} puntos, "
                       f"Cobertura: {track_result_right['coverage']*100:.1f}%")

            # === PASO 5: Validación de resultados ===
            if track_result_left['success'] and track_result_right['success']:
                result['success'] = True
                logger.info("✓ Wire tracking completado exitosamente en ambas máscaras")
            else:
                logger.warning("⚠️ Wire tracking falló en una o ambas máscaras")
                if not track_result_left['success']:
                    logger.warning("  - Fallo en máscara izquierda")
                if not track_result_right['success']:
                    logger.warning("  - Fallo en máscara derecha")

        except Exception as e:
            logger.error(f"❌ Error en process_wire_masks: {e}")
            import traceback
            logger.error(traceback.format_exc())
            result['error'] = str(e)

        return result

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

        # Penalización moderada
        confidence *= (1.0 - grad_normalized * 0.9)

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
            min_depth = 0.2   # 20cm mínimo
            max_depth = 5.0   # 3m máximo

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
                           min_confidence: float = 0.5, filter_background_color: bool = True) -> Dict[str, Any]:
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

            # Máscara de píxeles válidos - umbral básico
            valid_mask = disparity > 1.0
            logger.info(f"🔍 DEBUG Píxeles con disparidad > 1.0: {np.sum(valid_mask)}")

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

            logger.info(f"🔍 DEBUG Transformando a 3D con matriz Q...")
            # OPTIMIZACIÓN DE MEMORIA: Procesar en lotes para evitar crear arrays gigantes
            # En lugar de multiplicar Q por todos los puntos a la vez, procesamos por bloques
            batch_size = 100000  # 100k puntos por batch (~15MB por batch vs GB completos)
            num_batches = (num_valid + batch_size - 1) // batch_size

            logger.info(f"🔍 DEBUG Procesando {num_valid} puntos en {num_batches} lotes de {batch_size}")

            # Pre-allocate output array
            points_3d = np.empty((num_valid, 3), dtype=np.float32)

            for batch_idx in range(num_batches):
                start_idx = batch_idx * batch_size
                end_idx = min(start_idx + batch_size, num_valid)

                # Procesar este lote
                batch_x = x_indices[start_idx:end_idx]
                batch_y = y_indices[start_idx:end_idx]
                batch_disp = valid_disp[start_idx:end_idx]
                batch_size_actual = end_idx - start_idx

                # Crear puntos homogéneos para este lote
                points_2d_batch = np.column_stack([
                    batch_x,
                    batch_y,
                    batch_disp,
                    np.ones(batch_size_actual, dtype=np.float32)
                ])

                # Transformar a 3D (Q @ points_2d_batch.T)
                points_3d_h_batch = Q @ points_2d_batch.T

                # Convertir de homogéneo a cartesiano
                points_3d_batch = points_3d_h_batch[:3] / points_3d_h_batch[3]

                # Guardar en array de salida
                points_3d[start_idx:end_idx] = points_3d_batch.T

                # Liberar memoria del lote
                del points_2d_batch, points_3d_h_batch, points_3d_batch

                if batch_idx % 10 == 0:
                    logger.info(f"   Lote {batch_idx+1}/{num_batches} completado")

            logger.info(f"🔍 DEBUG Transformación 3D completada para {num_valid} puntos")
            
            logger.info(f"🔍 DEBUG Filtrando puntos por profundidad y límites espaciales...")

            # DEBUG: Mostrar estadísticas de coordenadas 3D (muestreo para evitar consumo de memoria)
            sample_size = min(100000, len(points_3d))
            sample_indices = np.random.choice(len(points_3d), sample_size, replace=False)
            logger.info(f"🔍 DEBUG Estadísticas de points_3d (muestra de {sample_size} puntos):")
            logger.info(f"   X - Min: {np.min(points_3d[sample_indices, 0]):.2f}m, Max: {np.max(points_3d[sample_indices, 0]):.2f}m")
            logger.info(f"   Y - Min: {np.min(points_3d[sample_indices, 1]):.2f}m, Max: {np.max(points_3d[sample_indices, 1]):.2f}m")
            logger.info(f"   Z - Min: {np.min(points_3d[sample_indices, 2]):.2f}m, Max: {np.max(points_3d[sample_indices, 2]):.2f}m")
            del sample_indices

            # OPTIMIZACIÓN DE MEMORIA: Filtrar por lotes para evitar crear arrays gigantes
            logger.info(f"🔍 DEBUG Aplicando filtros por lotes...")
            filter_batch_size = 500000  # 500k puntos por batch
            num_filter_batches = (num_valid + filter_batch_size - 1) // filter_batch_size

            # Pre-allocate máscara de filtro combinado
            combined_filter = np.zeros(num_valid, dtype=bool)

            for batch_idx in range(num_filter_batches):
                start_idx = batch_idx * filter_batch_size
                end_idx = min(start_idx + filter_batch_size, num_valid)

                # Extraer lote
                batch_points = points_3d[start_idx:end_idx]
                batch_depth = valid_depth[start_idx:end_idx]

                # Aplicar filtros al lote (in-place donde sea posible)
                batch_filter = (
                    (batch_depth > 0.3) & (batch_depth < 5.0) &  # Profundidad válida
                    (np.abs(batch_points[:, 0]) < 50.0) &        # X razonable
                    (np.abs(batch_points[:, 1]) < 50.0) &        # Y razonable
                    (np.abs(batch_points[:, 2]) < 50.0)          # Z razonable
                )

                # Guardar resultado en máscara combinada
                combined_filter[start_idx:end_idx] = batch_filter

                # Liberar memoria del lote
                del batch_points, batch_depth, batch_filter

                if batch_idx % 5 == 0:
                    logger.info(f"   Filtrado lote {batch_idx+1}/{num_filter_batches}")

            num_after_filter = np.sum(combined_filter)
            logger.info(f"🔍 DEBUG Puntos después de filtros: {num_after_filter}/{num_valid} ({100*num_after_filter/num_valid:.1f}%)")

            # Aplicar filtro a puntos 3D
            logger.info(f"🔍 DEBUG Extrayendo puntos filtrados...")
            final_points = points_3d[combined_filter]

            # Liberar puntos 3D originales YA que no se necesitan más
            del points_3d

            # Extraer colores SOLO para puntos filtrados (ahorro de memoria)
            logger.info(f"🔍 DEBUG Extrayendo colores para {num_after_filter} puntos válidos...")
            # Obtener índices originales que pasaron el filtro
            valid_indices_original = np.where(valid_mask)[0]
            filtered_indices = valid_indices_original[combined_filter]

            # Convertir índices lineales a (y, x)
            img_height, img_width = left_img.shape[:2]
            filtered_y = filtered_indices // img_width
            filtered_x = filtered_indices % img_width

            # Extraer colores directamente de la imagen
            if len(left_img.shape) == 3:
                final_colors = left_img[filtered_y, filtered_x] / 255.0
            else:
                gray_colors = left_img[filtered_y, filtered_x] / 255.0
                final_colors = np.column_stack([gray_colors, gray_colors, gray_colors])

            # Extraer confianza si existe
            final_confidence = None
            if confidence_map is not None:
                final_confidence = confidence_map[filtered_y, filtered_x]

            # Liberar memoria
            del valid_mask, y_indices, x_indices, valid_depth, combined_filter
            del valid_indices_original, filtered_indices, filtered_y, filtered_x
            
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
                           save_debug_images: bool = False, cable_mask: np.ndarray = None) -> Dict[str, Any]:
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
            # Para objetos finos en fondo oscuro, usar configuración especializada
            disparity_result = self.compute_disparity(
                left_rect, right_rect,
                algorithm=algorithm,
                use_wls_filter=True,
                use_object_mask=False,  # Deshabilitado por defecto, se puede habilitar vía parámetro
                use_edge_enhancement=False,  # Deshabilitado por defecto
                save_debug=save_debug_images
            )

            # APLICAR MÁSCARA DE CABLE si está configurada
            if cable_mask is not None:
                logger.info("🎯 Aplicando máscara de cable al mapa de disparidad...")

                # Redimensionar máscara si es necesario (debería tener mismo tamaño que imagen rectificada)
                if cable_mask.shape[:2] != disparity_result['disparity_map'].shape[:2]:
                    cable_mask = cv2.resize(cable_mask,
                                          (disparity_result['disparity_map'].shape[1],
                                           disparity_result['disparity_map'].shape[0]),
                                          interpolation=cv2.INTER_NEAREST)

                # Descartar disparidad FUERA del cable (poner a 0)
                disparity_before = np.sum(disparity_result['disparity_map'] > 0)
                disparity_result['disparity_map'][cable_mask == 0] = 0

                # También aplicar a mapa de confianza si existe
                if 'confidence_map' in disparity_result and disparity_result['confidence_map'] is not None:
                    disparity_result['confidence_map'][cable_mask == 0] = 0

                disparity_after = np.sum(disparity_result['disparity_map'] > 0)
                logger.info(f"   Píxeles válidos ANTES de máscara: {disparity_before}")
                logger.info(f"   Píxeles válidos DESPUÉS de máscara: {disparity_after}")
                logger.info(f"   Píxeles descartados (fondo): {disparity_before - disparity_after}")

                # Guardar mapa con máscara aplicada
                if save_debug_images:
                    debug_path = Path("data/results/debug")
                    disp_masked = disparity_result['disparity_map'].copy()
                    disp_vis = cv2.normalize(disp_masked, None, 0, 255, cv2.NORM_MINMAX, dtype=cv2.CV_8U)
                    disp_color = cv2.applyColorMap(disp_vis, cv2.COLORMAP_JET)
                    disp_color[disp_masked <= 0] = [0, 0, 0]
                    cv2.imwrite(str(debug_path / "10_disparity_with_cable_mask.png"), disp_color)

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
                try:
                    import matplotlib
                    matplotlib.use('Agg')  # Backend sin GUI para evitar warning de threads
                    import matplotlib.pyplot as plt

                    plt.figure(figsize=(10, 6))
                    valid_disp = disp_map[disp_map > 0]
                    if len(valid_disp) > 0:
                        plt.hist(valid_disp, bins=100, color='blue', alpha=0.7)
                        plt.xlabel('Disparidad (píxeles)')
                        plt.ylabel('Frecuencia')
                        plt.title(f'Histograma de Disparidad\nMin: {np.min(valid_disp):.2f}, Max: {np.max(valid_disp):.2f}, Mean: {np.mean(valid_disp):.2f}')
                        plt.grid(True, alpha=0.3)
                        plt.savefig(str(debug_path / "14_disparity_histogram.png"))
                        plt.close()
                    else:
                        logger.warning("No hay disparidad válida para histograma")
                except Exception as e:
                    logger.warning(f"No se pudo generar histograma: {e}")

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