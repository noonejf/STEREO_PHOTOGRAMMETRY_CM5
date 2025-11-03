#!/usr/bin/env python3
"""
Test para verificar qué cámara física es cuál

Este script captura una imagen de CAM0 y CAM1 por separado
para que el usuario pueda verificar cuál está a la izquierda y cuál a la derecha
"""

import subprocess
import sys
from pathlib import Path
from datetime import datetime

def capture_test_image(camera_id, output_file):
    """Capturar imagen de prueba de una cámara específica"""

    print(f"📷 Capturando CAM{camera_id}...")

    cmd = [
        "libcamera-jpeg",
        "--camera", str(camera_id),
        "--output", str(output_file),
        "-t", "2000",  # 2 segundos
        "--width", "1920",
        "--height", "1440",
        "--immediate"  # Captura inmediata sin preview
    ]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)

        if result.returncode == 0:
            print(f"   ✅ Captura exitosa: {output_file}")
            return True
        else:
            print(f"   ❌ Error: {result.stderr}")
            return False

    except subprocess.TimeoutExpired:
        print(f"   ❌ Timeout capturando CAM{camera_id}")
        return False
    except Exception as e:
        print(f"   ❌ Error: {e}")
        return False

def main():
    print("="*70)
    print("TEST DE IDENTIDAD DE CÁMARAS")
    print("="*70)
    print()
    print("Este script capturará una imagen de cada cámara por separado.")
    print("INSTRUCCIONES:")
    print("  1. Coloca un objeto distintivo frente a las cámaras")
    print("  2. El script capturará CAM0 y CAM1 por separado")
    print("  3. Revisa las imágenes para confirmar cuál es cuál")
    print()
    print("IMPORTANTE: Ponte frente a las cámaras y levanta tu MANO IZQUIERDA")
    print("            Así podrás identificar fácilmente qué cámara es cuál.")
    print()
    print("Capturando en 3 segundos...")
    print()

    # Crear directorio de salida
    output_dir = Path("data/results/debug/camera_identity_test")
    output_dir.mkdir(parents=True, exist_ok=True)

    # Capturar CAM0
    cam0_file = output_dir / "CAM0_test.jpg"
    success_cam0 = capture_test_image(0, cam0_file)

    print()

    # Capturar CAM1
    cam1_file = output_dir / "CAM1_test.jpg"
    success_cam1 = capture_test_image(1, cam1_file)

    print()
    print("="*70)
    print("RESULTADOS")
    print("="*70)
    print()

    if success_cam0 and success_cam1:
        print("✅ Ambas cámaras capturaron exitosamente")
        print()
        print(f"📁 Archivos guardados en: {output_dir}")
        print(f"   CAM0: {cam0_file}")
        print(f"   CAM1: {cam1_file}")
        print()
        print("🔍 AHORA VERIFICA:")
        print("   1. Abre ambas imágenes")
        print("   2. Si levantaste tu MANO IZQUIERDA:")
        print("      - En CAM0 debería aparecer a la IZQUIERDA de la imagen")
        print("      - En CAM1 debería aparecer a la DERECHA de la imagen")
        print()
        print("   3. Si es al revés (CAM0 muestra mano a la derecha):")
        print("      → Las cámaras están INVERTIDAS físicamente")
        print()
        print("ALTERNATIVA: Si no levantaste la mano, simplemente verifica:")
        print("   - ¿CAM0 ve desde la IZQUIERDA? (punto de vista izquierdo)")
        print("   - ¿CAM1 ve desde la DERECHA? (punto de vista derecho)")
        print()
        print("Si CAM0 ve desde la derecha y CAM1 desde la izquierda:")
        print("   → Las cámaras están FÍSICAMENTE AL REVÉS")
        print()

    else:
        print("❌ Hubo errores capturando las imágenes")
        print("   Verifica que las cámaras estén conectadas correctamente")

    print("="*70)

if __name__ == "__main__":
    main()
