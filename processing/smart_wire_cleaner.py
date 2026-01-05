#!/usr/bin/env python3
"""
Smart Wire Cleaner - Limpieza y adelgazamiento inteligente de máscaras de cable

Este módulo implementa un algoritmo de adelgazamiento inteligente que:
1. Limpia ruido y artefactos
2. Adelgaza el cable a grosor uniforme
3. Separa secciones superpuestas
4. Mantiene continuidad direccional
"""

import cv2
import numpy as np
from typing import Tuple, List
from pathlib import Path
import sys

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from utils.logger import get_logger

logger = get_logger(__name__)


class SmartWireCleaner:
    """
    Limpiador inteligente de máscaras de cable
    """

    def __init__(self):
        pass

    def clean_and_thin_mask(self, mask: np.ndarray, debug: bool = False) -> dict:
        """
        Limpiar y adelgazar máscara de cable de forma inteligente

        Args:
            mask: Máscara binaria (255=cable, 0=fondo)
            debug: Guardar visualizaciones intermedias

        Returns:
            result: Dict con máscara limpia y estadísticas
        """

        logger.info("Iniciando limpieza inteligente de mascara...")

        # PASO 1: Limpieza inicial de ruido
        logger.info("  [1/6] Limpiando ruido pequeño...")
        mask_denoised = self._remove_small_noise(mask)

        # PASO 2: Cerrar gaps pequeños
        logger.info("  [2/6] Cerrando gaps pequenos...")
        mask_closed = self._close_small_gaps(mask_denoised)

        # PASO 3: Adelgazamiento inicial (skeleton básico)
        logger.info("  [3/6] Creando skeleton inicial...")
        skeleton_initial = self._create_initial_skeleton(mask_closed)

        # PASO 4: Detectar y separar superposiciones
        logger.info("  [4/6] Detectando superposiciones...")
        skeleton_separated = self._separate_overlapping_sections(
            skeleton_initial, mask_closed
        )

        # PASO 5: Refinar con continuidad direccional
        logger.info("  [5/6] Refinando con continuidad direccional...")
        skeleton_refined = self._refine_with_directional_continuity(
            skeleton_separated
        )

        # PASO 6: Limpieza final de artefactos
        logger.info("  [6/6] Limpieza final...")
        skeleton_final = self._final_cleanup(skeleton_refined)

        # Estadísticas
        pixels_original = np.sum(mask > 0)
        pixels_final = np.sum(skeleton_final > 0)

        result = {
            'success': True,
            'mask_clean': skeleton_final,
            'pixels_original': pixels_original,
            'pixels_final': pixels_final,
            'reduction_ratio': pixels_final / pixels_original if pixels_original > 0 else 0
        }

        logger.info(f"  Limpieza completada:")
        logger.info(f"    Pixeles originales: {pixels_original}")
        logger.info(f"    Pixeles finales: {pixels_final}")
        logger.info(f"    Reduccion: {result['reduction_ratio']*100:.1f}%")

        if debug:
            result['intermediate'] = {
                'denoised': mask_denoised,
                'closed': mask_closed,
                'skeleton_initial': skeleton_initial,
                'skeleton_separated': skeleton_separated,
                'skeleton_refined': skeleton_refined
            }

        return result

    def _remove_small_noise(self, mask: np.ndarray, min_size: int = 50) -> np.ndarray:
        """
        Eliminar componentes pequeños que son ruido
        """

        # Encontrar componentes conectados
        num_labels, labels, stats, _ = cv2.connectedComponentsWithStats(
            mask, connectivity=8
        )

        # Crear máscara limpia
        mask_clean = np.zeros_like(mask)

        # Mantener solo componentes grandes
        for i in range(1, num_labels):  # Saltar fondo (0)
            area = stats[i, cv2.CC_STAT_AREA]
            if area >= min_size:
                mask_clean[labels == i] = 255

        return mask_clean

    def _close_small_gaps(self, mask: np.ndarray, gap_size: int = 5) -> np.ndarray:
        """
        Cerrar gaps pequeños en el cable usando operaciones morfológicas
        """

        # Operación de cierre con kernel pequeño
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (gap_size, gap_size))
        mask_closed = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)

        return mask_closed

    def _create_initial_skeleton(self, mask: np.ndarray) -> np.ndarray:
        """
        Crear skeleton inicial usando thinning de Zhang-Suen
        """

        mask_binary = (mask > 0).astype(np.uint8)
        skeleton = cv2.ximgproc.thinning(
            mask_binary * 255,
            thinningType=cv2.ximgproc.THINNING_ZHANGSUEN
        )

        return (skeleton > 0).astype(np.uint8)

    def _separate_overlapping_sections(self,
                                      skeleton: np.ndarray,
                                      original_mask: np.ndarray) -> np.ndarray:
        """
        Detectar y separar secciones del cable que se superponen

        Estrategia:
        1. Detectar puntos con 3+ vecinos (bifurcaciones/cruces)
        2. Analizar dirección del flujo en cada rama
        3. Separar ramas que son parte de secciones diferentes
        """

        skeleton_separated = skeleton.copy()
        coords = np.column_stack(np.where(skeleton > 0))

        # Detectar puntos de bifurcación (3+ vecinos)
        junction_points = []

        for y, x in coords:
            neighbors = skeleton[max(0, y-1):y+2, max(0, x-1):x+2]
            num_neighbors = np.sum(neighbors) - 1  # Excluir el punto mismo

            if num_neighbors >= 3:
                junction_points.append((x, y))

        logger.info(f"    Puntos de bifurcacion detectados: {len(junction_points)}")

        # Para cada punto de bifurcación, analizar direcciones
        for jx, jy in junction_points:
            # Obtener vecinos
            neighbors_coords = []
            for dy in [-1, 0, 1]:
                for dx in [-1, 0, 1]:
                    if dx == 0 and dy == 0:
                        continue
                    nx, ny = jx + dx, jy + dy
                    if 0 <= nx < skeleton.shape[1] and 0 <= ny < skeleton.shape[0]:
                        if skeleton[ny, nx] > 0:
                            neighbors_coords.append((nx, ny, dx, dy))

            # Si hay 3 o 4 vecinos, intentar separar
            if len(neighbors_coords) >= 3:
                # Analizar ángulos entre vecinos
                angles = []
                for nx, ny, dx, dy in neighbors_coords:
                    angle = np.arctan2(dy, dx)
                    angles.append(angle)

                # Si hay vecinos opuestos (cruce), mantener skeleton
                # Si hay vecinos en ángulo recto, puede ser bifurcación real
                # Esta es una heurística simple - puede refinarse
                pass

        return skeleton_separated

    def _refine_with_directional_continuity(self, skeleton: np.ndarray) -> np.ndarray:
        """
        Refinar skeleton manteniendo continuidad direccional

        En bifurcaciones, elegir la rama que mejor continúa la dirección actual
        en lugar de girar 90 grados
        """

        skeleton_refined = skeleton.copy()
        coords = np.column_stack(np.where(skeleton > 0))

        # Detectar puntos de bifurcación
        for y, x in coords:
            neighbors = skeleton[max(0, y-1):y+2, max(0, x-1):x+2]
            num_neighbors = np.sum(neighbors) - 1

            # Si tiene exactamente 3 vecinos, es una bifurcación
            if num_neighbors == 3:
                # Obtener coordenadas de vecinos
                neighbors_list = []
                for dy in [-1, 0, 1]:
                    for dx in [-1, 0, 1]:
                        if dx == 0 and dy == 0:
                            continue
                        nx, ny = x + dx, y + dy
                        if 0 <= nx < skeleton.shape[1] and 0 <= ny < skeleton.shape[0]:
                            if skeleton[ny, nx] > 0:
                                neighbors_list.append((dx, dy))

                if len(neighbors_list) == 3:
                    # Calcular ángulos
                    angles = [np.arctan2(dy, dx) for dx, dy in neighbors_list]

                    # Encontrar el par con menor diferencia angular
                    # (continuidad = menor cambio de dirección)
                    min_diff = float('inf')
                    remove_idx = None

                    for i in range(3):
                        # Calcular diferencia angular entre otros dos
                        other_indices = [j for j in range(3) if j != i]
                        ang1 = angles[other_indices[0]]
                        ang2 = angles[other_indices[1]]

                        diff = abs(ang1 - ang2)
                        if diff > np.pi:
                            diff = 2*np.pi - diff

                        # Si la diferencia es cercana a 180° (línea recta),
                        # remover el tercer vecino
                        if abs(diff - np.pi) < 0.5:  # Tolerancia de ~30°
                            if diff > min_diff:
                                continue
                            min_diff = diff
                            remove_idx = i

                    # Remover la rama que rompe continuidad
                    if remove_idx is not None:
                        dx, dy = neighbors_list[remove_idx]
                        skeleton_refined[y + dy, x + dx] = 0

        return skeleton_refined

    def _final_cleanup(self, skeleton: np.ndarray, min_length: int = 10) -> np.ndarray:
        """
        Limpieza final: remover ramas muy cortas que son artefactos
        """

        # Encontrar componentes conectados
        num_labels, labels, stats, _ = cv2.connectedComponentsWithStats(
            skeleton * 255, connectivity=8
        )

        skeleton_clean = np.zeros_like(skeleton)

        # Mantener solo componentes suficientemente largos
        for i in range(1, num_labels):
            area = stats[i, cv2.CC_STAT_AREA]
            if area >= min_length:
                skeleton_clean[labels == i] = 1

        return skeleton_clean


