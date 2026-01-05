#!/usr/bin/env python3
"""
Fix para mejorar detección de endpoints
"""

import cv2
import numpy as np
from pathlib import Path

def improved_endpoint_detection(skeleton: np.ndarray, mask: np.ndarray):
    """
    Detectar los 2 extremos verdaderos del cable usando múltiples estrategias

    Estrategias:
    1. Encontrar TODOS los puntos con 1 vecino
    2. Si hay más de 2, elegir los 2 más alejados entre sí
    3. Validar que estén cerca del borde de la máscara original
    """

    coords = np.column_stack(np.where(skeleton > 0))

    if len(coords) < 2:
        return None

    # PASO 1: Encontrar candidatos (puntos con 1 vecino)
    endpoints_1_neighbor = []

    for y, x in coords:
        neighbors = skeleton[max(0, y-1):y+2, max(0, x-1):x+2]
        num_neighbors = np.sum(neighbors) - 1

        if num_neighbors == 1:
            endpoints_1_neighbor.append((x, y))

    print(f"  Candidatos con 1 vecino: {len(endpoints_1_neighbor)}")

    # Si no hay candidatos, usar estrategia de fallback (extremos geométricos)
    if len(endpoints_1_neighbor) == 0:
        print("  No se encontraron endpoints, usando fallback geométrico")
        coords_xy = coords[:, [1, 0]]  # Convertir a (x, y)

        y_min_idx = np.argmin(coords_xy[:, 1])
        y_max_idx = np.argmax(coords_xy[:, 1])
        x_min_idx = np.argmin(coords_xy[:, 0])
        x_max_idx = np.argmax(coords_xy[:, 0])

        candidates = [
            tuple(coords_xy[y_min_idx]),
            tuple(coords_xy[y_max_idx]),
            tuple(coords_xy[x_min_idx]),
            tuple(coords_xy[x_max_idx])
        ]

        # Eliminar duplicados
        candidates = list(set(candidates))
        endpoints_1_neighbor = candidates

    # PASO 2: Si hay exactamente 2, usarlos directamente
    if len(endpoints_1_neighbor) == 2:
        print(f"  OK Exactamente 2 endpoints detectados")
        return endpoints_1_neighbor[0], endpoints_1_neighbor[1]

    # PASO 3: Si hay más de 2, elegir los 2 más alejados
    if len(endpoints_1_neighbor) > 2:
        print(f"  Múltiples candidatos, eligiendo los 2 más alejados...")
        max_dist = 0
        best_pair = None

        for i, p1 in enumerate(endpoints_1_neighbor):
            for j, p2 in enumerate(endpoints_1_neighbor[i+1:], i+1):
                dist = np.linalg.norm(np.array(p1) - np.array(p2))
                if dist > max_dist:
                    max_dist = dist
                    best_pair = (p1, p2)

        if best_pair:
            print(f"  OK Par mas alejado: {max_dist:.1f} px")
            return best_pair[0], best_pair[1]

    return None


def validate_endpoints_with_mask_boundary(endpoints, skeleton, mask):
    """
    Validar que los endpoints estén cerca del borde de la máscara original

    Los endpoints verdaderos deben estar en el perímetro de la máscara
    """

    # Calcular borde de la máscara
    mask_edge = cv2.Canny(mask, 50, 150)
    edge_pixels = np.column_stack(np.where(mask_edge > 0))

    if len(edge_pixels) == 0:
        return endpoints

    edge_pixels_xy = edge_pixels[:, [1, 0]]  # (x, y)

    validated = []
    for ep_x, ep_y in endpoints:
        # Distancia al borde más cercano
        distances = np.sqrt(np.sum((edge_pixels_xy - np.array([ep_x, ep_y]))**2, axis=1))
        min_dist = np.min(distances)

        print(f"  Endpoint ({ep_x}, {ep_y}) -> distancia al borde: {min_dist:.1f} px")

        # Endpoints verdaderos deben estar muy cerca del borde (< 5 píxeles)
        if min_dist < 5:
            validated.append((ep_x, ep_y))

    return validated if len(validated) >= 2 else endpoints


