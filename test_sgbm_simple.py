#!/usr/bin/env python3
"""
Test simple de SGBM para ver si encuentra correspondencias básicas
"""

import cv2
import numpy as np

def test_sgbm():
    """Test básico de SGBM"""

    print("="*70)
    print("TEST SIMPLE DE SGBM")
    print("="*70)
    print()

    # Cargar imágenes rectificadas
    left = cv2.imread('data/results/debug/03_left_rectified.jpg', cv2.IMREAD_GRAYSCALE)
    right = cv2.imread('data/results/debug/04_right_rectified.jpg', cv2.IMREAD_GRAYSCALE)

    if left is None or right is None:
        print("❌ No se encontraron imágenes")
        return

    print(f"✅ Imágenes cargadas: {left.shape}")
    print()

    # Crear SGBM con parámetros MUY SIMPLES
    print("🔧 Probando SGBM con parámetros BÁSICOS...")

    window_size = 5
    min_disp = 0
    num_disp = 16 * 6  # Debe ser múltiplo de 16

    sgbm = cv2.StereoSGBM_create(
        minDisparity=min_disp,
        numDisparities=num_disp,
        blockSize=window_size,
        P1=8 * 3 * window_size ** 2,
        P2=32 * 3 * window_size ** 2,
        disp12MaxDiff=1,
        uniquenessRatio=15,
        speckleWindowSize=0,
        speckleRange=0,
        preFilterCap=63,
        mode=cv2.STEREO_SGBM_MODE_SGBM_3WAY
    )

    # Calcular disparidad
    print("   Calculando...")
    disparity = sgbm.compute(left, right).astype(np.float32) / 16.0

    # Estadísticas
    valid_disp = disparity[disparity > 0]

    print()
    print(f"📊 RESULTADOS:")
    print(f"   Píxeles válidos: {len(valid_disp):,} / {disparity.size:,}")
    print(f"   Cobertura: {100*len(valid_disp)/disparity.size:.1f}%")

    if len(valid_disp) > 0:
        print(f"   Min disparidad: {np.min(valid_disp):.2f} px")
        print(f"   Max disparidad: {np.max(valid_disp):.2f} px")
        print(f"   Media: {np.mean(valid_disp):.2f} px")
        print()

        if np.max(valid_disp) < 10:
            print("   ❌ Disparidades MUY PEQUEÑAS (<10px)")
            print("      SGBM NO está encontrando matches correctos")
            print()
        else:
            print("   ✅ Disparidades en rango razonable")
            print()
    else:
        print()
        print("   ❌ NO hay disparidad válida!")
        print("      SGBM NO puede encontrar ningún match")
        print()

    # Guardar visualización
    if len(valid_disp) > 0:
        disp_vis = cv2.normalize(disparity, None, 0, 255, cv2.NORM_MINMAX, dtype=cv2.CV_8U)
        disp_color = cv2.applyColorMap(disp_vis, cv2.COLORMAP_JET)
        disp_color[disparity <= 0] = [0, 0, 0]

        output_path = 'data/results/debug/test_sgbm_simple.png'
        cv2.imwrite(output_path, disp_color)
        print(f"   Mapa guardado: {output_path}")
        print()

    print("="*70)
    print()
    print("💡 INTERPRETACIÓN:")
    print()

    if len(valid_disp) == 0:
        print("❌ SGBM NO FUNCIONA EN ABSOLUTO")
        print()
        print("Posibles causas:")
        print("  1. Las imágenes NO están rectificadas correctamente")
        print("  2. Las imágenes son demasiado diferentes")
        print("  3. Hay un problema en el código")
        print()
    elif len(valid_disp) < disparity.size * 0.1:
        print("⚠️ SGBM encuentra MUY POCOS matches (<10%)")
        print()
        print("Posibles causas:")
        print("  1. Parámetros de SGBM demasiado restrictivos")
        print("  2. Falta de textura en la escena")
        print("  3. numDisparities demasiado pequeño")
        print()
    elif np.max(valid_disp) > num_disp * 0.9:
        print("⚠️ Muchas disparidades cerca del MÁXIMO")
        print()
        print(f"  numDisparities actual: {num_disp}")
        print(f"  Disparidad máxima encontrada: {np.max(valid_disp):.1f}")
        print()
        print("SOLUCIÓN: Aumentar numDisparities")
        print()
    else:
        print("✅ SGBM funciona, pero puede necesitar ajustes")
        print()

    print("="*70)

if __name__ == "__main__":
    test_sgbm()
