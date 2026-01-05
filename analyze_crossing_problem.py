#!/usr/bin/env python3
"""
Analizar el problema de cruces en el cable

El usuario tiene UN cable en espiral que se cruza sobre sí mismo.
Necesitamos entender si quiere:
1. UNA curva continua trazada (el cable completo)
2. DOS líneas separadas en los cruces (topología 3D)
"""

import cv2
import numpy as np
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent))

from processing.curve_tracker import CurveTracker


def analyze_crossing():
    """
    Analizar el skeleton y mostrar dónde están los cruces
    """

    print("="*80)
    print("ANALISIS DE CRUCES EN EL CABLE")
    print("="*80)

    # Cargar máscara original
    mask_path = "data/results/debug/cable_mask_left.png"
    mask = cv2.imread(mask_path, cv2.IMREAD_GRAYSCALE)

    if mask is None:
        print(f"\nERROR: No se pudo cargar: {mask_path}")
        return

    print(f"\nMascara cargada: {mask.shape}")
    print(f"Pixeles: {np.sum(mask > 0)}")

    # Crear skeleton SIMPLE (sin limpieza)
    print("\n[1] Creando skeleton simple...")
    mask_binary = (mask > 0).astype(np.uint8)
    skeleton = cv2.ximgproc.thinning(mask_binary * 255,
                                     thinningType=cv2.ximgproc.THINNING_ZHANGSUEN)
    skeleton = (skeleton > 0).astype(np.uint8)

    pixels_skeleton = np.sum(skeleton > 0)
    print(f"    Skeleton: {pixels_skeleton} pixeles")

    # Analizar topología
    print("\n[2] Analizando topologia...")
    coords = np.column_stack(np.where(skeleton > 0))

    endpoints = []  # 1 vecino
    normal_points = []  # 2 vecinos
    junctions = []  # 3+ vecinos

    for y, x in coords:
        neighbors = skeleton[max(0, y-1):y+2, max(0, x-1):x+2]
        num_neighbors = np.sum(neighbors) - 1

        if num_neighbors == 1:
            endpoints.append((x, y))
        elif num_neighbors == 2:
            normal_points.append((x, y))
        elif num_neighbors >= 3:
            junctions.append((x, y, num_neighbors))

    print(f"    Endpoints (1 vecino):  {len(endpoints)}")
    print(f"    Normal (2 vecinos):     {len(normal_points)}")
    print(f"    Bifurcaciones (3+):     {len(junctions)}")

    # Mostrar bifurcaciones
    if len(junctions) > 0:
        print(f"\n[3] Detalles de bifurcaciones:")
        for i, (x, y, num_neighbors) in enumerate(junctions[:10]):  # Mostrar primeras 10
            print(f"    [{i}] ({x}, {y}) - {num_neighbors} vecinos")

    # Trazar curva COMPLETA usando CurveTracker
    print(f"\n[4] Trazando curva continua...")
    tracker = CurveTracker()
    result = tracker.extract_and_order_skeleton(skeleton, sample_spacing=3)

    if not result['success']:
        print(f"    ERROR: {result['error']}")
        return

    print(f"    Curva trazada: {result['num_points']} puntos")
    print(f"    Endpoints: {result['endpoints']}")

    # Guardar visualizaciones
    debug_path = Path("data/results/debug/crossing_analysis")
    debug_path.mkdir(parents=True, exist_ok=True)

    print(f"\n[5] Guardando visualizaciones...")

    # Visualización 1: Skeleton con bifurcaciones marcadas
    vis1 = np.zeros((*skeleton.shape, 3), dtype=np.uint8)
    vis1[skeleton > 0] = [255, 255, 255]  # Skeleton en blanco

    # Marcar bifurcaciones en rojo
    for x, y, num_neighbors in junctions:
        cv2.circle(vis1, (x, y), 15, (0, 0, 255), 2)
        cv2.circle(vis1, (x, y), 5, (0, 0, 255), -1)
        cv2.putText(vis1, str(num_neighbors), (x+18, y),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 255), 1)

    # Marcar endpoints en verde
    for x, y in endpoints:
        cv2.circle(vis1, (x, y), 12, (0, 255, 0), 2)

    cv2.imwrite(str(debug_path / "01_skeleton_junctions.png"), vis1)
    print(f"    Guardado: {debug_path / '01_skeleton_junctions.png'}")

    # Visualización 2: Curva ordenada en imagen original
    img_orig = cv2.imread("data/captures/stereo_20251119_175650/left.jpg")
    if img_orig is not None:
        tracker.visualize_curve(img_orig, result['ordered_points'],
                              debug_path / "02_traced_curve.jpg")
        print(f"    Guardado: {debug_path / '02_traced_curve.jpg'}")

    # Análisis de la pregunta clave
    print(f"\n{'='*80}")
    print("PREGUNTA CLAVE")
    print(f"{'='*80}")
    print(f"\nTienes UN cable continuo en espiral con {len(junctions)} bifurcaciones.")
    print(f"Estas bifurcaciones son lugares donde el cable se cruza sobre si mismo.")
    print(f"\nOPCIONES:")
    print(f"\n[A] Quieres UNA curva continua trazada desde inicio a fin")
    print(f"    -> El CurveTracker ya hace esto: {result['num_points']} puntos")
    print(f"    -> En los cruces, elige una rama y continua")
    print(f"\n[B] Quieres DOS lineas SEPARADAS en cada cruce")
    print(f"    -> Esto requiere informacion de PROFUNDIDAD (stereo)")
    print(f"    -> NO se puede hacer con una sola imagen")
    print(f"\n[C] Quieres eliminar las bifurcaciones falsas pero mantener cruces")
    print(f"    -> Esto es contradictorio: un cruce ES una bifurcacion")
    print(f"\nCual es tu objetivo real?")
    print(f"{'='*80}\n")


if __name__ == "__main__":
    analyze_crossing()
