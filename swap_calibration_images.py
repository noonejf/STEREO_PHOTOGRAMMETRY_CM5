#!/usr/bin/env python3
"""
Script para intercambiar TODAS las imágenes left/right en sesiones de calibración
Intercambia tanto las imágenes en calib_pair_XXX/ como las left_XXX.jpg y right_XXX.jpg

IMPORTANTE: Este script es para corregir fotos de calibración que fueron tomadas
con las cámaras invertidas. NO modifica el código de procesamiento.

Uso:
    python swap_calibration_images.py                    # Ver todas las sesiones
    python swap_calibration_images.py --session NOMBRE   # Procesar una sesión específica
    python swap_calibration_images.py --all              # Procesar TODAS sin preguntar
    python swap_calibration_images.py --undo             # Restaurar desde backup
"""

import os
import sys
import shutil
import argparse
from pathlib import Path

def swap_file_pair(file1: Path, file2: Path) -> bool:
    """Intercambiar dos archivos usando un temporal"""
    if not file1.exists() or not file2.exists():
        return False

    try:
        temp_file = file1.parent / f"_temp_swap_{file1.name}"

        # Swap: file1 -> temp, file2 -> file1, temp -> file2
        shutil.move(str(file1), str(temp_file))
        shutil.move(str(file2), str(file1))
        shutil.move(str(temp_file), str(file2))

        return True
    except Exception as e:
        print(f"      ❌ Error: {e}")
        return False

def swap_calibration_session(session_dir: Path, create_backup: bool = True) -> dict:
    """
    Intercambiar todas las imágenes left/right en una sesión de calibración

    Estructura esperada:
    session_dir/
    ├── calib_pair_000/
    │   ├── left.jpg
    │   └── right.jpg
    ├── calib_pair_001/
    │   └── ...
    ├── left_000.jpg
    ├── right_000.jpg
    └── ...
    """

    print(f"\n📁 Procesando: {session_dir.name}")

    # Crear backup si se solicita
    if create_backup:
        backup_dir = session_dir.parent / f"{session_dir.name}_BACKUP"
        if backup_dir.exists():
            print(f"   ⚠️  Backup ya existe: {backup_dir.name}")
        else:
            print(f"   💾 Creando backup...")
            try:
                shutil.copytree(session_dir, backup_dir)
                print(f"   ✅ Backup guardado: {backup_dir.name}")
            except Exception as e:
                print(f"   ❌ Error creando backup: {e}")
                return {"success": False, "error": "backup_failed"}

    swapped = {"pairs_in_folders": 0, "pairs_root": 0, "failed": 0}

    # 1. Intercambiar imágenes dentro de calib_pair_XXX/
    print(f"   🔄 Intercambiando calib_pair_XXX/left.jpg ↔ right.jpg...")

    pair_folders = sorted(session_dir.glob("calib_pair_*"))
    for pair_folder in pair_folders:
        if not pair_folder.is_dir():
            continue

        left_file = pair_folder / "left.jpg"
        right_file = pair_folder / "right.jpg"

        if swap_file_pair(left_file, right_file):
            swapped["pairs_in_folders"] += 1
        else:
            print(f"      ⚠️  Falta pareja en: {pair_folder.name}")
            swapped["failed"] += 1

    # 2. Intercambiar imágenes en el directorio raíz (left_XXX.jpg ↔ right_XXX.jpg)
    print(f"   🔄 Intercambiando left_XXX.jpg ↔ right_XXX.jpg...")

    left_files = sorted(session_dir.glob("left_*.jpg"))
    for left_file in left_files:
        # Extraer número: "left_000.jpg" -> "000"
        num = left_file.stem.split("_")[-1]
        right_file = session_dir / f"right_{num}.jpg"

        if swap_file_pair(left_file, right_file):
            swapped["pairs_root"] += 1
        else:
            print(f"      ⚠️  Falta pareja para: {left_file.name}")
            swapped["failed"] += 1

    # Resumen
    total_swapped = swapped["pairs_in_folders"] + swapped["pairs_root"]
    print(f"\n   ✅ Intercambiados:")
    print(f"      - En carpetas calib_pair_XXX: {swapped['pairs_in_folders']} pares")
    print(f"      - En directorio raíz: {swapped['pairs_root']} pares")
    print(f"      - Total: {total_swapped} pares")

    if swapped["failed"] > 0:
        print(f"   ⚠️  Fallos: {swapped['failed']}")

    return {"success": True, "swapped": total_swapped, "failed": swapped["failed"]}

def restore_from_backup(calibration_dir: Path, session_name: str = None):
    """Restaurar sesiones desde backup"""

    # Buscar backups
    backups = sorted(calibration_dir.glob("*_BACKUP"))

    if not backups:
        print("❌ No se encontraron backups para restaurar")
        print(f"\nBuscando en: {calibration_dir.absolute()}")
        return

    print(f"\n📦 Backups encontrados: {len(backups)}\n")

    for backup_dir in backups:
        # Nombre original: "calibration_XXXXXX_BACKUP" -> "calibration_XXXXXX"
        original_name = backup_dir.name.replace("_BACKUP", "")
        original_dir = calibration_dir / original_name

        # Si se especificó una sesión, solo restaurar esa
        if session_name and original_name != session_name:
            continue

        print(f"🔄 Restaurando: {original_name}")
        print(f"   Desde: {backup_dir.name}")

        # Eliminar directorio actual si existe
        if original_dir.exists():
            print(f"   🗑️  Eliminando versión actual...")
            shutil.rmtree(original_dir)

        # Restaurar desde backup
        shutil.copytree(backup_dir, original_dir)
        print(f"   ✅ Restaurado exitosamente")

        # Preguntar si eliminar backup
        response = input(f"\n   ¿Eliminar backup {backup_dir.name}? (s/N): ").strip().lower()
        if response == 's':
            shutil.rmtree(backup_dir)
            print(f"   🗑️  Backup eliminado\n")
        else:
            print(f"   💾 Backup conservado\n")

