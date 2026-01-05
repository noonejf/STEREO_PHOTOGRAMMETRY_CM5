#!/usr/bin/env python3
"""
Geometric Wire Matcher - Matching de cables basado en geometría de curvas
"""

import cv2
import numpy as np
from typing import Dict, Any, Tuple
from pathlib import Path

from processing.curve_tracker import CurveTracker
from utils.logger import get_logger

logger = get_logger(__name__)


class GeometricWireMatcher:
    """
    Matching de cables unifor mes basado en geometría y flujo de curvas

    En lugar de matching visual (que falla con cables uniformes),
    extrae el esqueleto geométrico del cable en ambas imágenes y
    hace matching basado en correspondencia de curvas ordenadas
    """

    def __init__(self):
        self.tracker = CurveTracker()

    def match_wire_curves(self,
                         left_img: np.ndarray,
                         right_img: np.ndarray,
                         left_mask: np.ndarray,
                         right_mask: np.ndarray,
                         sample_spacing: int = 3,
                         save_debug: bool = False) -> Dict[str, Any]:
        """
        Hacer matching de cables basado en geometría de curvas

        Args:
            left_img: Imagen izquierda rectificada
            right_img: Imagen derecha rectificada
            left_mask: Máscara binaria del cable en imagen izquierda
            right_mask: Máscara binaria del cable en imagen derecha
            sample_spacing: Espaciado entre puntos en curva
            save_debug: Guardar visualizaciones

        Returns:
            result: Dict con disparidad y estadísticas
        """

        logger.info("🎯 Iniciando matching geométrico de cables...")

        # PASO 1: Extraer curvas ordenadas de ambas imágenes
        logger.info("\n[1/4] Extrayendo curva de imagen IZQUIERDA...")
        left_result = self.tracker.extract_and_order_skeleton(left_mask, sample_spacing)

        if not left_result['success']:
            return {'success': False, 'error': f"Error en curva left: {left_result['error']}"}

        left_curve = left_result['ordered_points']
        logger.info(f"✓ Curva izquierda: {len(left_curve)} puntos")

        logger.info("\n[2/4] Extrayendo curva de imagen DERECHA...")
        right_result = self.tracker.extract_and_order_skeleton(right_mask, sample_spacing)

        if not right_result['success']:
            return {'success': False, 'error': f"Error en curva right: {right_result['error']}"}

        right_curve = right_result['ordered_points']
        logger.info(f"✓ Curva derecha: {len(right_curve)} puntos")

        # PASO 2: Hacer matching geométrico entre curvas
        logger.info("\n[3/4] Haciendo matching geométrico...")
        matches, disparities = self._match_curves(left_curve, right_curve, left_img, right_img)

        logger.info(f"✓ Matches geométricos: {len(matches)}")

        if len(matches) == 0:
            return {'success': False, 'error': 'No geometric matches found'}

        # PASO 3: Crear mapa de disparidad sparse
        height, width = left_img.shape[:2]
        disparity_map = np.zeros((height, width), dtype=np.float32)
        confidence_map = np.ones((height, width), dtype=np.float32)

        for idx, (x_left, y_left, x_right, disp) in enumerate(matches):
            disparity_map[y_left, x_left] = disp
            # Confianza alta para matches geométricos
            confidence_map[y_left, x_left] = 0.95

        # Estadísticas
        valid_disparities = disparities[disparities > 0]

        if len(valid_disparities) == 0:
            return {'success': False, 'error': 'No valid disparities'}

        result = {
            'success': True,
            'disparity_map': disparity_map,
            'confidence_map': confidence_map,
            'num_matches': len(matches),
            'min_disparity': float(np.min(valid_disparities)),
            'max_disparity': float(np.max(valid_disparities)),
            'mean_disparity': float(np.mean(valid_disparities)),
            'std_disparity': float(np.std(valid_disparities)),
            'median_disparity': float(np.median(valid_disparities)),
            'left_curve': left_curve,
            'right_curve': right_curve,
            'matches': matches,
            'disparities': disparities
        }

        logger.info(f"\n📊 Resultados del matching geométrico:")
        logger.info(f"  - Matches: {result['num_matches']}")
        logger.info(f"  - Disparidad: {result['min_disparity']:.1f} - {result['max_disparity']:.1f} px")
        logger.info(f"  - Media: {result['mean_disparity']:.1f} ± {result['std_disparity']:.1f} px")

        # PASO 4: Guardar debug si se solicita
        if save_debug:
            self._save_debug(left_img, right_img, left_curve, right_curve,
                           matches, disparities, result)

        return result

    def _match_curves(self,
                     left_curve: np.ndarray,
                     right_curve: np.ndarray,
                     left_img: np.ndarray,
                     right_img: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
        """
        Matching geométrico entre dos curvas ordenadas

        Estrategia MEJORADA para espirales:
        - Para cada punto LEFT, buscar punto RIGHT en misma fila Y (±tolerancia)
        - Entre múltiples candidatos, elegir el que tenga disparidad más cercana a la mediana
        - Esto evita saltos entre loops de la espiral
        """

        matches = []
        disparities = []

        n_left = len(left_curve)
        n_right = len(right_curve)

        logger.info(f"  Matching sincronizado: {n_left} pts (left) vs {n_right} pts (right)")

        # Crear índice espacial para right_curve por fila Y
        right_by_y = {}
        for idx, (x, y) in enumerate(right_curve):
            y_int = int(y)
            if y_int not in right_by_y:
                right_by_y[y_int] = []
            right_by_y[y_int].append((int(x), y_int, idx))

        # Primer paso: Recoger matches preliminares
        preliminary_matches = []

        for i_left, (x_left, y_left) in enumerate(left_curve):
            x_left, y_left = int(x_left), int(y_left)

            # Buscar candidatos en curva derecha en la misma fila Y (±5 px)
            candidates = []
            for dy in range(-5, 6):
                y_search = y_left + dy
                if y_search in right_by_y:
                    candidates.extend(right_by_y[y_search])

            if len(candidates) == 0:
                continue

            # Filtrar candidatos con disparidad positiva
            valid_candidates = [(x_r, y_r, idx_r) for x_r, y_r, idx_r in candidates if x_r < x_left]

            if len(valid_candidates) == 0:
                continue

            # Si hay un solo candidato, tomarlo
            if len(valid_candidates) == 1:
                x_right, y_right, idx_right = valid_candidates[0]
                disparity = x_left - x_right
                preliminary_matches.append((x_left, y_left, x_right, disparity, i_left, idx_right))
            else:
                # Múltiples candidatos: guardar todos para análisis posterior
                for x_right, y_right, idx_right in valid_candidates:
                    disparity = x_left - x_right
                    preliminary_matches.append((x_left, y_left, x_right, disparity, i_left, idx_right))

        logger.info(f"  Matches preliminares: {len(preliminary_matches)}")

        if len(preliminary_matches) == 0:
            logger.warning("  No se encontraron matches preliminares!")
            return np.array(matches), np.array(disparities)

        # Calcular disparidad mediana para filtrar outliers
        prelim_disparities = [m[3] for m in preliminary_matches]
        median_disparity = np.median(prelim_disparities)
        std_disparity = np.std(prelim_disparities)

        logger.info(f"  Disparidad mediana: {median_disparity:.1f} ± {std_disparity:.1f} px")

        # Segundo paso: Filtrar matches usando disparidad consistente
        # Para cada punto LEFT, elegir el candidato RIGHT con disparidad más cercana a la mediana
        matches_by_left = {}
        for x_left, y_left, x_right, disparity, i_left, idx_right in preliminary_matches:
            # Filtrar disparidades muy alejadas de la mediana (±3 std)
            if abs(disparity - median_disparity) > 3 * max(std_disparity, 10):
                continue

            # Si este punto LEFT ya tiene un match, elegir el mejor
            if i_left in matches_by_left:
                prev_disparity = matches_by_left[i_left][3]
                # Elegir el candidato con disparidad más cercana a la mediana
                if abs(disparity - median_disparity) < abs(prev_disparity - median_disparity):
                    matches_by_left[i_left] = (x_left, y_left, x_right, disparity)
            else:
                matches_by_left[i_left] = (x_left, y_left, x_right, disparity)

        # Convertir a listas finales
        for x_left, y_left, x_right, disparity in matches_by_left.values():
            matches.append((x_left, y_left, x_right, disparity))
            disparities.append(disparity)

        logger.info(f"  Matches finales después de filtrado: {len(matches)}")

        return np.array(matches), np.array(disparities)

    def _save_debug(self, left_img, right_img, left_curve, right_curve,
                   matches, disparities, result):
        """Guardar visualizaciones de debug"""

        debug_path = Path("data/results/debug/geometric_matcher")
        debug_path.mkdir(parents=True, exist_ok=True)

        # 1. Curvas con gradiente de color mostrando flujo
        logger.info("\n[4/4] Guardando visualizaciones...")

        self.tracker.visualize_curve(left_img, left_curve,
                                    debug_path / "01_left_curve_flow.jpg")

        self.tracker.visualize_curve(right_img, right_curve,
                                    debug_path / "02_right_curve_flow.jpg")

        # 2. Correspondencias lado a lado
        h, w = left_img.shape[:2]
        combined = np.zeros((h, w*2, 3), dtype=np.uint8)

        if len(left_img.shape) == 2:
            combined[:, :w] = cv2.cvtColor(left_img, cv2.COLOR_GRAY2BGR)
            combined[:, w:] = cv2.cvtColor(right_img, cv2.COLOR_GRAY2BGR)
        else:
            combined[:, :w] = left_img
            combined[:, w:] = right_img

        # Dibujar matches con color basado en disparidad
        disp_norm = (disparities - np.min(disparities)) / (np.max(disparities) - np.min(disparities) + 1e-8)

        for idx, (x_left, y_left, x_right, disp) in enumerate(matches):
            color_val = int(disp_norm[idx] * 255)
            color = cv2.applyColorMap(np.array([[color_val]], dtype=np.uint8),
                                     cv2.COLORMAP_JET)[0, 0]
            color = tuple(map(int, color))

            cv2.circle(combined, (x_left, y_left), 2, color, -1)
            cv2.circle(combined, (x_right + w, y_left), 2, color, -1)
            cv2.line(combined, (x_left, y_left), (x_right + w, y_left), color, 1)

        cv2.imwrite(str(debug_path / "03_correspondences.jpg"), combined)

        # 3. Mapa de disparidad sparse
        disp_vis = np.zeros((h, w, 3), dtype=np.uint8)

        for idx, (x_left, y_left, x_right, disp) in enumerate(matches):
            color_val = int(disp_norm[idx] * 255)
            color = cv2.applyColorMap(np.array([[color_val]], dtype=np.uint8),
                                     cv2.COLORMAP_JET)[0, 0]
            cv2.circle(disp_vis, (x_left, y_left), 2, tuple(map(int, color)), -1)

        cv2.imwrite(str(debug_path / "04_disparity_sparse.png"), disp_vis)

        # 4. Histograma
        try:
            import matplotlib
            matplotlib.use('Agg')
            import matplotlib.pyplot as plt

            fig, ax = plt.subplots(1, 1, figsize=(10, 6))

            ax.hist(disparities, bins=50, color='blue', alpha=0.7, edgecolor='black')
            ax.set_xlabel('Disparidad (píxeles)')
            ax.set_ylabel('Frecuencia')
            ax.set_title(f'Histograma de Disparidad Geométrica\n'
                        f'Media: {result["mean_disparity"]:.1f}px, '
                        f'Std: {result["std_disparity"]:.1f}px')
            ax.grid(True, alpha=0.3)

            plt.tight_layout()
            plt.savefig(str(debug_path / "05_disparity_histogram.png"))
            plt.close()

        except Exception as e:
            logger.warning(f"No se pudo generar histograma: {e}")

        logger.info(f"✓ Visualizaciones guardadas en: {debug_path}")


if __name__ == "__main__":
    print("="*80)
    print("GEOMETRIC WIRE MATCHER - TEST")
    print("="*80)
    print("\nEste módulo requiere imágenes reales para testing.")
    print("Usa test_geometric_wire_matching.py para ejecutar.")
