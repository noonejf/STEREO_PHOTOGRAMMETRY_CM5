#!/usr/bin/env python3
"""
SOLUCION FINAL: Limpieza inteligente de mascara de cable

Combina:
1. Adelgazamiento adaptativo
2. Detección de endpoints robusta
3. CurveTracker con refinamiento direccional mejorado
"""

import cv2
import numpy as np
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent))

from processing.adaptive_wire_thinner import adaptive_thin_mask
from processing.curve_tracker import CurveTracker


def clean_wire_mask_complete(mask: np.ndarray, target_width: int = 8) -> dict:
    """
    Limpieza completa de máscara de cable

    Args:
        mask: Máscara binaria manual (255=cable, 0=fondo)
        target_width: Ancho objetivo para adelgazamiento

    Returns:
        Dict con máscara limpia y metadatos
    """

    print(f"\n{'='*80}")
    print("LIMPIEZA COMPLETA DE MASCARA DE CABLE")
    print(f"{'='*80}\n")

    print(f"[1/3] Adelgazamiento adaptativo (ancho objetivo: {target_width}px)...")
    skeleton = adaptive_thin_mask(mask, target_width=target_width)
    print(f"      Pixeles: {np.sum(mask > 0)} -> {np.sum(skeleton > 0)}")

    print(f"\n[2/3] Extrayendo curva ordenada con CurveTracker...")
    tracker = CurveTracker()
    result = tracker.extract_and_order_skeleton(skeleton, sample_spacing=3)

    if not result['success']:
        print(f"\n ERROR: {result['error']}")
        return {'success': False, 'error': result['error']}

    print(f"      Curva: {result['num_points']} puntos")
    print(f"      Endpoints: {result['endpoints']}")

    start, end = result['endpoints']
    dist = np.linalg.norm(np.array(start) - np.array(end))
    print(f"      Distancia endpoints: {dist:.1f} px")

    print(f"\n[3/3] Verificando calidad...")

    # Verificar que los endpoints estén en extremos opuestos
    # (distancia razonable)
    diagonal = np.sqrt(mask.shape[0]**2 + mask.shape[1]**2)
    if dist < diagonal * 0.3:
        print(f"      WARNING: Endpoints muy cercanos ({dist:.1f} px)")

    print(f"\n{'='*80}")
    print("LIMPIEZA COMPLETADA EXITOSAMENTE")
    print(f"{'='*80}")

    return {
        'success': True,
        'mask_clean': result['skeleton'],
        'ordered_points': result['ordered_points'],
        'endpoints': result['endpoints'],
        'num_points': result['num_points'],
        'pixels_original': np.sum(mask > 0),
        'pixels_skeleton': np.sum(skeleton > 0),
        'pixels_final': result['num_points']
    }


def test_complete_cleaning():
    """Test de limpieza completa"""

    print("\n" + "="*80)
    print("TEST: Limpieza Completa de Mascara de Cable")
    print("="*80)

    # Cargar máscaras manuales
    left_mask_path = "data/results/debug/cable_mask_left.png"
    right_mask_path = "data/results/debug/cable_mask_right.png"

    left_mask = cv2.imread(left_mask_path, cv2.IMREAD_GRAYSCALE)
    right_mask = cv2.imread(right_mask_path, cv2.IMREAD_GRAYSCALE)

    if left_mask is None or right_mask is None:
        print("\nERROR: No se pudieron cargar las mascaras")
        return

    print(f"\nMascaras cargadas:")
    print(f"  LEFT:  {np.sum(left_mask > 0)} pixeles")
    print(f"  RIGHT: {np.sum(right_mask > 0)} pixeles")

    # Procesar LEFT
    print(f"\n{'#'*80}")
    print("PROCESANDO MASCARA LEFT")
    print(f"{'#'*80}")

    result_left = clean_wire_mask_complete(left_mask, target_width=8)

    if not result_left['success']:
        print("\nERROR en LEFT")
        return

    # Procesar RIGHT
    print(f"\n{'#'*80}")
    print("PROCESANDO MASCARA RIGHT")
    print(f"{'#'*80}")

    result_right = clean_wire_mask_complete(right_mask, target_width=8)

    if not result_right['success']:
        print("\nERROR en RIGHT")
        return

    # Guardar resultados
    debug_path = Path("data/results/debug/final_clean")
    debug_path.mkdir(parents=True, exist_ok=True)

    print(f"\n{'='*80}")
    print("GUARDANDO RESULTADOS")
    print(f"{'='*80}")

    # Guardar máscaras limpias
    cv2.imwrite(str(debug_path / "clean_left.png"),
               result_left['mask_clean'] * 255)
    cv2.imwrite(str(debug_path / "clean_right.png"),
               result_right['mask_clean'] * 255)

    print(f"  Guardado: {debug_path / 'clean_left.png'}")
    print(f"  Guardado: {debug_path / 'clean_right.png'}")

    # Visualizar curvas en imagen original
    left_img = cv2.imread("data/captures/stereo_20251119_175650/left.jpg")
    right_img = cv2.imread("data/captures/stereo_20251119_175650/right.jpg")

    if left_img is not None:
        tracker = CurveTracker()
        tracker.visualize_curve(left_img, result_left['ordered_points'],
                              debug_path / "curve_left.jpg")
        print(f"  Guardado: {debug_path / 'curve_left.jpg'}")

    if right_img is not None:
        tracker.visualize_curve(right_img, result_right['ordered_points'],
                              debug_path / "curve_right.jpg")
        print(f"  Guardado: {debug_path / 'curve_right.jpg'}")

    # Resumen final
    print(f"\n{'='*80}")
    print("RESUMEN FINAL")
    print(f"{'='*80}")

    print(f"\nLEFT:")
    print(f"  Pixeles originales: {result_left['pixels_original']}")
    print(f"  Pixeles skeleton:   {result_left['pixels_skeleton']}")
    print(f"  Puntos ordenados:   {result_left['num_points']}")
    print(f"  Endpoints:          {result_left['endpoints']}")

    print(f"\nRIGHT:")
    print(f"  Pixeles originales: {result_right['pixels_original']}")
    print(f"  Pixeles skeleton:   {result_right['pixels_skeleton']}")
    print(f"  Puntos ordenados:   {result_right['num_points']}")
    print(f"  Endpoints:          {result_right['endpoints']}")

    print(f"\n{'='*80}")
    print("PROCESO COMPLETADO")
    print(f"{'='*80}\n")


if __name__ == "__main__":
    test_complete_cleaning()