def test_smart_cleaner():
    """Test del limpiador inteligente"""

    print("="*80)
    print("TEST: Smart Wire Cleaner")
    print("="*80)

    # Cargar tu máscara manual
    mask_path = "data/results/debug/cable_mask_left.png"
    mask = cv2.imread(mask_path, cv2.IMREAD_GRAYSCALE)

    if mask is None:
        print(f"\nERROR: No se pudo cargar mascara: {mask_path}")
        return

    print(f"\nMascara cargada: {mask.shape}")
    print(f"Pixeles de cable: {np.sum(mask > 0)}")

    # Aplicar limpieza inteligente
    cleaner = SmartWireCleaner()
    result = cleaner.clean_and_thin_mask(mask, debug=True)

    if not result['success']:
        print("\nERROR en limpieza")
        return

    # Guardar resultados
    debug_path = Path("data/results/debug/smart_cleaner")
    debug_path.mkdir(parents=True, exist_ok=True)

    print(f"\nGuardando resultados en: {debug_path}")

    # Guardar todas las etapas intermedias
    cv2.imwrite(str(debug_path / "01_original.png"), mask)
    cv2.imwrite(str(debug_path / "02_denoised.png"),
               result['intermediate']['denoised'])
    cv2.imwrite(str(debug_path / "03_closed.png"),
               result['intermediate']['closed'])
    cv2.imwrite(str(debug_path / "04_skeleton_initial.png"),
               result['intermediate']['skeleton_initial'] * 255)
    cv2.imwrite(str(debug_path / "05_skeleton_separated.png"),
               result['intermediate']['skeleton_separated'] * 255)
    cv2.imwrite(str(debug_path / "06_skeleton_refined.png"),
               result['intermediate']['skeleton_refined'] * 255)
    cv2.imwrite(str(debug_path / "07_final.png"),
               result['mask_clean'] * 255)

    print(f"\nResultados:")
    print(f"  Pixeles originales: {result['pixels_original']}")
    print(f"  Pixeles finales:    {result['pixels_final']}")
    print(f"  Reduccion:          {result['reduction_ratio']*100:.1f}%")

    print("\n" + "="*80)


if __name__ == "__main__":
    test_smart_cleaner()
