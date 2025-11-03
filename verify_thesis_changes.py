#!/usr/bin/env python3
"""
Script de verificación de cambios basados en la tesis
Comprueba que todos los parámetros críticos estén configurados correctamente
"""

import sys
from pathlib import Path

# Colores para terminal
GREEN = '\033[92m'
RED = '\033[91m'
YELLOW = '\033[93m'
BLUE = '\033[94m'
RESET = '\033[0m'

def print_check(condition, message, expected, actual):
    """Imprimir resultado de verificación"""
    if condition:
        print(f"{GREEN}✓{RESET} {message}")
        print(f"  {BLUE}Esperado:{RESET} {expected}")
        print(f"  {BLUE}Actual:{RESET} {actual}")
    else:
        print(f"{RED}✗{RESET} {message}")
        print(f"  {RED}Esperado:{RESET} {expected}")
        print(f"  {RED}Actual:{RESET} {actual}")
    return condition

def verify_stereo_processor():
    """Verificar parámetros en stereo_processor.py"""
    print(f"\n{YELLOW}=== VERIFICANDO stereo_processor.py ==={RESET}\n")

    try:
        # Importar el módulo
        from config.camera_config import CameraConfig
        from processing.stereo_processor import StereoProcessor

        # Crear instancia con config mock
        config = CameraConfig()

        # Simular calibración para poder crear el procesador
        config.calibration_data = {
            'is_calibrated': True,
            'left_camera_matrix': [[1, 0, 0], [0, 1, 0], [0, 0, 1]],
            'left_distortion': [0, 0, 0, 0, 0],
            'right_camera_matrix': [[1, 0, 0], [0, 1, 0], [0, 0, 1]],
            'right_distortion': [0, 0, 0, 0, 0],
            'rotation_matrix': [[1, 0, 0], [0, 1, 0], [0, 0, 1]],
            'translation_vector': [[100], [0], [0]],
            'disparity_to_depth_matrix': [[1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 0, 1], [0, 0, 1, 0]]
        }

        processor = StereoProcessor(config)

        # Verificar parámetros SGBM
        all_ok = True

        all_ok &= print_check(
            processor.sgbm.getNumDisparities() == 64,
            "numDisparities (rango de búsqueda)",
            "64 (como tesis)",
            processor.sgbm.getNumDisparities()
        )

        all_ok &= print_check(
            processor.sgbm.getBlockSize() == 15,
            "blockSize (tamaño de ventana)",
            "15 (ventanas grandes para superficies lisas)",
            processor.sgbm.getBlockSize()
        )

        all_ok &= print_check(
            processor.sgbm.getUniquenessRatio() == 0,
            "uniquenessRatio (filtrado de ambigüedad)",
            "0 (desactivado, como tesis)",
            processor.sgbm.getUniquenessRatio()
        )

        all_ok &= print_check(
            processor.sgbm.getSpeckleWindowSize() == 100,
            "speckleWindowSize (tamaño de región de ruido)",
            "100 (reducido de 200)",
            processor.sgbm.getSpeckleWindowSize()
        )

        all_ok &= print_check(
            processor.sgbm.getSpeckleRange() == 8,
            "speckleRange (variación tolerada)",
            "8 (como tesis, aumentado de 2)",
            processor.sgbm.getSpeckleRange()
        )

        all_ok &= print_check(
            processor.sgbm.getPreFilterCap() == 61,
            "preFilterCap (límite de pre-filtro)",
            "61 (como tesis)",
            processor.sgbm.getPreFilterCap()
        )

        # Verificar filtro WLS
        all_ok &= print_check(
            processor.wls_filter.getLambda() == 3000.0,
            "WLS lambda (suavizado)",
            "3000.0 (reducido de 8000)",
            processor.wls_filter.getLambda()
        )

        return all_ok

    except Exception as e:
        print(f"{RED}ERROR al verificar stereo_processor.py: {e}{RESET}")
        return False

def verify_calibration_file():
    """Verificar parámetros en camera_calibration.py"""
    print(f"\n{YELLOW}=== VERIFICANDO camera_calibration.py ==={RESET}\n")

    try:
        # Leer el archivo y buscar alpha
        calibration_file = Path("camera/camera_calibration.py")

        if not calibration_file.exists():
            print(f"{RED}✗ Archivo no encontrado: {calibration_file}{RESET}")
            return False

        content = calibration_file.read_text(encoding='utf-8')

        # Buscar línea con alpha en stereoRectify
        alpha_found = False
        alpha_value = None

        for line in content.split('\n'):
            if 'alpha=' in line and 'stereoRectify' in content[max(0, content.find(line)-500):content.find(line)+500]:
                alpha_found = True
                # Extraer valor de alpha
                if 'alpha=0.0' in line or 'alpha = 0.0' in line:
                    alpha_value = 0.0
                elif 'alpha=-1' in line or 'alpha = -1' in line:
                    alpha_value = -1
                elif 'alpha=1.0' in line or 'alpha = 1.0' in line:
                    alpha_value = 1.0
                break

        if alpha_found:
            all_ok = print_check(
                alpha_value == 0.0,
                "alpha en stereoRectify (recorte de bordes)",
                "0.0 (recortar bordes distorsionados, como tesis)",
                alpha_value
            )
            return all_ok
        else:
            print(f"{RED}✗ No se encontró parámetro alpha en stereoRectify{RESET}")
            return False

    except Exception as e:
        print(f"{RED}ERROR al verificar camera_calibration.py: {e}{RESET}")
        return False

