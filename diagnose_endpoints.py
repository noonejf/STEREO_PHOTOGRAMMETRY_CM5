#!/usr/bin/env python3
"""
Diagnóstico de detección de extremos de cable
"""

import cv2
import numpy as np
from pathlib import Path
import sys

# Agregar directorio raíz al path
sys.path.insert(0, str(Path(__file__).parent))

from processing.curve_tracker import CurveTracker
from utils.logger import get_logger

logger = get_logger(__name__)


def detect_wire_mask_simple(image_path: str) -> np.ndarray:
    """
    Detectar cable usando método simple basado en bordes
    """
    img = cv2.imread(image_path)
    if img is None:
        raise ValueError(f"No se pudo cargar imagen: {image_path}")

    # Convertir a escala de grises
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    # Detectar bordes
    edges = cv2.Canny(gray, 50, 150)

    # Dilatar para conectar bordes cercanos
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
    edges_dilated = cv2.dilate(edges, kernel, iterations=2)

    # Cerrar gaps
    edges_closed = cv2.morphologyEx(edges_dilated, cv2.MORPH_CLOSE, kernel, iterations=3)

    # Rellenar regiones
    contours, _ = cv2.findContours(edges_closed, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    # Crear máscara con el contorno más grande
    mask = np.zeros_like(gray)
    if len(contours) > 0:
        largest = max(contours, key=cv2.contourArea)
        cv2.drawContours(mask, [largest], -1, 255, -1)

    return mask


def analyze_endpoints(image_path: str, save_debug: bool = True):
    """
    Analizar detección de extremos en imagen de cable
    """

    print("="*80)
    print("DIAGNÓSTICO DE DETECCIÓN DE EXTREMOS")
    print("="*80)
    print(f"\nImagen: {image_path}\n")

    # Cargar imagen
    img = cv2.imread(image_path)
    if img is None:
        print(f"ERROR: No se pudo cargar imagen: {image_path}")
        return

    h, w = img.shape[:2]
    print(f"Tamaño imagen: {w}x{h}")

    # Detectar máscara del cable
    print("\n[1/5] Detectando cable...")
    mask = detect_wire_mask_simple(image_path)
    pixels_mask = np.sum(mask > 0)
    print(f"  Píxeles de cable: {pixels_mask}")

    # Crear skeleton
    print("\n[2/5] Creando skeleton...")
    mask_binary = (mask > 0).astype(np.uint8)
    skeleton = cv2.ximgproc.thinning(mask_binary * 255,
                                     thinningType=cv2.ximgproc.THINNING_ZHANGSUEN)
    skeleton = (skeleton > 0).astype(np.uint8)
    pixels_skeleton = np.sum(skeleton > 0)
    print(f"  Píxeles de skeleton: {pixels_skeleton}")

    # Buscar endpoints (puntos con 1 vecino)
    print("\n[3/5] Buscando endpoints (puntos con 1 vecino)...")
    coords = np.column_stack(np.where(skeleton > 0))

    endpoints_1_neighbor = []
    endpoints_2_neighbors = []
    junctions = []  # Puntos con 3+ vecinos

    for y, x in coords:
        # Contar vecinos en ventana 3x3
        neighbors = skeleton[max(0, y-1):y+2, max(0, x-1):x+2]
        num_neighbors = np.sum(neighbors) - 1  # Excluir el punto mismo

        if num_neighbors == 1:
            endpoints_1_neighbor.append((x, y))
        elif num_neighbors == 2:
            endpoints_2_neighbors.append((x, y))
        elif num_neighbors >= 3:
            junctions.append((x, y))

    print(f"  Endpoints (1 vecino): {len(endpoints_1_neighbor)}")
    print(f"  Puntos normales (2 vecinos): {len(endpoints_2_neighbors)}")
    print(f"  Bifurcaciones (3+ vecinos): {len(junctions)}")

    # Mostrar coordenadas de todos los endpoints
    if len(endpoints_1_neighbor) > 0:
        print("\n  Coordenadas de endpoints:")
        for i, (x, y) in enumerate(endpoints_1_neighbor):
            print(f"    [{i}] ({x}, {y})")

    # Calcular distancia entre todos los pares de endpoints
    if len(endpoints_1_neighbor) >= 2:
        print("\n  Distancias entre endpoints:")
        for i, p1 in enumerate(endpoints_1_neighbor):
            for j, p2 in enumerate(endpoints_1_neighbor[i+1:], i+1):
                dist = np.linalg.norm(np.array(p1) - np.array(p2))
                print(f"    [{i}] <-> [{j}]: {dist:.1f} px")

    # Usar CurveTracker para extraer curva completa
    print("\n[4/5] Extrayendo curva ordenada...")
    tracker = CurveTracker()
    result = tracker.extract_and_order_skeleton(mask, sample_spacing=3)

    if result['success']:
        print(f"  ✓ Curva extraída: {result['num_points']} puntos")
        print(f"  Endpoints detectados por CurveTracker: {result['endpoints']}")

        detected_endpoints = result['endpoints']
        if len(detected_endpoints) == 2:
            dist = np.linalg.norm(np.array(detected_endpoints[0]) - np.array(detected_endpoints[1]))
            print(f"  Distancia entre endpoints: {dist:.1f} px")
    else:
        print(f"  ❌ Error: {result['error']}")
        detected_endpoints = []

    # Crear visualización
    if save_debug:
        print("\n[5/5] Guardando visualización...")
        debug_path = Path("data/results/debug/endpoint_diagnosis")
        debug_path.mkdir(parents=True, exist_ok=True)

        # Visualización 1: Skeleton con endpoints marcados
        vis1 = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        vis1_alpha = vis1.copy()

        # Dibujar skeleton en amarillo
        vis1_alpha[skeleton > 0] = [255, 255, 0]
        vis1 = cv2.addWeighted(vis1, 0.7, vis1_alpha, 0.3, 0)

        # Marcar endpoints (1 vecino) en verde
        for x, y in endpoints_1_neighbor:
            cv2.circle(vis1, (x, y), 10, (0, 255, 0), 2)
            cv2.circle(vis1, (x, y), 3, (0, 255, 0), -1)

        # Marcar bifurcaciones en rojo
        for x, y in junctions:
            cv2.circle(vis1, (x, y), 6, (255, 0, 0), 2)

        cv2.imwrite(str(debug_path / "01_skeleton_endpoints.jpg"),
                   cv2.cvtColor(vis1, cv2.COLOR_RGB2BGR))
        print(f"  ✓ Guardado: {debug_path / '01_skeleton_endpoints.jpg'}")

        # Visualización 2: Curva ordenada con flujo
        if result['success']:
            tracker.visualize_curve(img, result['ordered_points'],
                                  debug_path / "02_ordered_curve.jpg")
            print(f"  ✓ Guardado: {debug_path / '02_ordered_curve.jpg'}")

        # Visualización 3: Máscara y skeleton lado a lado
        vis3 = np.zeros((h, w*2, 3), dtype=np.uint8)
        vis3[:, :w] = cv2.cvtColor(mask, cv2.COLOR_GRAY2BGR)
        vis3[:, w:] = cv2.cvtColor(skeleton * 255, cv2.COLOR_GRAY2BGR)

        cv2.imwrite(str(debug_path / "03_mask_skeleton.jpg"), vis3)
        print(f"  ✓ Guardado: {debug_path / '03_mask_skeleton.jpg'}")

    # Resumen
    print("\n" + "="*80)
    print("RESUMEN")
    print("="*80)
    print(f"Endpoints candidatos (1 vecino): {len(endpoints_1_neighbor)}")
    print(f"Bifurcaciones (3+ vecinos): {len(junctions)}")

    if len(detected_endpoints) == 2:
        print(f"\n✓ CurveTracker detectó 2 endpoints correctamente")
        print(f"  Inicio: {detected_endpoints[0]}")
        print(f"  Final:  {detected_endpoints[1]}")
    elif len(endpoints_1_neighbor) == 2:
        print(f"\n✓ Se encontraron exactamente 2 endpoints")
        print(f"  Endpoint 1: {endpoints_1_neighbor[0]}")
        print(f"  Endpoint 2: {endpoints_1_neighbor[1]}")
    elif len(endpoints_1_neighbor) > 2:
        print(f"\n⚠ Se encontraron {len(endpoints_1_neighbor)} endpoints")
        print(f"  Puede haber bifurcaciones o fragmentación")
    else:
        print(f"\n⚠ Se encontraron {len(endpoints_1_neighbor)} endpoints")
        print(f"  El cable puede formar un loop cerrado o estar muy fragmentado")

    print("="*80)


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1:
        image_path = sys.argv[1]
    else:
        # Usar imagen más reciente por defecto
        image_path = "data/captures/stereo_20251119_175650/left.jpg"

    analyze_endpoints(image_path, save_debug=True)
