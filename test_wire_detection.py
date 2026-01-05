#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Script de prueba para detección de cables en entorno oscuro
Utiliza el nuevo pipeline especializado para objetos finos
"""

import sys
import cv2
import numpy as np
from pathlib import Path
from config.camera_config import CameraConfig
from processing.stereo_processor import StereoProcessor
from utils.logger import get_logger

# Fix encoding en Windows
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')

logger = get_logger(__name__)

def test_wire_detection():
    """Probar detección de cables con el nuevo pipeline"""

    print("=" * 80)
    print("TEST: Detección de cable blanco en fondo oscuro")
    print("=" * 80)

    # Cargar imágenes de debug existentes
    debug_path = Path("data/results/debug")
    left_img_path = debug_path / "01_left_original.jpg"
    right_img_path = debug_path / "02_right_original.jpg"

    if not left_img_path.exists() or not right_img_path.exists():
        print(f"❌ ERROR: No se encuentran las imágenes de prueba en {debug_path}")
        print("   Por favor, ejecuta primero el procesamiento normal para generar las imágenes.")
        return

    print(f"\n📂 Cargando imágenes desde {debug_path}")
    left_img = cv2.imread(str(left_img_path))
    right_img = cv2.imread(str(right_img_path))

    print(f"   Left: {left_img.shape}")
    print(f"   Right: {right_img.shape}")

    # Cargar configuración de cámara
    print("\n🔧 Cargando configuración de cámara...")
    config = CameraConfig()

    if not config.is_calibrated():
        print("❌ ERROR: Sistema no calibrado. Ejecuta calibración primero.")
        return

    print("   ✓ Calibración cargada")

    # Crear procesador
    print("\n🔧 Inicializando procesador estéreo...")
    processor = StereoProcessor(config)
    print("   ✓ Procesador inicializado")

    # ==================================================================
    # TEST 1: Detección de máscara de objeto
    # ==================================================================
    print("\n" + "=" * 80)
    print("TEST 1: Detección de objeto (cable blanco)")
    print("=" * 80)

    left_mask = processor.detect_foreground_object_mask(left_img, debug_name="test_left")
    right_mask = processor.detect_foreground_object_mask(right_img, debug_name="test_right")

    print(f"\n📊 Resultados de detección:")
    print(f"   Left mask: {np.sum(left_mask)} píxeles ({100*np.sum(left_mask)/left_mask.size:.2f}%)")
    print(f"   Right mask: {np.sum(right_mask)} píxeles ({100*np.sum(right_mask)/right_mask.size:.2f}%)")

    combined_mask = (left_mask & right_mask)
    print(f"   Combined mask: {np.sum(combined_mask)} píxeles ({100*np.sum(combined_mask)/combined_mask.size:.2f}%)")

    # ==================================================================
    # TEST 2: Rectificación
    # ==================================================================
    print("\n" + "=" * 80)
    print("TEST 2: Rectificación de imágenes")
    print("=" * 80)

    left_rect, right_rect = processor.rectify_images(left_img, right_img)
    print(f"   ✓ Imágenes rectificadas: {left_rect.shape}")

    # ==================================================================
    # TEST 3: Disparidad SIN máscara (baseline)
    # ==================================================================
    print("\n" + "=" * 80)
    print("TEST 3: Disparidad SGBM ESTÁNDAR (sin máscara)")
    print("=" * 80)

    disparity_baseline = processor.compute_disparity(
        left_rect, right_rect,
        algorithm="SGBM",
        use_wls_filter=True,
        use_object_mask=False,
        use_edge_enhancement=False,
        save_debug=False
    )

    print(f"\n📊 Estadísticas SGBM estándar:")
    print(f"   Píxeles válidos: {disparity_baseline['valid_pixels']} ({100*disparity_baseline['valid_pixels']/(left_rect.shape[0]*left_rect.shape[1]):.2f}%)")
    print(f"   Disparidad: min={disparity_baseline['min_disparity']:.2f}, max={disparity_baseline['max_disparity']:.2f}, mean={disparity_baseline['mean_disparity']:.2f}")

    # Guardar resultado
    disp_baseline_vis = cv2.normalize(disparity_baseline['disparity_map'], None, 0, 255, cv2.NORM_MINMAX, dtype=cv2.CV_8U)
    disp_baseline_color = cv2.applyColorMap(disp_baseline_vis, cv2.COLORMAP_JET)
    disp_baseline_color[disparity_baseline['disparity_map'] <= 0] = [0, 0, 0]
    cv2.imwrite(str(debug_path / "test_01_sgbm_standard.png"), disp_baseline_color)

    # ==================================================================
    # TEST 4: Disparidad CON máscara
    # ==================================================================
    print("\n" + "=" * 80)
    print("TEST 4: Disparidad SGBM CON MÁSCARA DE OBJETO")
    print("=" * 80)

    disparity_masked = processor.compute_disparity(
        left_rect, right_rect,
        algorithm="SGBM",
        use_wls_filter=True,
        use_object_mask=True,  # ✓ HABILITAR MÁSCARA
        use_edge_enhancement=False,
        save_debug=True  # Guardar máscaras intermedias
    )

    print(f"\n📊 Estadísticas SGBM con máscara:")
    print(f"   Píxeles válidos: {disparity_masked['valid_pixels']} ({100*disparity_masked['valid_pixels']/(left_rect.shape[0]*left_rect.shape[1]):.2f}%)")
    print(f"   Disparidad: min={disparity_masked['min_disparity']:.2f}, max={disparity_masked['max_disparity']:.2f}, mean={disparity_masked['mean_disparity']:.2f}")

    # Guardar resultado
    disp_masked_vis = cv2.normalize(disparity_masked['disparity_map'], None, 0, 255, cv2.NORM_MINMAX, dtype=cv2.CV_8U)
    disp_masked_color = cv2.applyColorMap(disp_masked_vis, cv2.COLORMAP_JET)
    disp_masked_color[disparity_masked['disparity_map'] <= 0] = [0, 0, 0]
    cv2.imwrite(str(debug_path / "test_02_sgbm_masked.png"), disp_masked_color)

    # ==================================================================
    # TEST 5: Disparidad SGBM_FINE (optimizado para cables)
    # ==================================================================
    print("\n" + "=" * 80)
    print("TEST 5: Disparidad SGBM_FINE (optimizado para cables)")
    print("=" * 80)

    disparity_fine = processor.compute_disparity(
        left_rect, right_rect,
        algorithm="SGBM_FINE",  # ✓ ALGORITMO ESPECIALIZADO
        use_wls_filter=True,
        use_object_mask=True,  # ✓ HABILITAR MÁSCARA
        use_edge_enhancement=False,
        save_debug=False
    )

    print(f"\n📊 Estadísticas SGBM_FINE:")
    print(f"   Píxeles válidos: {disparity_fine['valid_pixels']} ({100*disparity_fine['valid_pixels']/(left_rect.shape[0]*left_rect.shape[1]):.2f}%)")
    print(f"   Disparidad: min={disparity_fine['min_disparity']:.2f}, max={disparity_fine['max_disparity']:.2f}, mean={disparity_fine['mean_disparity']:.2f}")

    # Guardar resultado
    disp_fine_vis = cv2.normalize(disparity_fine['disparity_map'], None, 0, 255, cv2.NORM_MINMAX, dtype=cv2.CV_8U)
    disp_fine_color = cv2.applyColorMap(disp_fine_vis, cv2.COLORMAP_JET)
    disp_fine_color[disparity_fine['disparity_map'] <= 0] = [0, 0, 0]
    cv2.imwrite(str(debug_path / "test_03_sgbm_fine.png"), disp_fine_color)

    # ==================================================================
    # TEST 6: SGBM_FINE + Realce de bordes
    # ==================================================================
    print("\n" + "=" * 80)
    print("TEST 6: SGBM_FINE + REALCE DE BORDES")
    print("=" * 80)

    disparity_fine_edges = processor.compute_disparity(
        left_rect, right_rect,
        algorithm="SGBM_FINE",
        use_wls_filter=True,
        use_object_mask=True,
        use_edge_enhancement=True,  # ✓ REALZAR BORDES
        save_debug=False
    )

    print(f"\n📊 Estadísticas SGBM_FINE + bordes:")
    print(f"   Píxeles válidos: {disparity_fine_edges['valid_pixels']} ({100*disparity_fine_edges['valid_pixels']/(left_rect.shape[0]*left_rect.shape[1]):.2f}%)")
    print(f"   Disparidad: min={disparity_fine_edges['min_disparity']:.2f}, max={disparity_fine_edges['max_disparity']:.2f}, mean={disparity_fine_edges['mean_disparity']:.2f}")

    # Guardar resultado
    disp_fine_edges_vis = cv2.normalize(disparity_fine_edges['disparity_map'], None, 0, 255, cv2.NORM_MINMAX, dtype=cv2.CV_8U)
    disp_fine_edges_color = cv2.applyColorMap(disp_fine_edges_vis, cv2.COLORMAP_JET)
    disp_fine_edges_color[disparity_fine_edges['disparity_map'] <= 0] = [0, 0, 0]
    cv2.imwrite(str(debug_path / "test_04_sgbm_fine_edges.png"), disp_fine_edges_color)

    # ==================================================================
    # Resumen de resultados
    # ==================================================================
    print("\n" + "=" * 80)
    print("RESUMEN DE RESULTADOS")
    print("=" * 80)

    tests = [
        ("SGBM Estándar", disparity_baseline),
        ("SGBM + Máscara", disparity_masked),
        ("SGBM_FINE + Máscara", disparity_fine),
        ("SGBM_FINE + Máscara + Bordes", disparity_fine_edges)
    ]

    print(f"\n{'Configuración':<35} {'Píxeles válidos':<20} {'Disparidad media':<20}")
    print("-" * 80)
    for name, result in tests:
        valid_pct = 100 * result['valid_pixels'] / (left_rect.shape[0] * left_rect.shape[1])
        print(f"{name:<35} {result['valid_pixels']:>10} ({valid_pct:>5.2f}%) {result['mean_disparity']:>10.2f} px")

    print("\n" + "=" * 80)
    print("ARCHIVOS GENERADOS:")
    print("=" * 80)
    print(f"   {debug_path / 'test_01_sgbm_standard.png'}")
    print(f"   {debug_path / 'test_02_sgbm_masked.png'}")
    print(f"   {debug_path / 'test_03_sgbm_fine.png'}")
    print(f"   {debug_path / 'test_04_sgbm_fine_edges.png'}")
    print(f"   {debug_path / 'test_left_object_mask.png'}")
    print(f"   {debug_path / 'test_right_object_mask.png'}")
    print(f"   {debug_path / 'test_left_object_overlay.jpg'}")
    print(f"   {debug_path / 'test_right_object_overlay.jpg'}")
    print(f"   {debug_path / 'left_object_mask.png'}")
    print(f"   {debug_path / 'right_object_mask.png'}")
    print(f"   {debug_path / 'left_object_overlay.jpg'}")
    print(f"   {debug_path / 'right_object_overlay.jpg'}")

    print("\n✅ TEST COMPLETADO")
    print("\n💡 RECOMENDACIONES:")
    print("   1. Revisa las máscaras de objeto (*_object_mask.png) - deben capturar el cable")
    print("   2. Compara los mapas de disparidad (test_01 a test_04)")
    print("   3. test_03 o test_04 deberían dar mejores resultados para el cable")
    print("   4. Si la máscara no captura bien el cable, ajusta umbrales en detect_foreground_object_mask()")

if __name__ == "__main__":
    test_wire_detection()
