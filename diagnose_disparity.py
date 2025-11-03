#!/usr/bin/env python3
"""
Diagnóstico detallado de disparidad

Analiza el mapa de disparidad CRUDO para ver qué valores reales tiene
"""

import cv2
import numpy as np
from pathlib import Path
import json

def diagnose_disparity():
    """Diagnosticar mapa de disparidad"""

    print("="*70)
    print("DIAGNÓSTICO DETALLADO DE DISPARIDAD")
    print("="*70)
    print()

    # Leer imágenes originales rectificadas
    left_rect = cv2.imread("data/results/debug/03_left_rectified.jpg")
    right_rect = cv2.imread("data/results/debug/04_right_rectified.jpg")

    if left_rect is None or right_rect is None:
        print("❌ No se encontraron imágenes rectificadas")
        return

    h, w = left_rect.shape[:2]
    print(f"📐 Dimensiones: {w} x {h}")
    print()

    # Leer mapa de disparidad (formato PNG de 8-bit)
    disp_img = cv2.imread("data/results/debug/10_disparity_final.png", cv2.IMREAD_GRAYSCALE)

    if disp_img is None:
        print("❌ No se encontró mapa de disparidad")
        return

    # El mapa está normalizado 0-255, necesitamos desnormalizarlo
    # Leer calibración para saber el rango real
    calib_path = Path("data/calibration/calibration_data.json")
    if calib_path.exists():
        with open(calib_path) as f:
            calib = json.load(f)

        print("📊 CALIBRACIÓN:")
        print(f"   Baseline: {calib['baseline_meters']*1000:.1f} mm")
        print(f"   Focal: {calib['projection_left'][0][0]:.1f} px")
        print(f"   Error: {calib['calibration_error']:.3f} px")
        print()

    # Analizar regiones específicas
    print("🔍 ANÁLISIS POR REGIONES:")
    print()

    # Definir regiones de interés
    regions = {
        "Superior Izquierdo (fondo)": (slice(0, h//3), slice(0, w//3)),
        "Centro (posible mano)": (slice(h//3, 2*h//3), slice(w//3, 2*w//3)),
        "Inferior (fondo)": (slice(2*h//3, h), slice(w//3, 2*w//3)),
    }

    for name, (row_slice, col_slice) in regions.items():
        region = disp_img[row_slice, col_slice]
        valid = region[region > 0]

        if len(valid) > 0:
            print(f"{name}:")
            print(f"   Píxeles válidos: {len(valid):,} ({100*len(valid)/region.size:.1f}%)")
            print(f"   Valor normalizado: min={np.min(valid):.1f}, max={np.max(valid):.1f}, mean={np.mean(valid):.1f}")

            # Estimar disparidad real (asumiendo que 255 = maxDisp)
            # En tu caso maxDisp probablemente es 64
            max_disp = 64
            real_disp_min = (np.min(valid) / 255.0) * max_disp
            real_disp_max = (np.max(valid) / 255.0) * max_disp
            real_disp_mean = (np.mean(valid) / 255.0) * max_disp

            print(f"   Disparidad real estimada: min={real_disp_min:.1f}px, max={real_disp_max:.1f}px, mean={real_disp_mean:.1f}px")

            # Calcular profundidad
            if calib_path.exists():
                baseline = calib['baseline_meters']
                focal = calib['projection_left'][0][0]

                if real_disp_mean > 0.1:
                    depth_mean = (baseline * focal) / real_disp_mean
                    depth_min = (baseline * focal) / real_disp_max if real_disp_max > 0.1 else 999
                    depth_max = (baseline * focal) / real_disp_min if real_disp_min > 0.1 else 999

                    print(f"   Profundidad estimada: min={depth_min:.2f}m, max={depth_max:.2f}m, mean={depth_mean:.2f}m")
            print()
        else:
            print(f"{name}:")
            print(f"   ❌ SIN disparidad válida")
            print()

    # Verificar si hay regiones con disparidad = 0
    zero_pixels = np.sum(disp_img == 0)
    print(f"⚠️  PÍXELES CON DISPARIDAD = 0: {zero_pixels:,} ({100*zero_pixels/disp_img.size:.1f}%)")
    print()

    if zero_pixels > disp_img.size * 0.5:
        print("❌ MÁS DEL 50% tiene disparidad = 0")
        print("   Esto significa que NO se encontraron correspondencias")
        print()
        print("💡 POSIBLES CAUSAS:")
        print("   1. Imágenes muy similares (poca diferencia estéreo)")
        print("   2. Objetos demasiado lejos (disparidad imperceptible)")
        print("   3. Parámetros SGBM demasiado restrictivos")
        print("   4. Calibración muy incorrecta (rectificación mal)")
        print()

    # Analizar correspondencias en puntos específicos
    print("🎯 VERIFICACIÓN DE CORRESPONDENCIAS EN PUNTOS ESPECÍFICOS:")
    print()

    # Seleccionar 5 puntos manualmente para verificar
    test_points = [
        (w//4, h//3, "Parte superior izquierda"),
        (w//2, h//3, "Parte superior centro"),
        (3*w//4, h//3, "Parte superior derecha"),
        (w//2, h//2, "Centro de imagen"),
        (w//2, 2*h//3, "Parte inferior centro"),
    ]

    for x, y, desc in test_points:
        disp_val_norm = disp_img[y, x]

        if disp_val_norm > 0:
            disp_val_real = (disp_val_norm / 255.0) * 64  # Asumiendo numDisparities=64
            x_right = x - disp_val_real

            print(f"{desc}:")
            print(f"   Imagen IZQ: ({x:4d}, {y:4d})")
            print(f"   Imagen DER: ({x_right:7.1f}, {y:4d})  ← desplazado {disp_val_real:.1f}px a la izquierda")

            if abs(disp_val_real) < 1.0:
                print(f"   ⚠️  Disparidad MUY PEQUEÑA (<1px) - prácticamente sin desplazamiento")
            elif abs(disp_val_real) < 5.0:
                print(f"   ⚠️  Disparidad pequeña (<5px) - difícil de ver visualmente")
            else:
                print(f"   ✅ Disparidad apreciable (>5px)")
            print()
        else:
            print(f"{desc}:")
            print(f"   ❌ SIN DISPARIDAD (valor = 0)")
            print()

    print("="*70)
    print("💡 INTERPRETACIÓN:")
    print("="*70)
    print()

    avg_valid = np.mean(disp_img[disp_img > 0]) if np.any(disp_img > 0) else 0
    avg_real = (avg_valid / 255.0) * 64

    if avg_real < 2.0:
        print("❌ PROBLEMA GRAVE: Disparidad promedio < 2px")
        print()
        print("Esto explica por qué ves 'puntos en el mismo lugar':")
        print("- Con disparidad < 2px, el desplazamiento es IMPERCEPTIBLE")
        print("- Visualmente parece que no hay diferencia entre imágenes")
        print()
        print("CAUSAS POSIBLES:")
        print("1. Escena está DEMASIADO LEJOS (>10m)")
        print("2. Baseline muy pequeño (~1cm en vez de ~10cm)")
        print("3. Calibración COMPLETAMENTE incorrecta")
        print("4. Imágenes LEFT/RIGHT son la MISMA imagen")
        print()
        print("SOLUCIÓN:")
        print("✅ RE-CALIBRAR completamente el sistema")
        print("✅ Verificar que LEFT y RIGHT sean DIFERENTES imágenes")
        print("✅ Capturar objetos más CERCA (<2 metros)")

    elif avg_real < 10.0:
        print("⚠️  Disparidad baja: promedio {avg_real:.1f}px")
        print()
        print("Con disparidad tan baja (<10px), las correspondencias")
        print("son difíciles de ver visualmente.")
        print()
        print("SOLUCIÓN:")
        print("✅ RE-CALIBRAR el sistema")
        print("✅ Capturar objetos más CERCA")

    else:
        print(f"✅ Disparidad razonable: promedio {avg_real:.1f}px")
        print()
        print("Si aún ves 'puntos en mismo lugar', puede ser:")
        print("1. Error en visualización (bug en código)")
        print("2. Solo algunos puntos tienen disparidad baja")

if __name__ == "__main__":
    diagnose_disparity()
