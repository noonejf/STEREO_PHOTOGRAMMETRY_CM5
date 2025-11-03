#!/usr/bin/env python3
"""
Analizar par estéreo del tablero de ajedrez para diagnosticar problemas
de correspondencia

Este script:
1. Detecta esquinas del tablero en AMBAS imágenes
2. Verifica que las MISMAS esquinas se detecten
3. Calcula el desplazamiento (disparidad) entre esquinas correspondientes
4. Visualiza las correspondencias para ver si tienen sentido
"""

import cv2
import numpy as np
from pathlib import Path
import sys

def analyze_chessboard_stereo(left_path, right_path):
    """Analizar correspondencias en par estéreo de tablero"""

    print("="*70)
    print("ANÁLISIS DE CORRESPONDENCIAS - TABLERO DE AJEDREZ")
    print("="*70)
    print()

    # Cargar imágenes
    left_img = cv2.imread(left_path)
    right_img = cv2.imread(right_path)

    if left_img is None or right_img is None:
        print(f"❌ Error cargando imágenes:")
        print(f"   Left: {left_path}")
        print(f"   Right: {right_path}")
        return False

    print(f"✅ Imágenes cargadas:")
    print(f"   Left: {left_img.shape}")
    print(f"   Right: {right_img.shape}")
    print()

    # Convertir a escala de grises
    left_gray = cv2.cvtColor(left_img, cv2.COLOR_BGR2GRAY)
    right_gray = cv2.cvtColor(right_img, cv2.COLOR_BGR2GRAY)

    # Tamaño del tablero (esquinas internas)
    pattern_size = (9, 6)  # 10x7 cuadrados = 9x6 esquinas internas

    print(f"🔍 Buscando tablero {pattern_size[0]}x{pattern_size[1]} esquinas...")
    print()

    # Detectar esquinas en imagen IZQUIERDA
    print("📷 Detectando en imagen IZQUIERDA...")
    ret_left, corners_left = cv2.findChessboardCorners(
        left_gray, pattern_size,
        cv2.CALIB_CB_ADAPTIVE_THRESH + cv2.CALIB_CB_NORMALIZE_IMAGE + cv2.CALIB_CB_FAST_CHECK
    )

    if ret_left:
        # Refinar esquinas
        criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 30, 0.001)
        corners_left = cv2.cornerSubPix(left_gray, corners_left, (11, 11), (-1, -1), criteria)
        print(f"   ✅ {len(corners_left)} esquinas detectadas")
    else:
        print(f"   ❌ NO se detectó el tablero")
        print()
        print("💡 POSIBLE CAUSA:")
        print("   - Tablero borroso o con poca iluminación")
        print("   - Tamaño de tablero incorrecto (¿es 10x7 cuadrados?)")
        print("   - Tablero muy inclinado o fuera de foco")
        return False

    # Detectar esquinas en imagen DERECHA
    print()
    print("📷 Detectando en imagen DERECHA...")
    ret_right, corners_right = cv2.findChessboardCorners(
        right_gray, pattern_size,
        cv2.CALIB_CB_ADAPTIVE_THRESH + cv2.CALIB_CB_NORMALIZE_IMAGE + cv2.CALIB_CB_FAST_CHECK
    )

    if ret_right:
        # Refinar esquinas
        corners_right = cv2.cornerSubPix(right_gray, corners_right, (11, 11), (-1, -1), criteria)
        print(f"   ✅ {len(corners_right)} esquinas detectadas")
    else:
        print(f"   ❌ NO se detectó el tablero")
        return False

    print()
    print("="*70)
    print("📊 ANÁLISIS DE CORRESPONDENCIAS")
    print("="*70)
    print()

    # Ahora tenemos corners_left y corners_right
    # Ambos deberían tener 54 esquinas (9x6)
    # La esquina[i] en left debería corresponder a esquina[i] en right

    # Calcular desplazamientos (disparidades) para cada esquina
    disparities_x = []
    disparities_y = []

    for i in range(len(corners_left)):
        x_left, y_left = corners_left[i][0]
        x_right, y_right = corners_right[i][0]

        # Disparidad = posición en left - posición en right
        disp_x = x_left - x_right
        disp_y = y_left - y_right

        disparities_x.append(disp_x)
        disparities_y.append(disp_y)

    disparities_x = np.array(disparities_x)
    disparities_y = np.array(disparities_y)

    # Estadísticas
    print("📏 DESPLAZAMIENTO HORIZONTAL (Disparidad X):")
    print(f"   Min: {np.min(disparities_x):7.2f} px")
    print(f"   Max: {np.max(disparities_x):7.2f} px")
    print(f"   Media: {np.mean(disparities_x):7.2f} px")
    print(f"   Mediana: {np.median(disparities_x):7.2f} px")
    print(f"   Desv. Est.: {np.std(disparities_x):7.2f} px")
    print()

    print("📏 DESPLAZAMIENTO VERTICAL (Disparidad Y - debería ser ~0):")
    print(f"   Min: {np.min(disparities_y):7.2f} px")
    print(f"   Max: {np.max(disparities_y):7.2f} px")
    print(f"   Media: {np.mean(disparities_y):7.2f} px")
    print(f"   Mediana: {np.median(disparities_y):7.2f} px")
    print(f"   Desv. Est.: {np.std(disparities_y):7.2f} px")
    print()

    # DIAGNÓSTICO
    print("="*70)
    print("💡 DIAGNÓSTICO")
    print("="*70)
    print()

    mean_disp_x = np.mean(disparities_x)
    mean_disp_y = np.mean(disparities_y)
    std_disp_x = np.std(disparities_x)
    std_disp_y = np.std(disparities_y)

    # 1. Verificar dirección de disparidad
    if mean_disp_x > 5:
        print("✅ Disparidad horizontal POSITIVA (left > right)")
        print("   Esto es CORRECTO para configuración CAM0=left, CAM1=right")
        print()
    elif mean_disp_x < -5:
        print("❌ Disparidad horizontal NEGATIVA (left < right)")
        print("   ¡Las cámaras están INVERTIDAS!")
        print("   SOLUCIÓN: Intercambiar left_camera_id y right_camera_id en config")
        print()
    else:
        print("⚠️ Disparidad horizontal CASI CERO (<5px)")
        print("   Las imágenes son casi idénticas.")
        print("   POSIBLE CAUSA:")
        print("   - Las cámaras NO están en configuración estéreo")
        print("   - Objeto muy lejano (baseline insuficiente)")
        print()

    # 2. Verificar magnitud de disparidad
    if abs(mean_disp_x) > 500:
        print("❌ Disparidad DEMASIADO GRANDE (>500px)")
        print("   Con baseline ~10cm, esto es físicamente imposible.")
        print("   POSIBLE CAUSA:")
        print("   - Calibración con escala incorrecta (mm vs m)")
        print("   - Imágenes NO están rectificadas correctamente")
        print()
    elif abs(mean_disp_x) > 100:
        print("⚠️ Disparidad GRANDE (>100px)")
        print("   Puede indicar:")
        print("   - Objeto muy cercano (<50cm)")
        print("   - O problema de escala en calibración")
        print()
    elif abs(mean_disp_x) > 10:
        print("✅ Disparidad RAZONABLE (10-100px)")
        print("   Esto es consistente con configuración estéreo normal.")
        print()
    elif abs(mean_disp_x) > 0:
        print("⚠️ Disparidad PEQUEÑA (<10px)")
        print("   Puede indicar:")
        print("   - Objeto muy lejano (>5m)")
        print("   - Baseline insuficiente")
        print()

    # 3. Verificar disparidad vertical (rectificación)
    if abs(mean_disp_y) < 2:
        print("✅ Disparidad vertical MÍNIMA (<2px)")
        print("   Las imágenes están bien rectificadas (líneas epipolares horizontales).")
        print()
    elif abs(mean_disp_y) < 5:
        print("⚠️ Disparidad vertical MODERADA (2-5px)")
        print("   Rectificación aceptable pero no óptima.")
        print()
    else:
        print("❌ Disparidad vertical ALTA (>5px)")
        print("   Las imágenes NO están rectificadas correctamente.")
        print("   SOLUCIÓN: RE-CALIBRAR el sistema.")
        print()

    # 4. Verificar consistencia (desviación estándar)
    if std_disp_x < 5:
        print("✅ Disparidad CONSISTENTE (baja variación)")
        print("   Todas las esquinas tienen disparidad similar.")
        print()
    else:
        print("⚠️ Disparidad INCONSISTENTE (alta variación)")
        print(f"   Desv. Est.: {std_disp_x:.2f}px")
        print("   Puede indicar:")
        print("   - Tablero no plano")
        print("   - Errores de detección de esquinas")
        print("   - Distorsión no corregida")
        print()

    # CREAR VISUALIZACIÓN
    print("="*70)
    print("🎨 GENERANDO VISUALIZACIÓN...")
    print("="*70)
    print()

    # Dibujar esquinas detectadas
    vis_left = left_img.copy()
    vis_right = right_img.copy()

    cv2.drawChessboardCorners(vis_left, pattern_size, corners_left, ret_left)
    cv2.drawChessboardCorners(vis_right, pattern_size, corners_right, ret_right)

    # Crear imagen combinada
    h, w = left_img.shape[:2]
    combined = np.zeros((h, w*2, 3), dtype=np.uint8)
    combined[:, :w] = vis_left
    combined[:, w:] = vis_right

    # Dibujar líneas de correspondencia para algunas esquinas
    # Tomar muestra de esquinas (cada 5 para no saturar)
    colors = [
        (0, 255, 0),    # Verde
        (255, 0, 0),    # Azul
        (0, 0, 255),    # Rojo
        (255, 255, 0),  # Cyan
        (255, 0, 255),  # Magenta
        (0, 255, 255),  # Amarillo
    ]

    for i in range(0, len(corners_left), 5):
        x_left, y_left = corners_left[i][0]
        x_right, y_right = corners_right[i][0]

        color = colors[i % len(colors)]

        # Punto en left
        cv2.circle(combined, (int(x_left), int(y_left)), 8, color, -1)
        cv2.circle(combined, (int(x_left), int(y_left)), 9, (255, 255, 255), 2)

        # Punto en right (desplazado por w)
        cv2.circle(combined, (int(x_right) + w, int(y_right)), 8, color, -1)
        cv2.circle(combined, (int(x_right) + w, int(y_right)), 9, (255, 255, 255), 2)

        # Línea de correspondencia
        cv2.line(combined, (int(x_left), int(y_left)), (int(x_right) + w, int(y_right)), color, 2)

        # Etiqueta con disparidad
        disp_text = f"{disparities_x[i]:.0f}px"
        cv2.putText(combined, disp_text, (int(x_left) + 10, int(y_left) - 10),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 2)

    # Agregar información en la imagen
    info_y = 30
    cv2.putText(combined, f"Disparidad media: {mean_disp_x:.1f}px (horizontal) {mean_disp_y:.1f}px (vertical)",
               (10, info_y), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2)

    # Guardar visualización
    output_path = Path("data/results/debug/chessboard_correspondences.jpg")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(output_path), combined)

    print(f"✅ Visualización guardada: {output_path}")
    print()

    # CONCLUSIÓN FINAL
    print("="*70)
    print("🎯 CONCLUSIÓN FINAL")
    print("="*70)
    print()

    if mean_disp_x < -5:
        print("❌ PROBLEMA: CÁMARAS INVERTIDAS")
        print("   Las correspondencias van en dirección INCORRECTA.")
        print()
        print("SOLUCIÓN:")
        print("   Opción 1: Intercambiar físicamente los cables de las cámaras")
        print("   Opción 2: Modificar camera_config.py:")
        print("             left_camera.camera_id = 1")
        print("             right_camera.camera_id = 0")
        print()
    elif abs(mean_disp_y) > 5:
        print("❌ PROBLEMA: RECTIFICACIÓN INCORRECTA")
        print("   Las líneas epipolares NO son horizontales.")
        print()
        print("SOLUCIÓN:")
        print("   RE-CALIBRAR el sistema")
        print()
    elif abs(mean_disp_x) < 5:
        print("❌ PROBLEMA: SIN DISPARIDAD ESTÉREO")
        print("   Las imágenes son casi idénticas.")
        print()
        print("SOLUCIÓN:")
        print("   Verificar configuración física de las cámaras")
        print()
    elif abs(mean_disp_x) > 500:
        print("❌ PROBLEMA: DISPARIDAD ABSURDA")
        print("   Los valores son físicamente imposibles.")
        print()
        print("SOLUCIÓN:")
        print("   El problema está en la ESCALA de calibración (mm vs m)")
        print("   O las imágenes NO están rectificadas")
        print()
    else:
        print("✅ LAS CORRESPONDENCIAS SON CORRECTAS")
        print()
        print(f"   Disparidad: {mean_disp_x:.1f}px ± {std_disp_x:.1f}px")
        print(f"   Error vertical: {mean_disp_y:.1f}px")
        print()
        print("Si la reconstrucción 3D aún falla, el problema está en:")
        print("   - Algoritmo SGBM (parámetros)")
        print("   - Conversión disparidad → profundidad (matriz Q)")
        print()

    print("="*70)

    return True

if __name__ == "__main__":
    # Buscar la captura más reciente con tablero
    if len(sys.argv) == 3:
        left_path = sys.argv[1]
        right_path = sys.argv[2]
    else:
        # Usar captura más reciente
        left_path = "data/captures/stereo_20251103_165334/left.jpg"
        right_path = "data/captures/stereo_20251103_165334/right.jpg"

    analyze_chessboard_stereo(left_path, right_path)
