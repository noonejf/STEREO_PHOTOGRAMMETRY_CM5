#!/usr/bin/env python3
"""
Wire Matcher - Sistema de matching guiado para cables finos
Implementa correlación por línea epipolar para objetos uniformes sin textura interna
"""

import cv2
import numpy as np
from typing import Dict, Any, Tuple, List, Optional
from pathlib import Path

from utils.logger import get_logger, PerformanceLogger

logger = get_logger(__name__)


class WireMatcher:
    """
    Matching guiado especializado para cables/objetos finos uniformes

    En lugar de usar SGBM denso (que falla con objetos sin textura),
    este matcher:
    1. Extrae el esqueleto (centerline) del cable desde la máscara
    2. Para cada punto del esqueleto, busca correspondencia en la otra imagen
    3. Usa correlación cruzada normalizada (NCC) en línea epipolar
    4. Genera disparidad sparse solo para el cable
    """

    def __init__(self,
                 patch_size: int = 9,
                 max_disparity: int = 256,
                 sample_step: int = 3,
                 ncc_threshold: float = 0.65,
                 cross_check: bool = True):
        """
        Args:
            patch_size: Tamaño del patch para correlación (debe ser impar)
            max_disparity: Disparidad máxima a buscar (píxeles)
            sample_step: Muestreo del esqueleto (cada N píxeles)
            ncc_threshold: Umbral de correlación (0-1, mayor = más estricto)
            cross_check: Verificar matches left→right y right→left
        """

        if patch_size % 2 == 0:
            raise ValueError("patch_size debe ser impar")

        self.patch_size = patch_size
        self.max_disparity = max_disparity
        self.sample_step = sample_step
        self.ncc_threshold = ncc_threshold
        self.cross_check = cross_check
        self.half_patch = patch_size // 2

        logger.info(f"WireMatcher inicializado:")
        logger.info(f"  - Patch: {patch_size}x{patch_size}")
        logger.info(f"  - Max disparidad: {max_disparity}px")
        logger.info(f"  - Muestreo: cada {sample_step} píxeles")
        logger.info(f"  - NCC threshold: {ncc_threshold}")
        logger.info(f"  - Cross-check: {cross_check}")

    def extract_skeleton(self, mask: np.ndarray, sample_step: Optional[int] = None,
                        use_thinning: bool = True) -> np.ndarray:
        """
        Extraer puntos desde máscara binaria

        Args:
            mask: Máscara binaria (255=bordes/cable, 0=fondo)
            sample_step: Override de muestreo (None usa self.sample_step)
            use_thinning: Si True, aplica thinning. Si False, usa píxeles directos de la máscara

        Returns:
            points: Array Nx2 de (x, y) muestreado
        """

        with PerformanceLogger("Extracción de puntos de máscara", logger):

            # Asegurar formato correcto
            if mask.dtype != np.uint8:
                mask = (mask > 0).astype(np.uint8) * 255

            if use_thinning:
                # Aplicar thinning para obtener esqueleto de 1 píxel de ancho
                skeleton = cv2.ximgproc.thinning(mask, thinningType=cv2.ximgproc.THINNING_ZHANGSUEN)
                logger.info(f"  Thinning aplicado (esqueleto)")
            else:
                # Usar píxeles directamente de la máscara (BORDES DETECTADOS)
                skeleton = mask
                logger.info(f"  Usando píxeles de bordes directamente (sin thinning)")

            # Extraer coordenadas
            skeleton_points = np.column_stack(np.where(skeleton > 0))  # (y, x)
            skeleton_points = skeleton_points[:, [1, 0]]  # Convertir a (x, y)

            logger.info(f"  Puntos extraídos: {len(skeleton_points)} píxeles")

            # Muestrear puntos cada N píxeles para reducir densidad
            step = sample_step if sample_step is not None else self.sample_step

            if step > 1:
                sampled_points = skeleton_points[::step]
                logger.info(f"  Muestreado (cada {step}px): {len(sampled_points)} puntos")
            else:
                sampled_points = skeleton_points

            return sampled_points

    def normalize_cross_correlation(self, patch1: np.ndarray, patch2: np.ndarray) -> float:
        """
        Calcular correlación cruzada normalizada (NCC) entre dos patches

        NCC ∈ [-1, 1], donde:
          1.0 = match perfecto
          0.0 = no correlación
         -1.0 = anti-correlación

        Args:
            patch1, patch2: Patches del mismo tamaño

        Returns:
            ncc_score: Valor de correlación
        """

        # Normalizar patches (media=0, std=1)
        patch1_norm = (patch1 - np.mean(patch1)) / (np.std(patch1) + 1e-8)
        patch2_norm = (patch2 - np.mean(patch2)) / (np.std(patch2) + 1e-8)

        # Correlación cruzada normalizada
        ncc = np.mean(patch1_norm * patch2_norm)

        return float(np.clip(ncc, -1.0, 1.0))

    def find_correspondence_epipolar(self,
                                    left_img: np.ndarray,
                                    right_img: np.ndarray,
                                    x_left: int,
                                    y_left: int,
                                    search_range: Optional[Tuple[int, int]] = None,
                                    left_grad_x: Optional[np.ndarray] = None,
                                    left_grad_y: Optional[np.ndarray] = None,
                                    right_grad_x: Optional[np.ndarray] = None,
                                    right_grad_y: Optional[np.ndarray] = None) -> Tuple[Optional[int], float]:
        """
        Buscar correspondencia de un punto en imagen derecha sobre línea epipolar

        NUEVO: Usa gradientes en lugar de intensidad para objetos uniformes

        Args:
            left_img: Imagen izquierda (escala de grises)
            right_img: Imagen derecha (escala de grises)
            x_left, y_left: Coordenadas del punto en imagen izquierda
            search_range: (x_min, x_max) para búsqueda, None usa max_disparity
            left_grad_x, left_grad_y: Gradientes de imagen izquierda (opcional)
            right_grad_x, right_grad_y: Gradientes de imagen derecha (opcional)

        Returns:
            x_right: Coordenada x del match (None si no se encontró)
            score: Score NCC del mejor match
        """

        height, width = left_img.shape
        hp = self.half_patch

        # Verificar que el punto tiene suficiente margen para extraer patch
        if (y_left < hp or y_left >= height - hp or
            x_left < hp or x_left >= width - hp):
            return None, 0.0

        # NUEVO: Si se proporcionan gradientes, usar matching basado en gradientes
        use_gradient = (left_grad_x is not None and right_grad_x is not None)

        if use_gradient:
            # Extraer patches de gradientes
            patch_left_gx = left_grad_x[y_left - hp:y_left + hp + 1,
                                        x_left - hp:x_left + hp + 1]
            patch_left_gy = left_grad_y[y_left - hp:y_left + hp + 1,
                                        x_left - hp:x_left + hp + 1]

            # Calcular magnitud del gradiente
            patch_left_mag = np.sqrt(patch_left_gx**2 + patch_left_gy**2)

            # Si el gradiente es muy bajo, este no es un buen punto de borde
            if np.mean(patch_left_mag) < 10:
                return None, 0.0
        else:
            # Extraer patch de intensidad de imagen izquierda
            patch_left = left_img[y_left - hp:y_left + hp + 1,
                                  x_left - hp:x_left + hp + 1]

        # Determinar rango de búsqueda en imagen derecha
        if search_range is None:
            # Búsqueda estándar: desde x_left hasta x_left - max_disparity
            x_min = max(hp, x_left - self.max_disparity)
            x_max = x_left
        else:
            x_min, x_max = search_range
            x_min = max(hp, x_min)
            x_max = min(width - hp - 1, x_max)

        # Buscar mejor match por correlación
        best_x = None
        best_score = -1.0

        for x_right in range(x_min, x_max + 1):
            if use_gradient:
                # Extraer patches de gradientes en imagen derecha
                patch_right_gx = right_grad_x[y_left - hp:y_left + hp + 1,
                                             x_right - hp:x_right + hp + 1]
                patch_right_gy = right_grad_y[y_left - hp:y_left + hp + 1,
                                             x_right - hp:x_right + hp + 1]

                # Calcular magnitud
                patch_right_mag = np.sqrt(patch_right_gx**2 + patch_right_gy**2)

                # Correlacionar magnitudes de gradientes (más robusto que intensidad)
                score = self.normalize_cross_correlation(patch_left_mag, patch_right_mag)
            else:
                # Extraer patch candidato de intensidad
                patch_right = right_img[y_left - hp:y_left + hp + 1,
                                       x_right - hp:x_right + hp + 1]

                # Calcular correlación de intensidad
                score = self.normalize_cross_correlation(patch_left, patch_right)

            if score > best_score:
                best_score = score
                best_x = x_right

        # Validar threshold
        if best_score < self.ncc_threshold:
            return None, best_score

        return best_x, best_score

    def compute_disparity_sparse(self,
                                left_img: np.ndarray,
                                right_img: np.ndarray,
                                skeleton_points: np.ndarray,
                                save_debug: bool = False,
                                use_gradient_matching: bool = True) -> Dict[str, Any]:
        """
        Calcular disparidad sparse para puntos del esqueleto

        Args:
            left_img: Imagen izquierda rectificada (escala de grises)
            right_img: Imagen derecha rectificada (escala de grises)
            skeleton_points: Array Nx2 de (x, y) del esqueleto
            save_debug: Guardar imágenes de debug
            use_gradient_matching: Usar gradientes en vez de intensidad (mejor para objetos uniformes)

        Returns:
            result: Dict con disparidad sparse y estadísticas
        """

        with PerformanceLogger("Cálculo de disparidad sparse", logger):

            num_points = len(skeleton_points)
            logger.info(f"Procesando {num_points} puntos del esqueleto...")

            # DESACTIVADO: Matching basado en gradientes no funciona para patrones repetitivos
            # Volvemos a intensity-based matching
            left_grad_x, left_grad_y = None, None
            right_grad_x, right_grad_y = None, None

            # FORZAR intensity matching
            use_gradient_matching = False

            if use_gradient_matching:
                logger.info("🔍 Calculando gradientes para matching basado en bordes...")

                # Sobel en X e Y para ambas imágenes
                left_grad_x = cv2.Sobel(left_img, cv2.CV_32F, 1, 0, ksize=3)
                left_grad_y = cv2.Sobel(left_img, cv2.CV_32F, 0, 1, ksize=3)
                right_grad_x = cv2.Sobel(right_img, cv2.CV_32F, 1, 0, ksize=3)
                right_grad_y = cv2.Sobel(right_img, cv2.CV_32F, 0, 1, ksize=3)

                logger.info("✓ Gradientes calculados")
            else:
                logger.info("🔍 Usando matching basado en INTENSIDAD (no gradientes)")

            # Almacenar resultados
            valid_matches = []
            disparities = []
            scores = []

            # Procesar cada punto
            for idx, (x_left, y_left) in enumerate(skeleton_points):

                # Buscar correspondencia (con o sin gradientes)
                x_right, score = self.find_correspondence_epipolar(
                    left_img, right_img, x_left, y_left,
                    left_grad_x=left_grad_x, left_grad_y=left_grad_y,
                    right_grad_x=right_grad_x, right_grad_y=right_grad_y
                )

                if x_right is not None:
                    disparity = x_left - x_right

                    # Validar disparidad positiva
                    if disparity > 0:
                        valid_matches.append((x_left, y_left, x_right))
                        disparities.append(disparity)
                        scores.append(score)

                # Log progreso cada 10%
                if idx % max(1, num_points // 10) == 0:
                    progress = 100 * idx / num_points
                    logger.info(f"  Progreso: {progress:.0f}% ({idx}/{num_points})")

            num_valid = len(valid_matches)
            logger.info(f"✓ Matches válidos: {num_valid}/{num_points} ({100*num_valid/num_points:.1f}%)")

            # === FILTRO DE OUTLIERS AGRESIVO ===
            # Para cables uniformes planos: eliminar disparidades muy alejadas de la mediana
            if num_valid > 10:  # Solo si hay suficientes puntos
                logger.info("🔍 Aplicando filtro de outliers AGRESIVO para cable plano...")

                # Calcular estadísticas globales
                median_disp = np.median(disparities)
                mad = np.median(np.abs(np.array(disparities) - median_disp))  # Median Absolute Deviation

                # Umbral MUY ESTRICTO: 2 * MAD o 20px (lo que sea menor)
                # Cable de 1mm en superficie plana NO debería tener variación >20px
                threshold = min(2.0 * mad, 20.0)

                # Si MAD es muy grande, algo está mal - usar umbral fijo
                if mad > 30:
                    logger.warning(f"⚠️ MAD muy grande ({mad:.1f}px) - matches probablemente incorrectos")
                    threshold = 15.0  # Umbral fijo conservador

                logger.info(f"  Mediana global: {median_disp:.1f}px")
                logger.info(f"  MAD: {mad:.1f}px")
                logger.info(f"  Umbral de filtrado: ±{threshold:.1f}px (ESTRICTO)")

                # Filtrar puntos que están muy lejos de la mediana
                filtered_matches = []
                filtered_disparities = []
                filtered_scores = []

                for idx in range(num_valid):
                    disp = disparities[idx]

                    # Solo aceptar si está CERCA de la mediana
                    if abs(disp - median_disp) <= threshold:
                        filtered_matches.append(valid_matches[idx])
                        filtered_disparities.append(disp)
                        filtered_scores.append(scores[idx])

                num_filtered = len(filtered_matches)
                num_removed = num_valid - num_filtered

                logger.info(f"✓ Filtro global: {num_filtered}/{num_valid} puntos conservados")
                logger.info(f"  Outliers eliminados: {num_removed} ({100*num_removed/num_valid:.1f}%)")

                # Reemplazar con resultados filtrados
                if num_filtered > 50:  # Al menos 50 puntos para formar el cable
                    valid_matches = filtered_matches
                    disparities = filtered_disparities
                    scores = filtered_scores
                    num_valid = num_filtered

                    # Recalcular MAD después del filtro
                    new_mad = np.median(np.abs(np.array(disparities) - np.median(disparities)))
                    logger.info(f"  MAD después de filtro: {new_mad:.1f}px")
                else:
                    logger.warning(f"⚠️ Filtro demasiado agresivo (solo {num_filtered} puntos), manteniendo originales")

            if num_valid == 0:
                logger.error("❌ No se encontraron matches válidos!")
                return {
                    'success': False,
                    'num_matches': 0,
                    'matches': np.array([]),
                    'disparities': np.array([]),
                    'scores': np.array([])
                }

            # Convertir a arrays numpy
            matches_array = np.array(valid_matches)  # Nx3: (x_left, y_left, x_right)
            disparities_array = np.array(disparities)
            scores_array = np.array(scores)

            # Estadísticas
            stats = {
                'success': True,
                'num_points_input': num_points,
                'num_matches': num_valid,
                'match_ratio': num_valid / num_points,
                'min_disparity': float(np.min(disparities_array)),
                'max_disparity': float(np.max(disparities_array)),
                'mean_disparity': float(np.mean(disparities_array)),
                'median_disparity': float(np.median(disparities_array)),
                'std_disparity': float(np.std(disparities_array)),
                'mean_score': float(np.mean(scores_array)),
                'min_score': float(np.min(scores_array)),
                'matches': matches_array,
                'disparities': disparities_array,
                'scores': scores_array
            }

            logger.info(f"📊 Estadísticas de disparidad:")
            logger.info(f"  - Rango: {stats['min_disparity']:.1f} - {stats['max_disparity']:.1f} px")
            logger.info(f"  - Media: {stats['mean_disparity']:.1f} px")
            logger.info(f"  - Std: {stats['std_disparity']:.1f} px")
            logger.info(f"  - Score NCC medio: {stats['mean_score']:.3f}")

            # Guardar debug si se solicita
            if save_debug:
                self._save_debug_visualizations(left_img, right_img, stats)

            return stats

    def _save_debug_visualizations(self, left_img: np.ndarray, right_img: np.ndarray,
                                   stats: Dict[str, Any]):
        """Guardar visualizaciones de debug del matching"""

        debug_path = Path("data/results/debug/wire_matcher")
        debug_path.mkdir(parents=True, exist_ok=True)

        matches = stats['matches']
        disparities = stats['disparities']
        scores = stats['scores']

        # 1. Visualización de correspondencias
        h, w = left_img.shape
        combined = np.zeros((h, w*2, 3), dtype=np.uint8)
        combined[:, :w] = cv2.cvtColor(left_img, cv2.COLOR_GRAY2BGR)
        combined[:, w:] = cv2.cvtColor(right_img, cv2.COLOR_GRAY2BGR)

        # Colormap para disparidades (normalizar)
        disp_norm = (disparities - np.min(disparities)) / (np.max(disparities) - np.min(disparities) + 1e-8)

        for idx, (x_left, y_left, x_right) in enumerate(matches):
            # Color basado en disparidad (rojo=cerca, azul=lejos)
            color_val = int(disp_norm[idx] * 255)
            color = cv2.applyColorMap(np.array([[color_val]], dtype=np.uint8), cv2.COLORMAP_JET)[0, 0]
            color = tuple(map(int, color))

            # Dibujar puntos
            cv2.circle(combined, (int(x_left), int(y_left)), 3, color, -1)
            cv2.circle(combined, (int(x_right) + w, int(y_left)), 3, color, -1)

            # Línea conectando matches
            cv2.line(combined, (int(x_left), int(y_left)),
                    (int(x_right) + w, int(y_left)), color, 1)

        cv2.imwrite(str(debug_path / "01_correspondences.jpg"), combined)

        # 2. Mapa de disparidad sparse visualizado
        disp_map_vis = np.zeros((h, w, 3), dtype=np.uint8)

        for idx, (x_left, y_left, _) in enumerate(matches):
            color_val = int(disp_norm[idx] * 255)
            color = cv2.applyColorMap(np.array([[color_val]], dtype=np.uint8), cv2.COLORMAP_JET)[0, 0]
            cv2.circle(disp_map_vis, (int(x_left), int(y_left)), 2, tuple(map(int, color)), -1)

        cv2.imwrite(str(debug_path / "02_disparity_sparse.png"), disp_map_vis)

        # 3. Histograma de disparidades
        try:
            import matplotlib
            matplotlib.use('Agg')
            import matplotlib.pyplot as plt

            fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 4))

            # Histograma de disparidad
            ax1.hist(disparities, bins=50, color='blue', alpha=0.7)
            ax1.set_xlabel('Disparidad (píxeles)')
            ax1.set_ylabel('Frecuencia')
            ax1.set_title(f'Histograma de Disparidad\nMedia: {stats["mean_disparity"]:.1f}px, Std: {stats["std_disparity"]:.1f}px')
            ax1.grid(True, alpha=0.3)

            # Histograma de scores NCC
            ax2.hist(scores, bins=50, color='green', alpha=0.7)
            ax2.set_xlabel('Score NCC')
            ax2.set_ylabel('Frecuencia')
            ax2.set_title(f'Histograma de Scores\nMedia: {stats["mean_score"]:.3f}')
            ax2.grid(True, alpha=0.3)

            plt.tight_layout()
            plt.savefig(str(debug_path / "03_histograms.png"))
            plt.close()

        except Exception as e:
            logger.warning(f"No se pudo generar histogramas: {e}")

        logger.info(f"🔍 DEBUG visualizaciones guardadas en {debug_path}")

    def triangulate_3d_points(self,
                             matches: np.ndarray,
                             disparities: np.ndarray,
                             Q: np.ndarray) -> Dict[str, Any]:
        """
        Triangular puntos 3D desde matches y disparidades

        Args:
            matches: Array Nx3 (x_left, y_left, x_right)
            disparities: Array N de disparidades
            Q: Matriz 4x4 de proyección (disparity-to-depth)

        Returns:
            result: Dict con puntos 3D y estadísticas
        """

        with PerformanceLogger("Triangulación 3D", logger):

            num_points = len(matches)
            logger.info(f"Triangulando {num_points} puntos...")

            # Extraer coordenadas
            x_coords = matches[:, 0]
            y_coords = matches[:, 1]

            # Crear puntos homogéneos [x, y, disparity, 1]
            points_2d = np.column_stack([
                x_coords,
                y_coords,
                disparities,
                np.ones(num_points)
            ])

            # Transformar a 3D: Q @ points_2d.T
            points_3d_h = Q @ points_2d.T  # 4xN

            # Convertir de homogéneo a cartesiano
            points_3d = points_3d_h[:3] / points_3d_h[3]  # 3xN
            points_3d = points_3d.T  # Nx3

            # Filtrar outliers (puntos fuera de rango físico razonable)
            depth_mask = (points_3d[:, 2] > 0.2) & (points_3d[:, 2] < 5.0)
            spatial_mask = (np.abs(points_3d[:, 0]) < 10.0) & (np.abs(points_3d[:, 1]) < 10.0)

            valid_mask = depth_mask & spatial_mask

            points_3d_filtered = points_3d[valid_mask]

            logger.info(f"✓ Puntos 3D válidos: {len(points_3d_filtered)}/{num_points}")

            if len(points_3d_filtered) == 0:
                logger.error("❌ No hay puntos 3D válidos después de filtrado!")
                return {
                    'success': False,
                    'num_points': 0,
                    'points': np.array([]),
                    'bounds': {}
                }

            result = {
                'success': True,
                'num_points': len(points_3d_filtered),
                'points': points_3d_filtered,
                'bounds': {
                    'x_min': float(np.min(points_3d_filtered[:, 0])),
                    'x_max': float(np.max(points_3d_filtered[:, 0])),
                    'y_min': float(np.min(points_3d_filtered[:, 1])),
                    'y_max': float(np.max(points_3d_filtered[:, 1])),
                    'z_min': float(np.min(points_3d_filtered[:, 2])),
                    'z_max': float(np.max(points_3d_filtered[:, 2])),
                }
            }

            logger.info(f"📊 Bounds 3D:")
            logger.info(f"  X: [{result['bounds']['x_min']:.3f}, {result['bounds']['x_max']:.3f}] m")
            logger.info(f"  Y: [{result['bounds']['y_min']:.3f}, {result['bounds']['y_max']:.3f}] m")
            logger.info(f"  Z: [{result['bounds']['z_min']:.3f}, {result['bounds']['z_max']:.3f}] m")

            return result


