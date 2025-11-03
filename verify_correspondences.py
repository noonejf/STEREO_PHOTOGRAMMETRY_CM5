#!/usr/bin/env python3
"""
Script para verificar si las correspondencias son correctas

Muestra información detallada sobre las correspondencias encontradas
"""

import cv2
import numpy as np
from pathlib import Path

def verify_correspondences():
    """Verificar correspondencias en última imagen procesada"""

    print("="*60)
    print("VERIFICACIÓN DE CORRESPONDENCIAS")
    print("="*60)
    print()

    # Leer imagen de correspondencias
    corr_path = Path("data/results/debug/15_correspondences.jpg")
    if not corr_path.exists():
        print("❌ No se encontró archivo de correspondencias")
        print("   Ejecuta primero el procesamiento con save_debug_images=True")
        return

    # Leer mapa de disparidad
    disp_raw_path = Path("data/results/debug/09_disparity_raw.png")
    disp_final_path = Path("data/results/debug/10_disparity_final.png")

    if not disp_final_path.exists():
        print("❌ No se encontró mapa de disparidad")
        return

    # Cargar disparidad (está en formato 8-bit normalizado)
    disp_img = cv2.imread(str(disp_final_path), cv2.IMREAD_GRAYSCALE)

    # Estadísticas
    nonzero_disp = disp_img[disp_img > 0]

    print("📊 ESTADÍSTICAS DE DISPARIDAD:")
    print(f"   Píxeles con disparidad > 0: {len(nonzero_disp):,} / {disp_img.size:,}")
    print(f"   Cobertura: {100*len(nonzero_disp)/disp_img.size:.1f}%")
    print()

    if len(nonzero_disp) == 0:
        print("❌ NO hay disparidad válida!")
        print("   Esto significa que NO se encontraron correspondencias.")
        print()
        print("💡 POSIBLES CAUSAS:")
        print("   1. Imágenes idénticas (sin diferencia estéreo)")
        print("   2. Parámetros SGBM muy restrictivos")
        print("   3. Imágenes muy diferentes (no hay overlap)")
        return

    # Analizar distribución
    print("📈 DISTRIBUCIÓN DE DISPARIDAD (valores normalizados 0-255):")
    percentiles = [0, 25, 50, 75, 100]
    for p in percentiles:
        val = np.percentile(nonzero_disp, p)
        print(f"   Percentil {p:3d}%: {val:6.2f}")
    print()

    # Verificar si hay estructura
    print("🔍 ANÁLISIS DE ESTRUCTURA:")

    # Contar regiones conectadas
    _, labels = cv2.connectedComponents((disp_img > 0).astype(np.uint8))
    num_regions = labels.max()
    print(f"   Regiones conectadas: {num_regions}")

    if num_regions < 5:
        print("   ⚠️ Muy pocas regiones (posible ruido aislado)")
    elif num_regions > 1000:
        print("   ⚠️ Demasiadas regiones (ruido excesivo)")
    else:
        print("   ✅ Número razonable de regiones")
    print()

    # Verificar rango dinámico
    dynamic_range = np.max(nonzero_disp) - np.min(nonzero_disp)
    print(f"📏 RANGO DINÁMICO:")
    print(f"   Min: {np.min(nonzero_disp):.2f}")
    print(f"   Max: {np.max(nonzero_disp):.2f}")
    print(f"   Rango: {dynamic_range:.2f}")
    print()

    if dynamic_range < 10:
        print("   ⚠️ Rango muy pequeño (<10)")
        print("      Casi no hay variación de profundidad")
        print("      Posibles causas:")
        print("      - Escena muy plana (todo a misma distancia)")
        print("      - Calibración con error de escala")
    elif dynamic_range > 200:
        print("   ✅ Buen rango dinámico")
        print("      Hay variación de profundidad significativa")
    else:
        print("   ⚠️ Rango moderado")
        print("      Hay algo de variación pero podría mejorar")
    print()

    # Verificar patrón espacial
    print("🗺️ PATRÓN ESPACIAL:")
    h, w = disp_img.shape

    # Dividir imagen en cuadrantes
    quadrants = {
        'Superior Izquierdo': disp_img[0:h//2, 0:w//2],
        'Superior Derecho': disp_img[0:h//2, w//2:w],
        'Inferior Izquierdo': disp_img[h//2:h, 0:w//2],
        'Inferior Derecho': disp_img[h//2:h, w//2:w]
    }

    for name, quad in quadrants.items():
        coverage = 100 * np.sum(quad > 0) / quad.size
        print(f"   {name:20s}: {coverage:5.1f}% cobertura")
    print()

    # Verificar si hay sesgo vertical (error de rectificación)
    print("🔧 VERIFICACIÓN DE RECTIFICACIÓN:")
    row_coverage = np.sum(disp_img > 0, axis=1) / w
    top_third = np.mean(row_coverage[:h//3])
    middle_third = np.mean(row_coverage[h//3:2*h//3])
    bottom_third = np.mean(row_coverage[2*h//3:])

    print(f"   Tercio superior: {100*top_third:.1f}% cobertura media")
    print(f"   Tercio medio:    {100*middle_third:.1f}% cobertura media")
    print(f"   Tercio inferior: {100*bottom_third:.1f}% cobertura media")
    print()

    if abs(top_third - bottom_third) > 0.3:
        print("   ⚠️ Gran diferencia vertical detectada")
        print("      Posible problema de rectificación")
    else:
        print("   ✅ Distribución vertical razonable")
    print()

    # INTERPRETACIÓN FINAL
    print("="*60)
    print("💡 INTERPRETACIÓN:")
    print("="*60)

    if len(nonzero_disp) < disp_img.size * 0.1:
        print("❌ MUY POCA DISPARIDAD (<10% cobertura)")
        print()
        print("Esto significa que:")
        print("1. El algoritmo NO puede encontrar correspondencias")
        print("2. Posibles causas:")
        print("   - Falta de textura en la escena")
        print("   - Parámetros SGBM demasiado estrictos")
        print("   - Imágenes mal rectificadas")
        print()
        print("SOLUCIÓN:")
        print("   python3 verify_correspondences.py")

    elif dynamic_range < 20 and len(nonzero_disp) > disp_img.size * 0.5:
        print("⚠️ BUENA COBERTURA pero POCO RANGO")
        print()
        print("Esto significa que:")
        print("1. El algoritmo ENCUENTRA correspondencias")
        print("2. PERO todas están a ~misma distancia")
        print("3. Posible causa: CALIBRACIÓN con error de escala")
        print()
        print("Tu escena tiene objetos a diferentes distancias (tu mano cerca, pared lejos)")
        print("pero el sistema los ve todos a ~misma distancia.")
        print()
        print("SOLUCIÓN:")
        print("   ✅ RE-CALIBRAR el sistema con imágenes a diferentes distancias")
        print("   📖 Ver: RESUMEN_FINAL.md - PASO 1")

    else:
        print("✅ DISPARIDAD RAZONABLE")
        print()
        print("El algoritmo está encontrando correspondencias.")
        print("Si las correspondencias visuales no tienen sentido,")
        print("el problema es de CALIBRACIÓN (matriz Q incorrecta).")
        print()
        print("PRÓXIMO PASO:")
        print("   ✅ RE-CALIBRAR para corregir escala de profundidad")

    print()
    print("="*60)

if __name__ == "__main__":
    verify_correspondences()