def test_improved_detection(image_path: str):
    """Test de la detección mejorada"""

    print("="*80)
    print("TEST: Detección Mejorada de Endpoints")
    print("="*80)
    print(f"\nImagen: {image_path}\n")

    # Cargar imagen
    img = cv2.imread(image_path)
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    # Crear máscara simple
    edges = cv2.Canny(gray, 50, 150)
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
    edges_dilated = cv2.dilate(edges, kernel, iterations=2)
    edges_closed = cv2.morphologyEx(edges_dilated, cv2.MORPH_CLOSE, kernel, iterations=3)

    contours, _ = cv2.findContours(edges_closed, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    mask = np.zeros_like(gray)
    if len(contours) > 0:
        largest = max(contours, key=cv2.contourArea)
        cv2.drawContours(mask, [largest], -1, 255, -1)

    # Crear skeleton
    print("[1] Creando skeleton...")
    mask_binary = (mask > 0).astype(np.uint8)
    skeleton = cv2.ximgproc.thinning(mask_binary * 255,
                                     thinningType=cv2.ximgproc.THINNING_ZHANGSUEN)
    skeleton = (skeleton > 0).astype(np.uint8)
    print(f"    Píxeles: {np.sum(skeleton > 0)}")

    # Detectar endpoints CON LA FUNCIÓN MEJORADA
    print("\n[2] Detectando endpoints (MEJORADO)...")
    result = improved_endpoint_detection(skeleton, mask)

    if result:
        start_point, end_point = result
        print(f"\nOK ENDPOINTS DETECTADOS:")
        print(f"  Inicio: {start_point}")
        print(f"  Final:  {end_point}")

        dist = np.linalg.norm(np.array(start_point) - np.array(end_point))
        print(f"  Distancia: {dist:.1f} px")

        # Validar con borde de máscara
        print("\n[3] Validando con borde de máscara...")
        validated = validate_endpoints_with_mask_boundary(
            [start_point, end_point], skeleton, mask
        )

        if len(validated) >= 2:
            print(f"  OK Ambos endpoints validados")
        else:
            print(f"  WARNING Solo {len(validated)} endpoints validados")

        # Visualizar
        print("\n[4] Guardando visualización...")
        debug_path = Path("data/results/debug/improved_endpoints")
        debug_path.mkdir(parents=True, exist_ok=True)

        vis = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        vis_alpha = vis.copy()
        vis_alpha[skeleton > 0] = [255, 255, 0]
        vis = cv2.addWeighted(vis, 0.7, vis_alpha, 0.3, 0)

        # Marcar endpoints
        cv2.circle(vis, start_point, 15, (0, 255, 0), 3)
        cv2.circle(vis, start_point, 5, (0, 255, 0), -1)
        cv2.putText(vis, "START", (start_point[0]+20, start_point[1]),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)

        cv2.circle(vis, end_point, 15, (255, 0, 255), 3)
        cv2.circle(vis, end_point, 5, (255, 0, 255), -1)
        cv2.putText(vis, "END", (end_point[0]+20, end_point[1]),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 0, 255), 2)

        # Línea entre endpoints
        cv2.line(vis, start_point, end_point, (255, 0, 255), 2)

        out_path = debug_path / "improved_endpoints.jpg"
        cv2.imwrite(str(out_path), cv2.cvtColor(vis, cv2.COLOR_RGB2BGR))
        print(f"    Guardado: {out_path}")

    else:
        print("\nERROR No se pudieron detectar endpoints")

    print("\n" + "="*80)


if __name__ == "__main__":
    import sys

    image_path = "data/captures/stereo_20251119_175650/left.jpg"
    if len(sys.argv) > 1:
        image_path = sys.argv[1]

    test_improved_detection(image_path)
