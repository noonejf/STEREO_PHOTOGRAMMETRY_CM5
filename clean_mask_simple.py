#!/usr/bin/env python3
"""
Limpieza SIMPLE de mascara - Sin intentar separar nada

1. Limpiar ruido y protuberancias
2. Crear skeleton limpio
3. Trazar curva continua
"""

import cv2
import numpy as np
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent))

from processing.curve_tracker import CurveTracker


def clean_mask_simple(mask_path: str, min_area: int = 100):
    """
    Limpieza simple: remover ruido, mantener solo la region principal
    """

    print("="*80)
    print("LIMPIEZA SIMPLE DE MASCARA")
    print("="*80)

    # Cargar mascara
    mask = cv2.imread(mask_path, cv2.IMREAD_GRAYSCALE)
    if mask is None:
        print(f"\nERROR: No se pudo cargar: {mask_path}")
        return

    print(f"\nMascara original: {np.sum(mask > 0)} pixeles")

    # PASO 1: Operacion OPEN para eliminar protuberancias pequeñas
    print("\n[1] Eliminando protuberancias y ruido...")
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
    mask_opened = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel, iterations=2)
    print(f"    Despues de OPEN: {np.sum(mask_opened > 0)} pixeles")

    # PASO 2: Cerrar gaps pequeños
    print("\n[2] Cerrando gaps pequenos...")
    kernel_close = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
    mask_closed = cv2.morphologyEx(mask_opened, cv2.MORPH_CLOSE, kernel_close, iterations=1)
    print(f"    Despues de CLOSE: {np.sum(mask_closed > 0)} pixeles")

    # PASO 3: Mantener solo la componente más grande
    print("\n[3] Manteniendo solo componente principal...")
    num_labels, labels, stats, _ = cv2.connectedComponentsWithStats(mask_closed, connectivity=8)

    if num_labels <= 1:
        mask_main = mask_closed
    else:
        # Encontrar componente más grande (excluyendo fondo=0)
        areas = [stats[i, cv2.CC_STAT_AREA] for i in range(1, num_labels)]
        largest_idx = np.argmax(areas) + 1

        mask_main = np.zeros_like(mask_closed)
        mask_main[labels == largest_idx] = 255

    print(f"    Componente principal: {np.sum(mask_main > 0)} pixeles")

    # PASO 4: Skeleton simple
    print("\n[4] Creando skeleton...")
    skeleton = cv2.ximgproc.thinning(mask_main, thinningType=cv2.ximgproc.THINNING_ZHANGSUEN)
    skeleton = (skeleton > 0).astype(np.uint8)
    print(f"    Skeleton: {np.sum(skeleton > 0)} pixeles")

    # PASO 5: Trazar curva continua
    print("\n[5] Trazando curva continua...")
    tracker = CurveTracker()
    result = tracker.extract_and_order_skeleton(skeleton, sample_spacing=3)

    if not result['success']:
        print(f"    ERROR: {result['error']}")
        return None

    print(f"    Curva: {result['num_points']} puntos")
    print(f"    Endpoints: {result['endpoints']}")

    # Guardar resultados
    debug_path = Path("data/results/debug/simple_clean")
    debug_path.mkdir(parents=True, exist_ok=True)

    print(f"\n[6] Guardando resultados...")

    cv2.imwrite(str(debug_path / "01_original.png"), mask)
    cv2.imwrite(str(debug_path / "02_opened.png"), mask_opened)
    cv2.imwrite(str(debug_path / "03_closed.png"), mask_closed)
    cv2.imwrite(str(debug_path / "04_main_component.png"), mask_main)
    cv2.imwrite(str(debug_path / "05_skeleton.png"), skeleton * 255)

    print(f"    Mascaras guardadas en: {debug_path}")

    # Visualizar curva en imagen original
    img_path = "data/captures/stereo_20251119_175650/left.jpg"
    img = cv2.imread(img_path)

    if img is not None:
        tracker.visualize_curve(img, result['ordered_points'],
                              debug_path / "06_curve_on_image.jpg")
        print(f"    Curva visualizada: 06_curve_on_image.jpg")

    print(f"\n{'='*80}")
    print("COMPLETADO")
    print(f"{'='*80}")
    print(f"Pixeles: {np.sum(mask > 0)} -> {np.sum(skeleton > 0)}")
    print(f"Puntos ordenados: {result['num_points']}")
    print(f"Endpoints: {result['endpoints']}")
    print(f"{'='*80}\n")

    return {
        'mask_clean': mask_main,
        'skeleton': skeleton,
        'curve_points': result['ordered_points'],
        'endpoints': result['endpoints']
    }


if __name__ == "__main__":
    # Procesar LEFT
    print("\n" + "#"*80)
    print("PROCESANDO LEFT")
    print("#"*80 + "\n")

    result_left = clean_mask_simple("data/results/debug/cable_mask_left.png")

    # Procesar RIGHT
    print("\n" + "#"*80)
    print("PROCESANDO RIGHT")
    print("#"*80 + "\n")

    result_right = clean_mask_simple("data/results/debug/cable_mask_right.png")

    print("\nPROCESO COMPLETADO\n")
