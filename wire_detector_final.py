#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
DETECTOR FINAL DE CABLE - Basado en Canny optimizado
Versión refinada para integrar al pipeline de disparidad
"""

import sys
import cv2
import numpy as np
from pathlib import Path

if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')


def detect_wire_canny_optimized(img, debug_name="", min_area=50, connect_distance=50):
    """
    Detector de cable optimizado usando Canny + conexión de componentes

    Args:
        img: Imagen de entrada (BGR o escala de grises)
        debug_name: Nombre para guardar imágenes de debug
        min_area: Área mínima de componentes para mantener (elimina ruido)
        connect_distance: Distancia máxima para conectar componentes del cable

    Returns:
        mask: Máscara binaria (255=cable, 0=fondo)
        stats: Diccionario con estadísticas
    """

    # Convertir a escala de grises
    if len(img.shape) == 3:
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    else:
        gray = img.copy()

    # Suavizado MÍNIMO (solo para reducir ruido del sensor)
    blurred = cv2.GaussianBlur(gray, (3, 3), 0)

    # Canny con umbrales muy sensibles (detectar bordes sutiles)
    # low=10, high=30 funcionó mejor en las pruebas
    edges = cv2.Canny(blurred, threshold1=10, threshold2=30,
                     apertureSize=3, L2gradient=True)

    # Morfología: Dilatar para conectar bordes cercanos del cable
    kernel_dilate = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
    mask_dilated = cv2.dilate(edges, kernel_dilate, iterations=2)

    # Cerrar gaps en el contorno del cable
    kernel_close = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
    mask_closed = cv2.morphologyEx(mask_dilated, cv2.MORPH_CLOSE, kernel_close, iterations=2)

    # NUEVO: Cerrar gaps MÁS GRANDES (conectar partes del cable)
    # Usar kernel más grande para unir componentes separados
    kernel_connect = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (connect_distance, connect_distance))
    mask_connected = cv2.morphologyEx(mask_closed, cv2.MORPH_CLOSE, kernel_connect, iterations=1)

    # Filtrar componentes por área en la máscara CONECTADA
    num_labels, labels, stats_cc, centroids = cv2.connectedComponentsWithStats(mask_connected, connectivity=8)

    # Crear máscara filtrada (solo componentes grandes)
    mask_filtered = np.zeros_like(mask_connected)

    valid_components = []
    for i in range(1, num_labels):  # Empezar en 1 para ignorar el fondo
        area = stats_cc[i, cv2.CC_STAT_AREA]
        if area >= min_area:
            mask_filtered[labels == i] = 255
            valid_components.append({
                'id': i,
                'area': area,
                'bbox': (stats_cc[i, cv2.CC_STAT_LEFT],
                        stats_cc[i, cv2.CC_STAT_TOP],
                        stats_cc[i, cv2.CC_STAT_WIDTH],
                        stats_cc[i, cv2.CC_STAT_HEIGHT]),
                'centroid': centroids[i]
            })

    # Estadísticas
    pixels_total = np.sum(mask_filtered > 0)
    percentage = 100 * pixels_total / mask_filtered.size

    stats = {
        'pixels_detected': int(pixels_total),
        'percentage': percentage,
        'num_components': len(valid_components),
        'components': valid_components,
        'edges_raw': edges,
        'mask_before_connect': mask_closed,
        'mask_after_connect': mask_connected,
        'mask_final': mask_filtered
    }

    # Debug
    if debug_name:
        debug_path = Path("data/results/debug/wire_final")
        debug_path.mkdir(parents=True, exist_ok=True)

        # 1. Bordes raw de Canny
        cv2.imwrite(str(debug_path / f"{debug_name}_1_canny_raw.png"), edges)

        # 2. Después de morfología básica
        cv2.imwrite(str(debug_path / f"{debug_name}_2_morphology.png"), mask_closed)

        # 3. Después de conexión de componentes
        cv2.imwrite(str(debug_path / f"{debug_name}_3_connected.png"), mask_connected)

        # 4. Después de filtrado por área
        cv2.imwrite(str(debug_path / f"{debug_name}_4_filtered.png"), mask_filtered)

        # 5. Overlay sobre imagen original
        overlay = img.copy()
        if len(overlay.shape) == 2:
            overlay = cv2.cvtColor(overlay, cv2.COLOR_GRAY2BGR)

        overlay[mask_filtered > 0] = [0, 255, 0]
        result = cv2.addWeighted(
            img if len(img.shape) == 3 else cv2.cvtColor(img, cv2.COLOR_GRAY2BGR),
            0.7, overlay, 0.3, 0
        )

        # Dibujar bounding boxes de componentes
        for comp in valid_components:
            x, y, w, h = comp['bbox']
            cv2.rectangle(result, (x, y), (x+w, y+h), (255, 255, 0), 2)
            cv2.putText(result, f"A:{comp['area']}", (x, y-5),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 0), 1)

        cv2.imwrite(str(debug_path / f"{debug_name}_5_result.jpg"), result)

        print(f"\n📊 Estadísticas de detección ({debug_name}):")
        print(f"   Píxeles detectados: {pixels_total} ({percentage:.2f}%)")
        print(f"   Componentes válidos: {len(valid_components)}")
        for i, comp in enumerate(valid_components[:5]):  # Mostrar top 5
            print(f"      Componente {i+1}: área={comp['area']} px, bbox={comp['bbox']}")

    return mask_filtered, stats


def detect_wire_stereo_pair(left_img, right_img, min_area=50, connect_distance=50, use_intersection=True):
    """
    Detectar cable en par estéreo y combinar máscaras

    Args:
        left_img: Imagen izquierda
        right_img: Imagen derecha
        min_area: Área mínima de componentes
        connect_distance: Distancia para conectar componentes separados
        use_intersection: Si True, usa intersección de máscaras (conservador)
                         Si False, usa unión (liberal)

    Returns:
        mask_left, mask_right, mask_combined, stats
    """

    print("\n" + "="*80)
    print("DETECCIÓN DE CABLE EN PAR ESTÉREO")
    print("="*80)

    # Detectar en imagen izquierda
    print("\n🔍 Procesando imagen IZQUIERDA...")
    mask_left, stats_left = detect_wire_canny_optimized(left_img, debug_name="left",
                                                         min_area=min_area,
                                                         connect_distance=connect_distance)

    # Detectar en imagen derecha
    print("\n🔍 Procesando imagen DERECHA...")
    mask_right, stats_right = detect_wire_canny_optimized(right_img, debug_name="right",
                                                           min_area=min_area,
                                                           connect_distance=connect_distance)

    # Combinar máscaras
    if use_intersection:
        # Intersección: solo píxeles detectados en AMBAS imágenes (muy conservador)
        mask_combined = cv2.bitwise_and(mask_left, mask_right)
        method = "Intersección (AND)"
    else:
        # Unión: píxeles detectados en AL MENOS UNA imagen (liberal)
        mask_combined = cv2.bitwise_or(mask_left, mask_right)
        method = "Unión (OR)"

    pixels_combined = np.sum(mask_combined > 0)
    percentage_combined = 100 * pixels_combined / mask_combined.size

    print(f"\n📊 RESUMEN:")
    print(f"   Left:  {stats_left['pixels_detected']} px ({stats_left['percentage']:.2f}%)")
    print(f"   Right: {stats_right['pixels_detected']} px ({stats_right['percentage']:.2f}%)")
    print(f"   Combined ({method}): {pixels_combined} px ({percentage_combined:.2f}%)")

    # Guardar máscara combinada
    debug_path = Path("data/results/debug/wire_final")
    debug_path.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(debug_path / "combined_mask.png"), mask_combined)

    stats = {
        'left': stats_left,
        'right': stats_right,
        'combined_pixels': int(pixels_combined),
        'combined_percentage': percentage_combined,
        'method': method
    }

    return mask_left, mask_right, mask_combined, stats


def main():
    """Probar detector con imágenes actuales"""

    print("="*80)
    print("DETECTOR FINAL DE CABLE - PRUEBA")
    print("="*80)

    # Cargar imágenes
    left_path = Path("data/results/debug/01_left_original.jpg")
    right_path = Path("data/results/debug/02_right_original.jpg")

    if not left_path.exists() or not right_path.exists():
        print(f"❌ ERROR: No se encuentran las imágenes")
        return

    left_img = cv2.imread(str(left_path))
    right_img = cv2.imread(str(right_path))

    print(f"\n📂 Imágenes cargadas:")
    print(f"   Left: {left_img.shape}")
    print(f"   Right: {right_img.shape}")

    # Probar diferentes distancias de conexión
    connect_distances = [30, 50, 70, 100]

    print("\n" + "="*80)
    print("PROBANDO DIFERENTES DISTANCIAS DE CONEXIÓN")
    print("="*80)

    for connect_dist in connect_distances:
        print(f"\n{'='*80}")
        print(f"connect_distance = {connect_dist} píxeles")
        print(f"{'='*80}")

        mask_left, mask_right, mask_combined, stats = detect_wire_stereo_pair(
            left_img, right_img,
            min_area=50,
            connect_distance=connect_dist,
            use_intersection=False  # Usar unión para ser más liberal
        )

        # Renombrar archivos con connect_distance
        debug_path = Path("data/results/debug/wire_final")
        for old_name in ["left_5_result.jpg", "right_5_result.jpg", "combined_mask.png",
                        "left_3_connected.png", "right_3_connected.png"]:
            old_path = debug_path / old_name
            if old_path.exists():
                new_name = old_name.replace(".", f"_conn{connect_dist}.")
                old_path.rename(debug_path / new_name)

    print("\n" + "="*80)
    print("✅ PRUEBA COMPLETADA")
    print("="*80)
    print("\nRevisa: data/results/debug/wire_final/")
    print("\nArchivos generados (para cada connect_distance):")
    print("  - left_5_result_connXX.jpg    : Detección final en imagen izquierda")
    print("  - right_5_result_connXX.jpg   : Detección final en imagen derecha")
    print("  - left_3_connected_connXX.png : Máscara después de conexión (izq)")
    print("  - right_3_connected_connXX.png: Máscara después de conexión (der)")
    print("  - combined_mask_connXX.png    : Máscara combinada")
    print("\n💡 Compara las diferentes distancias para ver cuál conecta mejor el cable")


if __name__ == "__main__":
    main()
