#!/usr/bin/env python3
"""
Verificar coordenadas exactas de correspondencias

Lee la imagen de correspondencias y verifica si los puntos
realmente están en coordenadas diferentes
"""

import cv2
import numpy as np
from pathlib import Path

def check_coords():
    """Verificar coordenadas de correspondencias"""

    print("="*70)
    print("VERIFICACIÓN DE COORDENADAS DE CORRESPONDENCIAS")
    print("="*70)
    print()

    # Leer imagen de correspondencias
    corr_img = cv2.imread("data/results/debug/15_correspondences.jpg")
    if corr_img is None:
        print("❌ No se encontró imagen de correspondencias")
        return

    h, w, _ = corr_img.shape
    half_w = w // 2

    print(f"📐 Imagen completa: {w} x {h}")
    print(f"   Cada sub-imagen: {half_w} x {h}")
    print()

    # Detectar círculos (puntos de correspondencia) usando detección de color
    # Los puntos están en colores específicos: verde, rojo, azul, amarillo, magenta, cyan

    colors_to_find = [
        ("Verde", [0, 255, 0]),
        ("Rojo", [0, 0, 255]),  # BGR format
        ("Azul", [255, 0, 0]),
        ("Amarillo", [0, 255, 255]),
        ("Magenta", [255, 0, 255]),
        ("Cyan", [255, 255, 0])
    ]

    print("🔍 BUSCANDO CORRESPONDENCIAS POR COLOR:")
    print()

    for color_name, color_bgr in colors_to_find:
        # Crear máscara para este color (con tolerancia)
        lower = np.array([max(0, c-30) for c in color_bgr])
        upper = np.array([min(255, c+30) for c in color_bgr])

        mask = cv2.inRange(corr_img, lower, upper)

        # Encontrar contornos
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        if len(contours) >= 2:
            # Obtener centros de los dos puntos más grandes
            areas = [(cv2.contourArea(c), c) for c in contours]
            areas.sort(key=lambda x: x[0], reverse=True)

            if len(areas) >= 2:
                # Punto en imagen izquierda
                M1 = cv2.moments(areas[0][1])
                if M1["m00"] > 0:
                    x1 = int(M1["m10"] / M1["m00"])
                    y1 = int(M1["m01"] / M1["m00"])
                else:
                    continue

                # Punto en imagen derecha
                M2 = cv2.moments(areas[1][1])
                if M2["m00"] > 0:
                    x2 = int(M2["m10"] / M2["m00"])
                    y2 = int(M2["m01"] / M2["m00"])
                else:
                    continue

                # Determinar cuál está en izq y cuál en der
                if x1 < half_w and x2 >= half_w:
                    left_x, left_y = x1, y1
                    right_x, right_y = x2 - half_w, y2  # Ajustar coordenada
                elif x2 < half_w and x1 >= half_w:
                    left_x, left_y = x2, y2
                    right_x, right_y = x1 - half_w, y1
                else:
                    # Ambos en mismo lado, skip
                    continue

                # Calcular disparidad
                disparity = left_x - right_x

                print(f"Punto {color_name}:")
                print(f"   Imagen IZQ: ({left_x:4d}, {left_y:4d})")
                print(f"   Imagen DER: ({right_x:4d}, {right_y:4d})")
                print(f"   Disparidad: {disparity:6.1f} px")

                if abs(disparity) < 1:
                    print(f"   ❌ MISMO LUGAR (disparidad ≈ 0)")
                elif abs(disparity) < 5:
                    print(f"   ⚠️  Disparidad muy pequeña (<5px)")
                elif disparity > 0:
                    print(f"   ✅ Desplazado a la IZQUIERDA (correcto)")
                else:
                    print(f"   ❌ Desplazado a la DERECHA (invertido!)")
                print()

    print("="*70)
    print()
    print("💡 INTERPRETACIÓN:")
    print()
    print("Si ves muchos puntos con 'MISMO LUGAR' o 'disparidad < 5px':")
    print("   → El algoritmo NO está encontrando correspondencias correctas")
    print("   → Posible calibración muy mala")
    print()
    print("Si ves 'Desplazado a la DERECHA':")
    print("   → Las cámaras están INVERTIDAS físicamente")
    print()
    print("Si ves 'Desplazado a la IZQUIERDA' con valores >5px:")
    print("   → ✅ Las correspondencias están CORRECTAS")
    print("   → El problema es otro (quizás solo percepción visual)")

if __name__ == "__main__":
    check_coords()
