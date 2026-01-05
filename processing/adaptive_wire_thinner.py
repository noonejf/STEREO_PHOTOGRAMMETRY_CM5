#!/usr/bin/env python3
"""
Adaptive Wire Thinner - Adelgazamiento adaptativo basado en ancho local

Estrategia SIMPLE y DIRECTA:
1. Calcular transformada de distancia (grosor local)
2. Para cada pixel, si el grosor local >umbral, crear skeleton local
3. Resultado: skeleton con grosor adaptativo uniforme
"""

import cv2
import numpy as np
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))


def adaptive_thin_mask(mask: np.ndarray, target_width: int = 8) -> np.ndarray:
    """
    Adelgazar máscara de forma adaptativa

    Args:
        mask: Máscara binaria (255=cable, 0=fondo)
        target_width: Ancho objetivo del cable (en pixeles)

    Returns:
        Máscara adelgazada
    """

    print(f"  Adelgazamiento adaptativo (ancho objetivo: {target_width}px)...")

    # PASO 1: Limpieza básica
    kernel_clean = np.ones((3, 3), np.uint8)
    mask_clean = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel_clean)

    # PASO 2: Cerrar gaps pequeños
    kernel_close = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
    mask_closed = cv2.morphologyEx(mask_clean, cv2.MORPH_CLOSE, kernel_close)

    # PASO 3: Calcular transformada de distancia
    dist_transform = cv2.distanceTransform(mask_closed, cv2.DIST_L2, 5)

    # PASO 4: Crear máscara adelgazada usando umbral en la distancia
    # Los pixeles con alta distancia (centro del cable) se mantienen
    # Los pixeles con baja distancia (bordes) se eliminan
    threshold = target_width / 2.0
    mask_thin = (dist_transform >= threshold / 2).astype(np.uint8) * 255

    # PASO 5: Skeleton final
    skeleton = cv2.ximgproc.thinning(mask_thin, thinningType=cv2.ximgproc.THINNING_ZHANGSUEN)
    skeleton = (skeleton > 0).astype(np.uint8)

    print(f"    Pixeles: {np.sum(mask > 0)} -> {np.sum(skeleton > 0)}")

    return skeleton


def test_adaptive_thinner():
    """Test del adelgazamiento adaptativo"""

    print("="*80)
    print("TEST: Adaptive Wire Thinner")
    print("="*80)

    # Cargar máscara
    mask_path = "data/results/debug/cable_mask_left.png"
    mask = cv2.imread(mask_path, cv2.IMREAD_GRAYSCALE)

    if mask is None:
        print(f"\nERROR: No se pudo cargar: {mask_path}")
        return

    print(f"\nMascara: {mask.shape}")
    print(f"Pixeles originales: {np.sum(mask > 0)}")

    # Probar diferentes anchos objetivo
    target_widths = [4, 6, 8, 10, 12]

    debug_path = Path("data/results/debug/adaptive_thinner")
    debug_path.mkdir(parents=True, exist_ok=True)

    # Guardar original
    cv2.imwrite(str(debug_path / "00_original.png"), mask)

    results = []

    for width in target_widths:
        print(f"\n[Testing width={width}]")
        skeleton = adaptive_thin_mask(mask, target_width=width)

        filename = f"{width:02d}_width_{width}px.png"
        cv2.imwrite(str(debug_path / filename), skeleton * 255)

        pixels = np.sum(skeleton > 0)
        results.append((width, pixels))

        print(f"  Guardado: {filename}")

    print("\n" + "="*80)
    print("RESULTADOS")
    print("="*80)
    print(f"Ancho objetivo  |  Pixeles finales")
    print("-" * 40)
    for width, pixels in results:
        print(f"  {width:2d} px        |  {pixels:6d}")

    print("\n" + "="*80)


if __name__ == "__main__":
    test_adaptive_thinner()
