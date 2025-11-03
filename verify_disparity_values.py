#!/usr/bin/env python3
"""
Script para verificar los valores REALES de disparidad en el mapa
y compararlos con las correspondencias visuales
"""

import cv2
import numpy as np
from pathlib import Path

def verify_disparity_values():
    """Verificar valores de disparidad"""

    print("="*70)
    print("VERIFICACIÓN DE VALORES DE DISPARIDAD")
    print("="*70)
    print()

    # Cargar imagen de correspondencias para ver los puntos marcados
    corr_img = cv2.imread('data/results/debug/15_correspondences.jpg')
    if corr_img is None:
        print("❌ No se encontró imagen de correspondencias")
        return

    # Cargar imágenes rectificadas
    left_rect = cv2.imread('data/results/debug/03_left_rectified.jpg')
    right_rect = cv2.imread('data/results/debug/04_right_rectified.jpg')

    if left_rect is None or right_rect is None:
        print("❌ No se encontraron imágenes rectificadas")
        return

    print(f"✅ Imágenes cargadas: {left_rect.shape}")
    print()

    # La imagen de correspondencias tiene ambas imágenes side-by-side
    h, w = left_rect.shape[:2]

    # Ahora vamos a buscar manualmente algunos puntos y calcular su disparidad REAL
    # Convertir a escala de grises para matching
    left_gray = cv2.cvtColor(left_rect, cv2.COLOR_BGR2GRAY)
    right_gray = cv2.cvtColor(right_rect, cv2.COLOR_BGR2GRAY)

    # Seleccionar algunos puntos de prueba en la imagen izquierda
    # Vamos a tomar puntos con buena textura
    test_points = [
        (w//4, h//4),      # Cuadrante superior izquierdo
        (w//2, h//2),      # Centro
        (3*w//4, h//2),    # Derecha centro
        (w//2, 3*h//4),    # Inferior centro
    ]

    print("🔍 VERIFICANDO DISPARIDAD REAL MEDIANTE TEMPLATE MATCHING:")
    print()

    for i, (x, y) in enumerate(test_points):
        # Tomar template de 15x15 alrededor del punto en imagen izquierda
        template_size = 15
        half_size = template_size // 2

        if (y - half_size < 0 or y + half_size >= h or
            x - half_size < 0 or x + half_size >= w):
            continue

        template = left_gray[y-half_size:y+half_size+1, x-half_size:x+half_size+1]

        # Buscar este template en imagen derecha en la MISMA FILA (y)
        # Solo buscar hacia la izquierda (disparidad positiva)
        search_range = min(400, x)  # Buscar hasta 400 píxeles a la izquierda

        if x - search_range < half_size:
            search_range = x - half_size

        if search_range < 10:
            continue

        # Región de búsqueda en imagen derecha
        search_region = right_gray[y-half_size:y+half_size+1,
                                   x-search_range-half_size:x+half_size+1]

        # Template matching
        result = cv2.matchTemplate(search_region, template, cv2.TM_CCOEFF_NORMED)

        # Encontrar mejor match
        min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(result)

        # Calcular disparidad real
        # max_loc[0] es la posición x del match en search_region
        # La posición real en right_gray es: x - search_range - half_size + max_loc[0]
        x_right = x - search_range - half_size + max_loc[0] + half_size
        disparity_real = x - x_right

        print(f"Punto #{i+1}: ({x}, {y})")
        print(f"  Posición en LEFT:  x={x}")
        print(f"  Posición en RIGHT: x={x_right}")
        print(f"  Disparidad REAL:   {disparity_real:.1f} px")
        print(f"  Confianza match:   {max_val:.3f}")
        print()

    print("="*70)
    print()
    print("💡 CONCLUSIÓN:")
    print()
    print("Si las disparidades REALES (calculadas arriba) son ~30-50px")
    print("pero en el mapa de disparidad ves valores muy diferentes,")
    print("entonces hay un BUG en el cálculo de disparidad.")
    print()
    print("PRÓXIMO PASO:")
    print("  Necesitamos ver los valores RAW del mapa de disparidad")
    print("  para comparar con las disparidades reales.")
    print()
    print("="*70)

if __name__ == "__main__":
    verify_disparity_values()
