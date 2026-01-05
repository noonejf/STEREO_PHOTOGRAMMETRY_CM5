#!/usr/bin/env python3
"""
Flow-Based Wire Cleaner - Limpieza basada en flujo de direccion

Estrategia completamente diferente:
1. Calcular campo de gradiente/dirección en toda la máscara
2. Desde los endpoints, seguir el flujo natural del cable
3. Evitar saltos direccionales bruscos (no giros de 90°)
4. Separar automáticamente secciones superpuestas
"""

import cv2
import numpy as np
from typing import Tuple, List, Optional
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))

from utils.logger import get_logger

logger = get_logger(__name__)


class FlowBasedWireCleaner:
    """
    Limpiador basado en análisis de flujo direccional
    """

    def __init__(self):
        pass

    def clean_mask(self, mask: np.ndarray, debug: bool = False) -> dict:
        """
        Limpiar máscara usando análisis de flujo direccional

        Args:
            mask: Máscara binaria (255=cable, 0=fondo)
            debug: Guardar imágenes intermedias

        Returns:
            Dict con máscara limpia
        """

        logger.info("Limpieza basada en flujo direccional...")

        # PASO 1: Pre-procesamiento básico
        logger.info("  [1/5] Pre-procesamiento...")
        mask_clean = self._preprocess(mask)

        # PASO 2: Skeleton inicial
        logger.info("  [2/5] Skeleton inicial...")
        skeleton = self._create_skeleton(mask_clean)

        # PASO 3: Calcular campo de dirección
        logger.info("  [3/5] Calculando campo de direccion...")
        direction_field = self._compute_direction_field(mask_clean)

        # PASO 4: Detectar endpoints
        logger.info("  [4/5] Detectando endpoints...")
        endpoints = self._find_endpoints(skeleton)
        logger.info(f"    Endpoints detectados: {len(endpoints)}")

        # PASO 5: Trazar desde endpoints siguiendo flujo
        logger.info("  [5/5] Trazando curva siguiendo flujo...")
        clean_curve = self._trace_from_endpoints(
            skeleton, direction_field, endpoints, mask_clean
        )

        pixels_original = np.sum(mask > 0)
        pixels_final = np.sum(clean_curve > 0)

        result = {
            'success': True,
            'mask_clean': clean_curve,
            'pixels_original': pixels_original,
            'pixels_final': pixels_final,
            'endpoints': endpoints
        }

        logger.info(f"  Pixeles: {pixels_original} -> {pixels_final}")

        if debug:
            result['intermediate'] = {
                'skeleton': skeleton,
                'direction_field': direction_field
            }

        return result

    def _preprocess(self, mask: np.ndarray) -> np.ndarray:
        """Pre-procesamiento: limpieza de ruido y cerrado de gaps"""

        # Remover ruido pequeño
        kernel_small = np.ones((3, 3), np.uint8)
        mask_opened = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel_small)

        # Cerrar gaps
        kernel_close = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 7))
        mask_closed = cv2.morphologyEx(mask_opened, cv2.MORPH_CLOSE, kernel_close)

        return mask_closed

    def _create_skeleton(self, mask: np.ndarray) -> np.ndarray:
        """Crear skeleton usando Zhang-Suen"""

        mask_binary = (mask > 0).astype(np.uint8)
        skeleton = cv2.ximgproc.thinning(
            mask_binary * 255,
            thinningType=cv2.ximgproc.THINNING_ZHANGSUEN
        )

        return (skeleton > 0).astype(np.uint8)

    def _compute_direction_field(self, mask: np.ndarray) -> np.ndarray:
        """
        Calcular campo de dirección usando transformada de distancia

        La idea: En cada punto, la dirección del cable es perpendicular
        al gradiente de la transformada de distancia
        """

        # Transformada de distancia
        dist_transform = cv2.distanceTransform(mask, cv2.DIST_L2, 5)

        # Calcular gradiente
        grad_x = cv2.Sobel(dist_transform, cv2.CV_64F, 1, 0, ksize=5)
        grad_y = cv2.Sobel(dist_transform, cv2.CV_64F, 0, 1, ksize=5)

        # Dirección perpendicular al gradiente (dirección del cable)
        # Nota: perpendicular = rotar 90°
        direction_x = -grad_y
        direction_y = grad_x

        # Normalizar
        magnitude = np.sqrt(direction_x**2 + direction_y**2) + 1e-8
        direction_x /= magnitude
        direction_y /= magnitude

        # Combinar en un solo array (dx, dy)
        direction_field = np.stack([direction_x, direction_y], axis=-1)

        return direction_field

    def _find_endpoints(self, skeleton: np.ndarray) -> List[Tuple[int, int]]:
        """Encontrar endpoints del skeleton"""

        coords = np.column_stack(np.where(skeleton > 0))
        endpoints = []

        for y, x in coords:
            neighbors = skeleton[max(0, y-1):y+2, max(0, x-1):x+2]
            num_neighbors = np.sum(neighbors) - 1

            if num_neighbors == 1:
                endpoints.append((x, y))

        # Si hay más de 2, elegir los 2 más alejados
        if len(endpoints) > 2:
            max_dist = 0
            best_pair = None

            for i, p1 in enumerate(endpoints):
                for j, p2 in enumerate(endpoints[i+1:], i+1):
                    dist = np.linalg.norm(np.array(p1) - np.array(p2))
                    if dist > max_dist:
                        max_dist = dist
                        best_pair = [p1, p2]

            if best_pair:
                endpoints = best_pair

        return endpoints

    def _trace_from_endpoints(self,
                             skeleton: np.ndarray,
                             direction_field: np.ndarray,
                             endpoints: List[Tuple[int, int]],
                             original_mask: np.ndarray) -> np.ndarray:
        """
        Trazar curva desde endpoints siguiendo campo de dirección

        Esta es la clave: en lugar de seguir el skeleton con todas sus
        bifurcaciones, seguir el FLUJO DIRECCIONAL desde los endpoints
        """

        h, w = skeleton.shape
        clean_curve = np.zeros_like(skeleton)

        if len(endpoints) < 2:
            logger.warning("    Menos de 2 endpoints, usando skeleton completo")
            return skeleton

        start_point, end_point = endpoints[:2]

        # Trazar desde start hacia end siguiendo dirección
        logger.info(f"    Trazando desde {start_point} hacia {end_point}")

        visited = np.zeros_like(skeleton, dtype=bool)
        current = np.array(start_point, dtype=float)
        target = np.array(end_point, dtype=float)

        path = [tuple(current.astype(int))]
        max_iterations = h * w  # Safety limit

        for iteration in range(max_iterations):
            x, y = int(current[0]), int(current[1])

            # Verificar límites
            if x < 0 or x >= w or y < 0 or y >= h:
                break

            # Marcar visitado
            visited[y, x] = True
            clean_curve[y, x] = 1

            # Si llegamos al endpoint final, terminar
            if np.linalg.norm(current - target) < 3:
                logger.info(f"    Alcanzado endpoint final en {iteration} pasos")
                break

            # Obtener dirección del campo
            dir_vec = direction_field[y, x]

            # Si estamos en el skeleton, usar vecinos del skeleton
            # Si no, usar dirección del campo
            if skeleton[y, x] > 0:
                # Buscar vecinos en skeleton no visitados
                neighbors = []
                for dy in [-1, 0, 1]:
                    for dx in [-1, 0, 1]:
                        if dx == 0 and dy == 0:
                            continue

                        nx, ny = x + dx, y + dy

                        if 0 <= nx < w and 0 <= ny < h:
                            if skeleton[ny, nx] > 0 and not visited[ny, nx]:
                                neighbors.append((nx, ny, dx, dy))

                if len(neighbors) == 0:
                    # No hay vecinos en skeleton, usar campo de dirección
                    next_pos = current + dir_vec * 2
                elif len(neighbors) == 1:
                    # Un solo vecino, tomarlo
                    next_pos = np.array([neighbors[0][0], neighbors[0][1]], dtype=float)
                else:
                    # Múltiples vecinos: elegir el más alineado con dirección
                    best_score = -999
                    best_neighbor = neighbors[0]

                    for nx, ny, dx, dy in neighbors:
                        vec_to_neighbor = np.array([dx, dy], dtype=float)
                        vec_to_neighbor /= (np.linalg.norm(vec_to_neighbor) + 1e-8)

                        # Producto punto con dirección del campo
                        score = np.dot(dir_vec, vec_to_neighbor)

                        # También considerar dirección hacia el target
                        vec_to_target = target - current
                        vec_to_target /= (np.linalg.norm(vec_to_target) + 1e-8)
                        score_target = np.dot(vec_to_neighbor, vec_to_target)

                        # Combinar ambos scores
                        total_score = 0.7 * score + 0.3 * score_target

                        if total_score > best_score:
                            best_score = total_score
                            best_neighbor = (nx, ny, dx, dy)

                    next_pos = np.array([best_neighbor[0], best_neighbor[1]], dtype=float)

            else:
                # Fuera del skeleton, seguir dirección del campo
                next_pos = current + dir_vec * 2

            # Actualizar posición
            current = next_pos

            # Clip a límites de imagen
            current[0] = np.clip(current[0], 0, w-1)
            current[1] = np.clip(current[1], 0, h-1)

        logger.info(f"    Trazado completado: {np.sum(clean_curve > 0)} pixeles")

        return clean_curve


