#!/usr/bin/env python3
"""
Script de prueba modular (MODO SIMPLE) para el CameraCalibrator.

Este script SÓLO comprueba si las esquinas se pueden detectar,
ignora todos los filtros de calidad (blur, contraste, etc.)
"""

import cv2
import glob
import sys
from pathlib import Path
import numpy as np

# --- Configuración del Proyecto ---
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

try:
    from config.camera_config import CameraConfig
    from camera.camera_calibration import CameraCalibrator
    from utils.logger import setup_logger
except ImportError as e:
    print(f"Error: No se pudieron importar los módulos. Asegúrate de estar en el directorio raíz.")
    print(f"Detalle: {e}")
    sys.exit(1)

# --- CONFIGURA ESTO ---
# Cambia esto por la carpeta de la sesión que falló.
SESSION_DIR_TO_TEST = 'data/calibration/calibration_20251022_130116' 

def run_test():
    """
    Ejecuta el test de validación de imágenes.
    """
    setup_logger() # Configura el logger para ver la salida del calibrador
    
    print(f"=== Probador Modular de Calibración (MODO SIMPLE) ===")
    print(f"Usando sesión: {SESSION_DIR_TO_TEST}\n")

    session_path = Path(SESSION_DIR_TO_TEST)
    if not session_path.exists():
        print(f"Error: El directorio de sesión no existe: {SESSION_DIR_TO_TEST}")
        print("Por favor, actualiza la variable 'SESSION_DIR_TO_TEST' en este script.")
        return

    # 1. Cargar configuración y calibrador
    try:
        config = CameraConfig()
        calibrator = CameraCalibrator(config)
    except Exception as e:
        print(f"Error inicializando configuración o calibrador: {e}")
        return

    # 2. Buscar pares de imágenes (usando tu formato de guardado)
    left_images = sorted(session_path.glob("left_*.jpg"))
    right_images = sorted(session_path.glob("right_*.jpg"))

    if not left_images or not right_images:
        print("No se encontraron imágenes 'left_*.jpg' o 'right_*.jpg' en la sesión.")
        return

    print(f"Encontrados {len(left_images)} pares de imágenes. Analizando...\n")

    valid_pairs_found = 0

    for left_path, right_path in zip(left_images, right_images):
        print(f"--- Procesando: {left_path.name} y {right_path.name} ---")
        
        img_left = cv2.imread(str(left_path))
        img_right = cv2.imread(str(right_path))

        if img_left is None or img_right is None:
            print("ERROR: No se pudo cargar una de las imágenes.\n")
            continue

        # 3. Probar Detección de Esquinas (Paso 1 del calibrador)
        ret_left, corners_left = calibrator.detect_chessboard_corners(img_left, improve_accuracy=True)
        ret_right, corners_right = calibrator.detect_chessboard_corners(img_right, improve_accuracy=True)

        # 4. Lógica simple: Si ambas se detectan, es válida
        if ret_left and ret_right:
            status_text = "ACEPTADA"
            color = (0, 255, 0) # Verde
            valid_pairs_found += 1
            print(f"  Izquierda: OK")
            print(f"  Derecha:   OK")
        else:
            status_text = "RECHAZADA"
            color = (0, 0, 255) # Rojo
            print(f"  Izquierda: {'OK' if ret_left else 'FALLÓ'}")
            print(f"  Derecha:   {'OK' if ret_right else 'FALLÓ'}")
            
            # Si quieres ver la imagen aunque falle, descomenta las siguientes 3 líneas
            #print("\nPresiona cualquier tecla para continuar...")
            #display_img_fail = cv2.resize(np.hstack((img_left, img_right)), (1280, 480))
            #cv2.imshow("Probador de Calibracion (Modo Simple)", display_img_fail)
            #cv2.waitKey(0)
            
            print("---") # Separador
            continue # Saltar a la siguiente imagen
        
        # 5. Mostrar Feedback Visual (¡Lo que querías!)
        
        # Dibuja las esquinas encontradas
        img_left_drawn = cv2.drawChessboardCorners(
            img_left.copy(), 
            calibrator.board_size, 
            corners_left, 
            ret_left
        )
        img_right_drawn = cv2.drawChessboardCorners(
            img_right.copy(), 
            calibrator.board_size, 
            corners_right, 
            ret_right
        )
        
        # Combina imágenes para mostrarlas
        h, w = img_left_drawn.shape[:2]
        combined_image = np.zeros((h, w*2, 3), dtype=np.uint8)
        combined_image[0:h, 0:w] = img_left_drawn
        combined_image[0:h, w:w*2] = img_right_drawn
        
        cv2.putText(combined_image, status_text, (50, 70), cv2.FONT_HERSHEY_SIMPLEX, 2.5, color, 8)
        
        print("\nPresiona any tecla para continuar con la siguiente imagen...")

        # Redimensiona para ver cómodamente
        display_img = cv2.resize(combined_image, (1280, 480))
        cv2.imshow("Probador de Calibracion (Modo Simple)", display_img)
        cv2.waitKey(0) # Espera a que presiones una tecla

    cv2.destroyAllWindows()
    print(f"\n--- ANÁLISIS COMPLETO ---")
    print(f"Pares válidos encontrados: {valid_pairs_found} / {len(left_images)}")
    
    # Comprobar contra el mínimo requerido de la config
    min_required = config.stereo.min_calibration_images
    print(f"Pares mínimos requeridos: {min_required}")
    
    if valid_pairs_found < min_required:
        print(f"Resultado: INSUFICIENTE. Se necesitan {min_required} pares.")
    else:
        print(f"Resultado: ¡SUFICIENTE PARA CALIBRAR!")

if __name__ == "__main__":
    run_test()