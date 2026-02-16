import cv2
import numpy as np
from cv2 import aruco
import os

def create_charuco_board():
    # Configuración del tablero
    # Usamos DICT_6X6_250 porque es estándar y robusto
    aruco_dict = aruco.getPredefinedDictionary(aruco.DICT_6X6_250)
    
    # Dimensiones físicas (Ajustar según necesidad)
    # X=5, Y=7 cuadrados cabe bien en una hoja A4
    SQUARES_X = 5
    SQUARES_Y = 7
    
    # Tamaño en píxeles para la imagen de alta resolución
    # ~300 DPI para A4
    IMG_WIDTH = 2480 
    IMG_HEIGHT = 3508
    
    # Crear el tablero
    # squareLength=1, markerLength=0.8 (proporción, no importa la unidad absoluta aquí)
    board = aruco.CharucoBoard((SQUARES_X, SQUARES_Y), 1.0, 0.8, aruco_dict)
    
    # Dibujar la imagen
    img = board.generateImage((IMG_WIDTH, IMG_HEIGHT), marginSize=100, borderBits=1)
    
    # Guardar como imagen PNG de alta calidad
    output_filename = "charuco_board_5x7.png"
    cv2.imwrite(output_filename, img)
    print(f"✅ Imagen del tablero guardada como: {output_filename}")
    
    # Intentar convertir a PDF (Opcional, requiere librerías extra, mejor nos quedamos con PNG para imprimir)
    print("\nℹ️  Instrucciones de impresión:")
    print("1. Abre la imagen generada.")
    print("2. Imprime en tamaño A4 sin escalar (Escala 100%).")
    print("3. Mide con un calibrador el tamaño real de un cuadrado impreso (ej. 30mm).")
    print("4. ESE valor medido es el que debes poner en la configuración de la cámara.")

if __name__ == "__main__":
    try:
        create_charuco_board()
    except AttributeError:
        print("❌ Error: No se encontró el módulo 'aruco'.")
        print("Asegúrate de tener instalado 'opencv-contrib-python':")
        print("pip install opencv-contrib-python")