def test_flow_cleaner():
    """Test del limpiador basado en flujo"""

    print("="*80)
    print("TEST: Flow-Based Wire Cleaner")
    print("="*80)

    # Cargar máscara
    mask_path = "data/results/debug/cable_mask_left.png"
    mask = cv2.imread(mask_path, cv2.IMREAD_GRAYSCALE)

    if mask is None:
        print(f"\nERROR: No se pudo cargar: {mask_path}")
        return

    print(f"\nMascara: {mask.shape}, pixeles: {np.sum(mask > 0)}")

    # Limpiar
    cleaner = FlowBasedWireCleaner()
    result = cleaner.clean_mask(mask, debug=True)

    if not result['success']:
        print("\nERROR en limpieza")
        return

    # Guardar
    debug_path = Path("data/results/debug/flow_cleaner")
    debug_path.mkdir(parents=True, exist_ok=True)

    cv2.imwrite(str(debug_path / "01_original.png"), mask)
    cv2.imwrite(str(debug_path / "02_skeleton.png"),
               result['intermediate']['skeleton'] * 255)
    cv2.imwrite(str(debug_path / "03_clean.png"),
               result['mask_clean'] * 255)

    # Visualizar campo de dirección
    dir_field = result['intermediate']['direction_field']
    dir_vis = np.zeros((*dir_field.shape[:2], 3), dtype=np.uint8)

    # Convertir direcciones a colores (HSV)
    angles = np.arctan2(dir_field[:,:,1], dir_field[:,:,0])
    angles = (angles + np.pi) / (2 * np.pi) * 180  # 0-180 para HSV Hue

    magnitudes = np.sqrt(dir_field[:,:,0]**2 + dir_field[:,:,1]**2)
    magnitudes = np.clip(magnitudes * 255, 0, 255).astype(np.uint8)

    dir_vis[:,:,0] = angles.astype(np.uint8)
    dir_vis[:,:,1] = 255
    dir_vis[:,:,2] = magnitudes

    dir_vis_bgr = cv2.cvtColor(dir_vis, cv2.COLOR_HSV2BGR)
    cv2.imwrite(str(debug_path / "04_direction_field.png"), dir_vis_bgr)

    print(f"\nResultados guardados en: {debug_path}")
    print(f"Pixeles: {result['pixels_original']} -> {result['pixels_final']}")
    print(f"Endpoints: {result['endpoints']}")

    print("\n" + "="*80)


if __name__ == "__main__":
    test_flow_cleaner()
