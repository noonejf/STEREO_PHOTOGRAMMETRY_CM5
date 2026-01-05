#!/usr/bin/env python3
"""
Script de prueba para la integración del SmartWireTracker.
Prueba el flujo completo: máscaras → endpoints → tracking → visualización
"""

import cv2
import numpy as np
from pathlib import Path

# Importar componentes
from config.camera_config import CameraConfig
from processing.stereo_processor import StereoProcessor


def test_wire_tracker_integration():
    """Prueba la integración completa del wire tracker."""

    print("="*70)
    print("TEST DE INTEGRACIÓN - SMART WIRE TRACKER")
    print("="*70)

    # Verificar que existan máscaras de prueba
    mask_left_path = Path("data/results/debug/cable_mask_left.png")
    mask_right_path = Path("data/results/debug/cable_mask_right.png")

    if not mask_left_path.exists() or not mask_right_path.exists():
        print("❌ ERROR: No se encontraron máscaras de prueba")
        print(f"   Esperadas en: {mask_left_path.parent}")
        print("\n   Ejecuta primero el ProcessingDialog y crea las máscaras manualmente.")
        return False

    print(f"✓ Máscaras encontradas:")
    print(f"  - {mask_left_path}")
    print(f"  - {mask_right_path}")

    # Cargar máscaras
    mask_left = cv2.imread(str(mask_left_path), cv2.IMREAD_GRAYSCALE)
    mask_right = cv2.imread(str(mask_right_path), cv2.IMREAD_GRAYSCALE)

    if mask_left is None or mask_right is None:
        print("❌ ERROR: No se pudieron cargar las máscaras")
        return False

    print(f"✓ Máscaras cargadas:")
    print(f"  LEFT: {mask_left.shape}, píxeles blancos: {np.sum(mask_left > 0)}")
    print(f"  RIGHT: {mask_right.shape}, píxeles blancos: {np.sum(mask_right > 0)}")

    # Cargar configuración de cámara
    try:
        camera_config = CameraConfig()
        if not camera_config.is_calibrated():
            print("⚠️ WARNING: Sistema no calibrado")
            print("   Continuando de todas formas para probar el wire tracker...")
            # Crear configuración temporal para testing
            camera_config.calibration_data = {
                'K1': np.eye(3),
                'K2': np.eye(3),
                'D1': np.zeros(5),
                'D2': np.zeros(5),
                'R': np.eye(3),
                'T': np.array([[0.1], [0], [0]]),
                'rectification_maps': None
            }
    except Exception as e:
        print(f"⚠️ WARNING: Error cargando config: {e}")
        print("   Usando configuración temporal...")
        # Crear mock config
        class MockConfig:
            def __init__(self):
                self.calibration_data = {
                    'K1': np.eye(3),
                    'K2': np.eye(3),
                    'D1': np.zeros(5),
                    'D2': np.zeros(5),
                    'R': np.eye(3),
                    'T': np.array([[0.1], [0], [0]]),
                    'rectification_maps': None
                }
            def is_calibrated(self):
                return True

        camera_config = MockConfig()

    print("\n" + "="*70)
    print("EJECUTANDO WIRE TRACKER...")
    print("="*70)

    try:
        # Crear procesador
        processor = StereoProcessor(camera_config)

        # Procesar máscaras
        result = processor.process_wire_masks(
            mask_left,
            mask_right,
            save_debug=True
        )

        # Verificar resultados
        print("\n" + "="*70)
        print("RESULTADOS")
        print("="*70)

        if result['success']:
            print("✅ WIRE TRACKING EXITOSO\n")

            print("LEFT:")
            print(f"  Start: {result['left']['start']}")
            print(f"  End: {result['left']['end']}")
            print(f"  Path: {len(result['left']['path'])} puntos")
            print(f"  Cobertura: {result['left']['coverage']*100:.1f}%")
            print(f"  Success: {result['left']['success']}")

            print("\nRIGHT:")
            print(f"  Start: {result['right']['start']}")
            print(f"  End: {result['right']['end']}")
            print(f"  Path: {len(result['right']['path'])} puntos")
            print(f"  Cobertura: {result['right']['coverage']*100:.1f}%")
            print(f"  Success: {result['right']['success']}")

            print("\n" + "="*70)
            print("IMÁGENES DE DEBUG GENERADAS")
            print("="*70)

            debug_dir = Path("data/results/debug")
            debug_files = [
                "endpoints_left.png",
                "endpoints_right.png",
                "wire_path_left.png",
                "wire_path_right.png"
            ]

            for filename in debug_files:
                filepath = debug_dir / filename
                if filepath.exists():
                    print(f"  ✓ {filepath}")
                else:
                    print(f"  ⚠️ {filepath} (no generada)")

            print("\n✅ TEST COMPLETADO EXITOSAMENTE")
            return True

        else:
            print("❌ WIRE TRACKING FALLÓ\n")
            if 'error' in result:
                print(f"Error: {result['error']}")

            print("\n❌ TEST FALLÓ")
            return False

    except Exception as e:
        print(f"\n❌ ERROR DURANTE TEST: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = test_wire_tracker_integration()
    exit(0 if success else 1)