def find_calibration_sessions(calibration_dir: Path) -> list:
    """Encontrar todas las sesiones de calibración"""
    if not calibration_dir.exists():
        return []

    # Buscar directorios que empiecen con "calibration_" (no backups)
    sessions = []
    for item in calibration_dir.iterdir():
        if item.is_dir() and item.name.startswith("calibration_") and not item.name.endswith("_BACKUP"):
            # Verificar que tenga contenido de calibración
            has_pairs = any(item.glob("calib_pair_*"))
            has_images = any(item.glob("left_*.jpg"))

            if has_pairs or has_images:
                sessions.append(item)

    return sorted(sessions)

def main():
    parser = argparse.ArgumentParser(
        description="Intercambiar imágenes left/right en sesiones de calibración",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Ejemplos:
  python swap_calibration_images.py                    # Listar sesiones
  python swap_calibration_images.py --all              # Procesar todas
  python swap_calibration_images.py --session calibration_20251023_185640
  python swap_calibration_images.py --undo             # Restaurar backup
        """
    )
    parser.add_argument(
        "--session",
        type=str,
        help="Nombre de la sesión específica a procesar"
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Procesar TODAS las sesiones sin preguntar"
    )
    parser.add_argument(
        "--undo",
        action="store_true",
        help="Restaurar desde backup"
    )
    parser.add_argument(
        "--no-backup",
        action="store_true",
        help="NO crear backup (PELIGROSO - no recomendado)"
    )

    args = parser.parse_args()

    calibration_dir = Path("data/calibration")

    print("=" * 70)
    print("🔄 SWAP DE IMÁGENES DE CALIBRACIÓN")
    print("=" * 70)

    # Modo restaurar
    if args.undo:
        restore_from_backup(calibration_dir, args.session)
        return

    # Encontrar sesiones
    sessions = find_calibration_sessions(calibration_dir)

    if not sessions:
        print(f"\n❌ No se encontraron sesiones de calibración")
        print(f"\nBuscando en: {calibration_dir.absolute()}")
        return

    # Filtrar por sesión específica si se solicitó
    if args.session:
        session_dir = calibration_dir / args.session
        if not session_dir.exists() or session_dir not in sessions:
            print(f"\n❌ Sesión no encontrada: {args.session}")
            print(f"\nSesiones disponibles:")
            for s in sessions:
                print(f"  - {s.name}")
            sys.exit(1)
        sessions = [session_dir]

    # Mostrar sesiones
    print(f"\n✅ Sesiones encontradas: {len(sessions)}")
    for session in sessions:
        num_pairs = len(list(session.glob("calib_pair_*")))
        num_root = len(list(session.glob("left_*.jpg")))
        print(f"  - {session.name}:")
        print(f"      calib_pair_XXX/: {num_pairs} carpetas")
        print(f"      left/right_XXX.jpg: {num_root} pares")

    # Confirmar acción
    if not args.all:
        if len(sessions) > 1:
            print(f"\n⚠️  Se procesarán {len(sessions)} sesiones")
        else:
            print(f"\n📝 Se procesará: {sessions[0].name}")

        if not args.no_backup:
            print(f"💾 Se creará backup automático")
        else:
            print(f"⚠️  NO se creará backup (--no-backup activado)")

        response = input("\n¿Continuar con el intercambio? (s/N): ").strip().lower()
        if response != 's':
            print("\n❌ Operación cancelada")
            return

    # Procesar sesiones
    print("\n" + "=" * 70)
    print("🚀 INICIANDO INTERCAMBIO...")
    print("=" * 70)

    results = []
    for session in sessions:
        result = swap_calibration_session(session, create_backup=not args.no_backup)
        results.append(result)

    # Resumen final
    success_count = sum(1 for r in results if r.get("success"))
    total_swapped = sum(r.get("swapped", 0) for r in results)

    print("\n" + "=" * 70)
    print(f"✅ COMPLETADO: {success_count}/{len(sessions)} sesiones procesadas")
    print(f"📊 Total de pares intercambiados: {total_swapped}")
    print("=" * 70)

    if success_count > 0:
        print("\n📝 PRÓXIMOS PASOS:")
        print("   1. python main.py")
        print("   2. Click '🎯 Calibrar Cámaras'")
        print("   3. Selecciona la sesión intercambiada")
        print("   4. Click 'Procesar Sesión Existente'")
        print("   5. La calibración se recalculará con imágenes CORRECTAS")
        print(f"\n💾 Para deshacer: python {sys.argv[0]} --undo")

if __name__ == "__main__":
    main()
