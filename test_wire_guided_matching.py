#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
TEST - Wire Guided Matching
Probar sistema completo de matching guiado para cables
"""

import sys
import cv2
import numpy as np
from pathlib import Path

if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')

from config.camera_config import CameraConfig
from processing.stereo_processor import StereoProcessor
from processing.point_cloud_generator import PointCloudExporter


def main():
    """Probar matching guiado con imágenes reales del cable"""

    print("="*80)
    print("TEST - WIRE GUIDED MATCHING")
    print("="*80)

    # ========== PASO 1: Cargar configuración y verificar calibración ==========
    print("\n[1/6] Cargando configuración del sistema...")

    try:
        config = CameraConfig()

        if not config.is_calibrated():
            print("❌ ERROR: Sistema no calibrado!")
            print("   Ejecuta calibración primero con: python3 main.py")
            return

        print("✓ Sistema calibrado correctamente")

    except Exception as e:
        print(f"❌ ERROR cargando configuración: {e}")
        return

    # ========== PASO 2: Cargar imágenes del cable ==========
    print("\n[2/6] Cargando imágenes del cable...")

    # Buscar imágenes más recientes en debug
    debug_path = Path("data/results/debug")
    left_path = debug_path / "01_left_original.jpg"
    right_path = debug_path / "02_right_original.jpg"

    if not left_path.exists() or not right_path.exists():
        print(f"❌ ERROR: No se encuentran imágenes en {debug_path}")
        print("   Archivos esperados:")
        print(f"     - {left_path}")
        print(f"     - {right_path}")
        print("\n   Ejecuta primero el procesamiento 3D desde la GUI")
        return

    left_img = cv2.imread(str(left_path))
    right_img = cv2.imread(str(right_path))

    print(f"✓ Imágenes cargadas:")
    print(f"  - Left:  {left_img.shape}")
    print(f"  - Right: {right_img.shape}")

    # ========== PASO 3: Cargar máscaras del cable generadas en GUI ==========
    print("\n[3/6] Cargando máscaras del cable...")

    mask_left_path = Path("data/results/debug/cable_mask_left.png")
    mask_right_path = Path("data/results/debug/cable_mask_right.png")

    if not mask_left_path.exists() or not mask_right_path.exists():
        print(f"❌ ERROR: No se encontraron máscaras del cable!")
        print(f"\n⚠️ IMPORTANTE: Primero debes generar las máscaras del cable:")
        print(f"   1. Ejecuta: python main.py")
        print(f"   2. Carga las imágenes del cable")
        print(f"   3. Click en '🔧 Configurar Filtro de Cable'")
        print(f"   4. Ajusta los parámetros en el tuner hasta que SOLO se vea el cable")
        print(f"   5. Click en '✓ Aplicar y Continuar Procesamiento'")
        print(f"\n   Las máscaras se guardarán automáticamente en:")
        print(f"     - {mask_left_path}")
        print(f"     - {mask_right_path}")
        print(f"\n   Luego vuelve a ejecutar este test.")
        return

    # Cargar máscaras
    mask_left = cv2.imread(str(mask_left_path), cv2.IMREAD_GRAYSCALE)
    mask_right = cv2.imread(str(mask_right_path), cv2.IMREAD_GRAYSCALE)

    # Estadísticas
    pixels_left = np.sum(mask_left > 0)
    pixels_right = np.sum(mask_right > 0)
    percent_left = 100 * pixels_left / mask_left.size
    percent_right = 100 * pixels_right / mask_right.size

    print(f"✓ Máscaras del cable cargadas:")
    print(f"  - Left:  {pixels_left} píxeles ({percent_left:.2f}%)")
    print(f"  - Right: {pixels_right} píxeles ({percent_right:.2f}%)")

    if pixels_left == 0 or pixels_right == 0:
        print("❌ ERROR: Las máscaras están vacías!")
        print("   Asegúrate de haber ajustado bien el filtro en el tuner.")
        return

    # ========== PASO 4: Inicializar procesador estéreo ==========
    print("\n[4/6] Inicializando procesador estéreo...")

    try:
        processor = StereoProcessor(config)
        print("✓ Procesador estéreo inicializado")
    except Exception as e:
        print(f"❌ ERROR inicializando procesador: {e}")
        return

    # ========== PASO 5: Rectificar imágenes ==========
    print("\n[5/6] Rectificando imágenes...")

    try:
        left_rect, right_rect = processor.rectify_images(left_img, right_img)
        print(f"✓ Imágenes rectificadas: {left_rect.shape}")

        # Guardar imágenes rectificadas
        output_path = Path("data/results/debug/wire_matcher")
        output_path.mkdir(parents=True, exist_ok=True)

        cv2.imwrite(str(output_path / "00_left_rectified.jpg"), left_rect)
        cv2.imwrite(str(output_path / "00_right_rectified.jpg"), right_rect)
        print(f"  Guardadas en: {output_path}")

    except Exception as e:
        print(f"❌ ERROR en rectificación: {e}")
        import traceback
        traceback.print_exc()
        return

    # ========== PASO 6: Ejecutar matching guiado ==========
    print("\n[6/6] Ejecutando matching guiado para cable...")
    print("\nParámetros:")
    print("  - Patch size: 11x11 píxeles (contexto medio)")
    print("  - Sample step: 5 píxeles (reducido para velocidad)")
    print("  - NCC threshold: 0.70 (más estricto)")
    print("  - Max disparity: 150 píxeles (REDUCIDO - objeto cercano)")
    print("  - Modo: INTENSITY-BASED (sin gradientes)")
    print("  - Filtro de outliers global: ACTIVADO")

    try:
        # Usar máscara left (la rectificación no cambia mucho la máscara)
        disparity_result = processor.compute_disparity_wire_guided(
            left_rect, right_rect,
            wire_mask=mask_left,
            patch_size=11,        # Contexto medio
            sample_step=5,        # Reducido
            ncc_threshold=0.70,   # Más estricto
            max_disparity=150,    # REDUCIDO
            save_debug=True
        )

        if not disparity_result['success']:
            print(f"❌ ERROR en matching: {disparity_result.get('error', 'Unknown')}")
            return

        print("\n✓ Matching completado exitosamente!")
        print(f"\n📊 Resultados:")
        print(f"  - Matches válidos: {disparity_result['num_matches']}")
        print(f"  - Match ratio: {disparity_result['match_ratio']*100:.1f}%")
        print(f"  - Disparidad: {disparity_result['min_disparity']:.1f} - {disparity_result['max_disparity']:.1f} px")
        print(f"  - Disparidad media: {disparity_result['mean_disparity']:.1f} px")
        print(f"  - Score NCC medio: {disparity_result['mean_ncc_score']:.3f}")

    except Exception as e:
        print(f"❌ ERROR en matching guiado: {e}")
        import traceback
        traceback.print_exc()
        return

    # ========== PASO 7: Convertir a profundidad ==========
    print("\n[7/8] Convirtiendo disparidad a profundidad...")

    try:
        depth_result = processor.disparity_to_depth(disparity_result['disparity_map'])

        print(f"✓ Profundidad calculada:")
        print(f"  - Rango: {depth_result['min_depth']:.2f}m - {depth_result['max_depth']:.2f}m")
        print(f"  - Media: {depth_result['mean_depth']:.2f}m")
        print(f"  - Píxeles válidos: {depth_result['valid_pixels']}")

    except Exception as e:
        print(f"❌ ERROR calculando profundidad: {e}")
        import traceback
        traceback.print_exc()
        return

    # ========== PASO 8: Generar nube de puntos 3D ==========
    print("\n[8/8] Generando nube de puntos 3D...")

    try:
        point_cloud_result = processor.generate_point_cloud(
            left_rect,
            disparity_result['disparity_map'],
            depth_result['depth_map'],
            disparity_result['confidence_map'],
            min_confidence=0.5  # Usar scores NCC como confianza
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

    except Exception as e:
        print(f"❌ ERROR generando nube de puntos: {e}")
        import traceback
        traceback.print_exc()
        return

    # ========== PASO 9: Exportar nube de puntos ==========
    print("\n[9/9] Exportando nube de puntos...")

    try:
        generator = PointCloudExporter()

        output_file = Path("data/results/wire_cable_guided.ply")

        # Extraer colores de imagen rectificada SOLO para puntos válidos en la nube
        # Los puntos de point_cloud_result ya están filtrados
        num_points = point_cloud_result['num_points']
        colors = np.zeros((num_points, 3), dtype=np.float32)

        # Necesitamos extraer colores de las posiciones originales (antes de filtrar)
        # Usaremos la imagen rectificada para obtener colores
        points_3d = point_cloud_result['points']

        # Para cada punto 3D válido, extraer color de la imagen
        # Pero necesitamos las coordenadas 2D... esto es complicado
        # WORKAROUND: Usar color blanco para todos los puntos del cable
        colors[:] = [1.0, 1.0, 1.0]  # Blanco (como el cable real)

        export_result = generator.export_point_cloud(
            points=point_cloud_result['points'],
            colors=colors,
            output_file=str(output_file),
            format_type='ply'
        )

        if export_result['success']:
            print(f"✓ Nube de puntos exportada:")
            print(f"  - Archivo: {export_result['output_file']}")
            print(f"  - Tamaño: {export_result['file_size_mb']:.2f} MB")
        else:
            print(f"❌ ERROR exportando: {export_result.get('error', 'Unknown')}")

    except Exception as e:
        print(f"❌ ERROR en exportación: {e}")
        import traceback
        traceback.print_exc()

    # ========== RESUMEN FINAL ==========
    print("\n" + "="*80)
    print("✅ TEST COMPLETADO")
    print("="*80)
    print("\n📂 Archivos generados:")
    print(f"  - Nube de puntos: data/results/wire_cable_guided.ply")
    print(f"  - Debug matching:  data/results/debug/wire_matcher/")
    print(f"  - Debug detección: data/results/debug/wire_final/")
    print("\n💡 Abre el archivo PLY con MeshLab o CloudCompare para visualizar el cable en 3D")


if __name__ == "__main__":
    main()