if __name__ == "__main__":
    # Test básico del WireMatcher
    print("="*80)
    print("WIRE MATCHER - TEST")
    print("="*80)

    # Test de extracción de esqueleto
    test_mask = np.zeros((100, 100), dtype=np.uint8)
    cv2.line(test_mask, (10, 10), (90, 90), 255, 3)  # Línea diagonal

    matcher = WireMatcher(patch_size=9, sample_step=5)
    skeleton = matcher.extract_skeleton(test_mask)

    print(f"\n✓ Esqueleto extraído: {len(skeleton)} puntos")
    print(f"  Primeros 5 puntos: {skeleton[:5]}")

    # Test de NCC
    patch1 = np.random.randint(0, 255, (9, 9), dtype=np.uint8)
    patch2 = patch1.copy()  # Match perfecto
    patch3 = np.random.randint(0, 255, (9, 9), dtype=np.uint8)  # Aleatorio

    ncc_perfect = matcher.normalize_cross_correlation(patch1, patch2)
    ncc_random = matcher.normalize_cross_correlation(patch1, patch3)

    print(f"\n✓ NCC test:")
    print(f"  Match perfecto: {ncc_perfect:.3f} (esperado ~1.0)")
    print(f"  Match aleatorio: {ncc_random:.3f} (esperado ~0.0)")

    print("\n✅ Tests completados")
