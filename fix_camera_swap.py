#!/usr/bin/env python3
"""
Script para arreglar el intercambio de cámaras LEFT/RIGHT

Las cámaras están físicamente invertidas. Este script:
1. Intercambia las imágenes left ↔ right en capturas existentes
2. Marca el sistema para que siempre intercambie en el futuro
"""

import json
from pathlib import Path
import shutil

def fix_camera_swap():
    """Arreglar intercambio de cámaras"""

    print("="*60)
    print("ARREGLANDO INTERCAMBIO DE CÁMARAS")
    print("="*60)
    print()

    # 1. Intercambiar última captura
    captures_dir = Path("data/captures")
    sessions = sorted(captures_dir.glob("stereo_*"))

    if sessions:
        latest = sessions[-1]
        print(f"📁 Última sesión: {latest.name}")

        left_path = latest / "left.jpg"
        right_path = latest / "right.jpg"

        if left_path.exists() and right_path.exists():
            temp_path = latest / "temp_swap.jpg"

            # Intercambiar
            shutil.move(str(left_path), str(temp_path))
            shutil.move(str(right_path), str(left_path))
            shutil.move(str(temp_path), str(right_path))

            print(f"✅ Imágenes intercambiadas:")
            print(f"   - left.jpg ↔ right.jpg")
            print()

    # 2. Marcar configuración
    config_file = Path("config/camera_settings.json")

    if config_file.exists():
        with open(config_file, 'r') as f:
            config = json.load(f)
    else:
        config = {}

    config['cameras_swapped'] = True
    config['swap_note'] = 'Las cámaras físicas están invertidas. El software intercambia automáticamente.'

    config_file.parent.mkdir(exist_ok=True)
    with open(config_file, 'w') as f:
        json.dump(config, f, indent=4)

    print("✅ Configuración actualizada")
    print()

    # 3. Instrucciones
    print("="*60)
    print("PRÓXIMOS PASOS:")
    print("="*60)
    print()
    print("1. INVALIDAR CALIBRACIÓN ACTUAL:")
    print("   La calibración se hizo con cámaras invertidas")
    print()
    print("2. RE-CALIBRAR:")
    print("   python3 main.py")
    print("   → Click 'Calibrate'")
    print("   → Captura 25-30 imágenes del tablero")
    print()
    print("3. VERIFICAR:")
    print("   python3 test_improvements.py")
    print("   → Las correspondencias ahora deben ir hacia la IZQUIERDA")
    print()
    print("="*60)

if __name__ == "__main__":
    fix_camera_swap()