def verify_preprocessing():
    """Verificar que bilateralFilter esté eliminado"""
    print(f"\n{YELLOW}=== VERIFICANDO PREPROCESAMIENTO ==={RESET}\n")

    try:
        stereo_file = Path("processing/stereo_processor.py")

        if not stereo_file.exists():
            print(f"{RED}✗ Archivo no encontrado: {stereo_file}{RESET}")
            return False

        content = stereo_file.read_text(encoding='utf-8')

        # Buscar función preprocess_images
        preprocess_start = content.find('def preprocess_images')
        preprocess_end = content.find('def ', preprocess_start + 1)
        preprocess_section = content[preprocess_start:preprocess_end]

        # Verificar que bilateralFilter esté comentado
        bilateral_lines = [line for line in preprocess_section.split('\n') if 'bilateralFilter' in line]
        all_commented = all(line.strip().startswith('#') for line in bilateral_lines)

        all_ok = print_check(
            all_commented and len(bilateral_lines) > 0,
            "bilateralFilter eliminado (preserva textura)",
            "Comentado/eliminado",
            "Comentado" if all_commented else "ACTIVO (ERROR)"
        )

        # Verificar que CLAHE esté presente
        clahe_present = 'createCLAHE' in preprocess_section
        all_ok &= print_check(
            clahe_present,
            "CLAHE presente (ecualización adaptativa)",
            "Presente",
            "Presente" if clahe_present else "AUSENTE"
        )

        return all_ok

    except Exception as e:
        print(f"{RED}ERROR al verificar preprocesamiento: {e}{RESET}")
        return False

def verify_disparity_thresholds():
    """Verificar umbrales de disparidad"""
    print(f"\n{YELLOW}=== VERIFICANDO UMBRALES DE DISPARIDAD ==={RESET}\n")

    try:
        stereo_file = Path("processing/stereo_processor.py")

        if not stereo_file.exists():
            print(f"{RED}✗ Archivo no encontrado: {stereo_file}{RESET}")
            return False

        content = stereo_file.read_text(encoding='utf-8')

        # Buscar función generate_point_cloud
        pc_start = content.find('def generate_point_cloud')
        pc_end = content.find('def ', pc_start + 1)
        pc_section = content[pc_start:pc_end]

        # Buscar línea con valid_mask = disparity >
        all_ok = True
        for line in pc_section.split('\n'):
            if 'valid_mask = disparity >' in line and '1.0' in line:
                all_ok &= print_check(
                    True,
                    "Umbral de disparidad en nube de puntos",
                    "> 1.0 (como tesis)",
                    "✓ Encontrado: " + line.strip()
                )
                break
        else:
            print(f"{RED}✗ No se encontró 'valid_mask = disparity > 1.0'{RESET}")
            all_ok = False

        # Buscar en compute_disparity
        disp_start = content.find('def compute_disparity')
        disp_end = content.find('def ', disp_start + 1)
        disp_section = content[disp_start:disp_end]

        for line in disp_section.split('\n'):
            if 'valid_mask = disparity' in line and '> 0.5' in line:
                all_ok &= print_check(
                    True,
                    "Umbral de disparidad para estadísticas",
                    "> 0.5 (reducido de 0)",
                    "✓ Encontrado: " + line.strip()
                )
                break

        return all_ok

    except Exception as e:
        print(f"{RED}ERROR al verificar umbrales: {e}{RESET}")
        return False

def main():
    """Ejecutar verificación completa"""
    print(f"\n{BLUE}{'='*60}{RESET}")
    print(f"{BLUE}VERIFICACIÓN DE CAMBIOS BASADOS EN TESIS{RESET}")
    print(f"{BLUE}{'='*60}{RESET}")

    results = []

    # Verificar cada componente
    results.append(("Parámetros SGBM", verify_stereo_processor()))
    results.append(("Calibración (alpha)", verify_calibration_file()))
    results.append(("Preprocesamiento", verify_preprocessing()))
    results.append(("Umbrales de disparidad", verify_disparity_thresholds()))

    # Resumen final
    print(f"\n{BLUE}{'='*60}{RESET}")
    print(f"{BLUE}RESUMEN DE VERIFICACIÓN{RESET}")
    print(f"{BLUE}{'='*60}{RESET}\n")

    all_passed = True
    for name, passed in results:
        status = f"{GREEN}✓ PASS{RESET}" if passed else f"{RED}✗ FAIL{RESET}"
        print(f"{name:.<40} {status}")
        all_passed &= passed

    print(f"\n{BLUE}{'='*60}{RESET}")

    if all_passed:
        print(f"{GREEN}✓ TODOS LOS CAMBIOS VERIFICADOS CORRECTAMENTE{RESET}")
        print(f"\n{YELLOW}IMPORTANTE:{RESET} Ahora debes RECALIBRAR el sistema para que")
        print(f"los nuevos parámetros (especialmente alpha=0.0) tomen efecto.")
        print(f"\nPasos siguientes:")
        print(f"  1. Ejecuta: python main.py")
        print(f"  2. Haz clic en 'Calibrate'")
        print(f"  3. Captura 25 imágenes del tablero")
        print(f"  4. Captura una foto de tu mano")
        print(f"  5. Procesa con 'Process Latest'")
        return 0
    else:
        print(f"{RED}✗ ALGUNOS CAMBIOS NO SE APLICARON CORRECTAMENTE{RESET}")
        print(f"\nRevisa los errores arriba y verifica manualmente los archivos.")
        return 1

if __name__ == "__main__":
    sys.exit(main())
