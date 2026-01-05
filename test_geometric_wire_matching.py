#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
TEST - Geometric Wire Matching
Matching de cables basado en geometría de curvas (no apariencia visual)
"""

import sys
import cv2
import numpy as np
from pathlib import Path

if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')

from config.camera_config import CameraConfig
from processing.stereo_processor import StereoProcessor
from processing.geometric_wire_matcher import GeometricWireMatcher
from processing.point_cloud_generator import PointCloudExporter


def main():
    """Probar matching geométrico con imágenes reales del cable"""

    print("="*80)
    print("TEST - GEOMETRIC WIRE MATCHING")
    print("="*80)
    print("\nEstrategia: Matching basado en GEOMETRÍA, no en apariencia visual")
    print("  1. Extraer esqueleto geométrico del cable en cada imagen")
    print("  2. Ordenar puntos siguiendo el FLUJO del cable")
    print("  3. Hacer matching punto a punto usando restricción epipolar")
    print("  4. Calcular disparidad y reconstruir 3D")

    # ========== PASO 1: Cargar configuración ==========
    print("\n[1/7] Cargando configuración del sistema...")

    try:
        config = CameraConfig()

        if not config.is_calibrated():
            print("❌ ERROR: Sistema no calibrado!")
            return

        print("✓ Sistema calibrado correctamente")

    except Exception as e:
        print(f"❌ ERROR cargando configuración: {e}")
        return

    # ========== PASO 2: Cargar imágenes ==========
    print("\n[2/7] Cargando imágenes del cable...")

    debug_path = Path("data/results/debug")
    left_path = debug_path / "01_left_original.jpg"
    right_path = debug_path / "02_right_original.jpg"

    if not left_path.exists() or not right_path.exists():
        print(f"❌ ERROR: No se encuentran imágenes en {debug_path}")
        return

    left_img = cv2.imread(str(left_path))
    right_img = cv2.imread(str(right_path))

    print(f"✓ Imágenes cargadas: {left_img.shape}")

    # ========== PASO 3: Cargar máscaras ==========
    print("\n[3/7] Cargando máscaras del cable...")

    mask_left_path = debug_path / "cable_mask_left.png"
    mask_right_path = debug_path / "cable_mask_right.png"

    if not mask_left_path.exists() or not mask_right_path.exists():
        print(f"❌ ERROR: No se encontraron máscaras del cable!")
        print(f"\n⚠️ Ejecuta primero el tuner de detección para generar máscaras")
        return

    mask_left = cv2.imread(str(mask_left_path), cv2.IMREAD_GRAYSCALE)
    mask_right = cv2.imread(str(mask_right_path), cv2.IMREAD_GRAYSCALE)

    pixels_left = np.sum(mask_left > 0)
    pixels_right = np.sum(mask_right > 0)

    print(f"✓ Máscaras cargadas:")
    print(f"  - Left:  {pixels_left} píxeles")
    print(f"  - Right: {pixels_right} píxeles")

    # ========== PASO 4: Rectificar imágenes Y MÁSCARAS ==========
    print("\n[4/7] Rectificando imágenes Y máscaras...")

    try:
        processor = StereoProcessor(config)
        left_rect, right_rect = processor.rectify_images(left_img, right_img)
        print(f"✓ Imágenes rectificadas: {left_rect.shape}")

        # IMPORTANTE: Rectificar las máscaras también
        print("  Rectificando máscaras...")

        # Convertir máscaras a 3 canales para rectificación
        mask_left_3ch = cv2.cvtColor(mask_left, cv2.COLOR_GRAY2BGR)
        mask_right_3ch = cv2.cvtColor(mask_right, cv2.COLOR_GRAY2BGR)

        # Rectificar máscaras
        mask_left_rect, mask_right_rect = processor.rectify_images(mask_left_3ch, mask_right_3ch)

        # Convertir de vuelta a escala de grises
        mask_left_rect = cv2.cvtColor(mask_left_rect, cv2.COLOR_BGR2GRAY)
        mask_right_rect = cv2.cvtColor(mask_right_rect, cv2.COLOR_BGR2GRAY)

        # Binarizar (la interpolación puede haber creado valores intermedios)
        _, mask_left_rect = cv2.threshold(mask_left_rect, 127, 255, cv2.THRESH_BINARY)
        _, mask_right_rect = cv2.threshold(mask_right_rect, 127, 255, cv2.THRESH_BINARY)

        print(f"✓ Máscaras rectificadas:")
        print(f"  - Left:  {np.sum(mask_left_rect > 0)} píxeles")
        print(f"  - Right: {np.sum(mask_right_rect > 0)} píxeles")

        # Reemplazar máscaras originales con rectificadas
        mask_left = mask_left_rect
        mask_right = mask_right_rect

    except Exception as e:
        print(f"❌ ERROR en rectificación: {e}")
        import traceback
        traceback.print_exc()
        return

    # ========== PASO 5: Matching geométrico ==========
    print("\n[5/7] Ejecutando matching GEOMÉTRICO...")
    print("\nParámetros:")
    print("  - Método: Extracción de esqueleto + ordenamiento de curva")
    print("  - Sample spacing: 3 píxeles (denso)")
    print("  - Matching: Por posición en curva (no por apariencia)")
    print("  - Restricción: Epipolar (misma fila Y)")

    try:
        matcher = GeometricWireMatcher()

        match_result = matcher.match_wire_curves(
            left_rect, right_rect,
            mask_left, mask_right,
            sample_spacing=10,  # Spacing más grande para reducir número de puntos
            save_debug=True
        )

        if not match_result['success']:
            print(f"❌ ERROR en matching: {match_result.get('error', 'Unknown')}")
            return

        print(f"\n✓ Matching geométrico completado!")
        print(f"\n📊 Resultados:")
        print(f"  - Puntos en curva LEFT: {len(match_result['left_curve'])}")
        print(f"  - Puntos en curva RIGHT: {len(match_result['right_curve'])}")
        print(f"  - Matches geométricos: {match_result['num_matches']}")
        print(f"  - Disparidad: {match_result['min_disparity']:.1f} - {match_result['max_disparity']:.1f} px")
        print(f"  - Disparidad media: {match_result['mean_disparity']:.1f} px")
        print(f"  - Std disparidad: {match_result['std_disparity']:.1f} px")

    except Exception as e:
        print(f"❌ ERROR en matching geométrico: {e}")
        import traceback
        traceback.print_exc()
        return

    # ========== PASO 6: Convertir a profundidad ==========
    print("\n[6/7] Convirtiendo disparidad a profundidad...")

    try:
        depth_result = processor.disparity_to_depth(match_result['disparity_map'])

        print(f"✓ Profundidad calculada:")
        print(f"  - Rango: {depth_result['min_depth']:.2f}m - {depth_result['max_depth']:.2f}m")
        print(f"  - Media: {depth_result['mean_depth']:.2f}m")
        print(f"  - Píxeles válidos: {depth_result['valid_pixels']}")

    except Exception as e:
        print(f"❌ ERROR calculando profundidad: {e}")
        import traceback
        traceback.print_exc()
        return

    # ========== PASO 7: Generar nube de puntos 3D ==========
    print("\n[7/7] Generando nube de puntos 3D...")

    try:
        point_cloud_result = processor.generate_point_cloud(
            left_rect,
            match_result['disparity_map'],
            depth_result['depth_map'],
            match_result['confidence_map'],
            min_confidence=0.5
        )

        if point_cloud_result['num_points'] == 0:
            print("❌ ERROR: No se generaron puntos 3D válidos!")
            return

        print(f"✓ Nube de puntos generada:")
        print(f"  - Número de puntos: {point_cloud_result['num_points']}")
        print(f"  - Densidad: {point_cloud_result['density']:.4f}")
        print(f"\n📊 Bounds 3D:")
        print(f"  X: [{point_cloud_result['bounds']['x_min']:.3f}, {point_cloud_result['bounds']['x_max']:.3f}] m")
        print(f"  Y: [{point_cloud_result['bounds']['y_min']:.3f}, {point_cloud_result['bounds']['y_max']:.3f}] m")
        print(f"  Z: [{point_cloud_result['bounds']['z_min']:.3f}, {point_cloud_result['bounds']['z_max']:.3f}] m")

        # Exportar nube de puntos
        print("\n[8/8] Exportando nube de puntos...")

        generator = PointCloudExporter()
        output_file = Path("data/results/wire_cable_geometric.ply")

        # Usar color basado en el flujo de la curva (gradiente)
        num_points = point_cloud_result['num_points']
        colors = np.zeros((num_points, 3), dtype=np.float32)

        # Color gradiente de rojo (inicio) a azul (fin) para mostrar flujo
        for i in range(num_points):
            ratio = i / num_points
            # Rojo -> Amarillo -> Verde -> Cian -> Azul
            colors[i] = [1.0 - ratio, ratio, ratio * 0.5]

        export_result = generator.export_point_cloud(
            points=point_cloud_result['points'],
            colors=colors,
            output_file=str(output_file),
            format_type='ply'
        )

        if export_result['success']:
            print(f"✓ Nube de puntos exportada:")
            print(f"  - Archivo: {output_file}")
            print(f"  - Tamaño: {export_result.get('file_size_mb', 0):.2f} MB")
        else:
            print(f"❌ ERROR exportando: {export_result.get('error', 'Unknown')}")

    except Exception as e:
        print(f"❌ ERROR generando nube de puntos: {e}")
        import traceback
        traceback.print_exc()

    # ========== RESUMEN FINAL ==========
    print("\n" + "="*80)
    print("✅ TEST COMPLETADO")
    print("="*80)
    print("\n📂 Archivos generados:")
    print(f"  - Nube de puntos: data/results/wire_cable_geometric.ply")
    print(f"  - Debug matching:  data/results/debug/geometric_matcher/")
    print(f"  - Curvas con flujo: *_curve_flow.jpg (rojo=inicio, azul=fin)")
    print("\n💡 Abre el PLY con MeshLab/CloudCompare para ver el cable 3D")
    print("   El color del cable muestra el FLUJO geométrico (dirección)")


if __name__ == "__main__":
    main()
