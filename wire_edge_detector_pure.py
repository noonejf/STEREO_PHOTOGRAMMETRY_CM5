#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Detector PURO de bordes del cable
SIN rellenar gaps - SOLO detecta bordes reales que existen
"""

import sys
import cv2
import numpy as np
from pathlib import Path

if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')


def detect_wire_edges_pure(img, canny_low=10, canny_high=30, min_dilation=1):
    """
    Detector PURO de bordes - NO inventa píxeles

    Args:
        img: Imagen de entrada
        canny_low: Umbral bajo de Canny
        canny_high: Umbral alto de Canny
        min_dilation: Iteraciones mínimas de dilatación (solo para engrosar ligeramente el borde)

    Returns:
        edge_mask: Máscara binaria SOLO con bordes reales detectados
        stats: Estadísticas
    """

    # Convertir a escala de grises
    if len(img.shape) == 3:
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    else:
        gray = img.copy()

    # Suavizado MÍNIMO
    blurred = cv2.GaussianBlur(gray, (3, 3), 0)

    # Canny - DETECCIÓN PURA de bordes
    edges = cv2.Canny(blurred, threshold1=canny_low, threshold2=canny_high,
                     apertureSize=3, L2gradient=True)

    # Dilatación MÍNIMA - solo para engrosar ligeramente el borde (1-2 píxeles)
    # Esto ayuda a SGBM a tener más contexto, pero NO rellena gaps grandes
    if min_dilation > 0:
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
        edge_mask = cv2.dilate(edges, kernel, iterations=min_dilation)
    else:
        edge_mask = edges

    # Estadísticas
    pixels_detected = np.sum(edge_mask > 0)
    percentage = 100 * pixels_detected / edge_mask.size

    stats = {
        'pixels_detected': int(pixels_detected),
        'percentage': percentage,
        'canny_params': (canny_low, canny_high),
        'dilation_iterations': min_dilation
    }

    return edge_mask, stats


def test_pure_detection():
    """Probar detector puro con diferentes configuraciones"""

    print("="*80)
    print("DETECTOR PURO DE BORDES - Sin rellenar gaps")
    print("="*80)

    # Cargar imágenes
    left_path = Path("data/results/debug/01_left_original.jpg")
    right_path = Path("data/results/debug/02_right_original.jpg")

    if not left_path.exists():
        print(f"❌ ERROR: No se encuentra {left_path}")
        return

    left_img = cv2.imread(str(left_path))
    right_img = cv2.imread(str(right_path))

    print(f"\n📂 Imágenes cargadas:")
    print(f"   Left: {left_img.shape}")
    print(f"   Right: {right_img.shape}")

    debug_path = Path("data/results/debug/wire_pure")
    debug_path.mkdir(parents=True, exist_ok=True)

    # Probar diferentes configuraciones de Canny
    configs = [
        (5, 15, "Ultra sensible"),
        (10, 30, "Sensible (original)"),
        (15, 45, "Moderado"),
        (20, 60, "Conservador"),
    ]

    print("\n" + "="*80)
    print("PROBANDO DIFERENTES SENSIBILIDADES DE CANNY")
    print("="*80)

    for low, high, name in configs:
        print(f"\n{'='*60}")
        print(f"{name}: low={low}, high={high}")
        print(f"{'='*60}")

        # Detectar en ambas imágenes
        left_mask, left_stats = detect_wire_edges_pure(left_img, low, high, min_dilation=1)
        right_mask, right_stats = detect_wire_edges_pure(right_img, low, high, min_dilation=1)

        print(f"   Left:  {left_stats['pixels_detected']} px ({left_stats['percentage']:.2f}%)")
        print(f"   Right: {right_stats['pixels_detected']} px ({right_stats['percentage']:.2f}%)")

        # Guardar visualizaciones
        # Left
        overlay_left = left_img.copy()
        overlay_left[left_mask > 0] = [0, 255, 0]
        result_left = cv2.addWeighted(left_img, 0.7, overlay_left, 0.3, 0)
        cv2.imwrite(str(debug_path / f"left_{name.replace(' ', '_')}_overlay.jpg"), result_left)
        cv2.imwrite(str(debug_path / f"left_{name.replace(' ', '_')}_mask.png"), left_mask)

        # Right
        overlay_right = right_img.copy()
        overlay_right[right_mask > 0] = [0, 255, 0]
        result_right = cv2.addWeighted(right_img, 0.7, overlay_right, 0.3, 0)
        cv2.imwrite(str(debug_path / f"right_{name.replace(' ', '_')}_overlay.jpg"), result_right)
        cv2.imwrite(str(debug_path / f"right_{name.replace(' ', '_')}_mask.png"), right_mask)

    print("\n" + "="*80)
    print("✅ DETECCIÓN PURA COMPLETADA")
    print("="*80)
    print(f"\nRevisa: {debug_path}/")
    print("\nArchivos generados:")
    print("  - *_overlay.jpg : Bordes detectados en verde")
    print("  - *_mask.png    : Máscara binaria pura")
    print("\n💡 IMPORTANTE:")
    print("   - Estos son SOLO los bordes REALES detectados")
    print("   - NO se rellenan gaps ni se inventan píxeles")
    print("   - Úsalos para SGBM - matcheará solo donde hay textura real")


if __name__ == "__main__":
    test_pure_detection()
