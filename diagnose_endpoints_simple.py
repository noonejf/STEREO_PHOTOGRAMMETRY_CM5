#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Diagnóstico simple de detección de extremos
"""

import cv2
import numpy as np
from pathlib import Path
import sys
import os

# Force UTF-8 for Windows console
if sys.platform == 'win32':
    os.environ['PYTHONIOENCODING'] = 'utf-8'

def detect_wire_mask_simple(image_path: str) -> np.ndarray:
    """Detectar cable usando método simple"""
    img = cv2.imread(image_path)
    if img is None:
        raise ValueError(f"No se pudo cargar imagen: {image_path}")

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    edges = cv2.Canny(gray, 50, 150)
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
    edges_dilated = cv2.dilate(edges, kernel, iterations=2)
    edges_closed = cv2.morphologyEx(edges_dilated, cv2.MORPH_CLOSE, kernel, iterations=3)

    contours, _ = cv2.findContours(edges_closed, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    mask = np.zeros_like(gray)
    if len(contours) > 0:
        largest = max(contours, key=cv2.contourArea)
        cv2.drawContours(mask, [largest], -1, 255, -1)

    return mask, img


def find_endpoints(skeleton: np.ndarray):
    """Encontrar endpoints (1 vecino)"""
    coords = np.column_stack(np.where(skeleton > 0))

    endpoints = []
    for y, x in coords:
        neighbors = skeleton[max(0, y-1):y+2, max(0, x-1):x+2]
        num_neighbors = np.sum(neighbors) - 1

        if num_neighbors == 1:
            endpoints.append((x, y))

    return endpoints


def analyze_simple(image_path: str):
    """Análisis simple sin logger"""

    print("="*80)
    print("DIAGNOSTICO DE ENDPOINTS - Version Simple")
    print("="*80)
    print(f"\nImagen: {image_path}\n")

    # Cargar y detectar
    mask, img = detect_wire_mask_simple(image_path)
    h, w = img.shape[:2]

    print(f"[1] Creando skeleton...")
    mask_binary = (mask > 0).astype(np.uint8)
    skeleton = cv2.ximgproc.thinning(mask_binary * 255,
                                     thinningType=cv2.ximgproc.THINNING_ZHANGSUEN)
    skeleton = (skeleton > 0).astype(np.uint8)
    pixels = np.sum(skeleton > 0)
    print(f"    Pixeles: {pixels}")

    print(f"\n[2] Buscando endpoints (1 vecino)...")
    endpoints = find_endpoints(skeleton)
    print(f"    Encontrados: {len(endpoints)}")

    for i, (x, y) in enumerate(endpoints):
        print(f"    [{i}] ({x:4d}, {y:4d})")

    # Distancias
    if len(endpoints) >= 2:
        print(f"\n[3] Distancias:")
        for i, p1 in enumerate(endpoints):
            for j, p2 in enumerate(endpoints[i+1:], i+1):
                dist = np.linalg.norm(np.array(p1) - np.array(p2))
                print(f"    [{i}] <-> [{j}]: {dist:6.1f} px")

        # Encontrar los 2 mas alejados
        print(f"\n[4] Los 2 extremos mas alejados:")
        max_dist = 0
        best_pair = None
        for i, p1 in enumerate(endpoints):
            for j, p2 in enumerate(endpoints[i+1:], i+1):
                dist = np.linalg.norm(np.array(p1) - np.array(p2))
                if dist > max_dist:
                    max_dist = dist
                    best_pair = (i, j, p1, p2)

        if best_pair:
            i, j, p1, p2 = best_pair
            print(f"    [{i}] ({p1[0]:4d}, {p1[1]:4d})")
            print(f"    [{j}] ({p2[0]:4d}, {p2[1]:4d})")
            print(f"    Distancia: {max_dist:.1f} px")

    # Visualizar
    print(f"\n[5] Guardando visualizacion...")
    debug_path = Path("data/results/debug/endpoint_diagnosis")
    debug_path.mkdir(parents=True, exist_ok=True)

    # Imagen 1: Skeleton + endpoints
    vis1 = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
    vis1_alpha = vis1.copy()
    vis1_alpha[skeleton > 0] = [255, 255, 0]  # Amarillo
    vis1 = cv2.addWeighted(vis1, 0.7, vis1_alpha, 0.3, 0)

    # Marcar todos los endpoints
    for i, (x, y) in enumerate(endpoints):
        cv2.circle(vis1, (x, y), 12, (0, 255, 0), 2)
        cv2.circle(vis1, (x, y), 4, (0, 255, 0), -1)
        cv2.putText(vis1, str(i), (x+15, y), cv2.FONT_HERSHEY_SIMPLEX,
                   0.6, (255, 255, 255), 2)

    # Marcar el par mas alejado
    if len(endpoints) >= 2 and best_pair:
        i, j, p1, p2 = best_pair
        cv2.circle(vis1, p1, 20, (255, 0, 255), 3)  # Magenta
        cv2.circle(vis1, p2, 20, (255, 0, 255), 3)
        cv2.line(vis1, p1, p2, (255, 0, 255), 2)

    out_path = debug_path / "skeleton_with_endpoints.jpg"
    cv2.imwrite(str(out_path), cv2.cvtColor(vis1, cv2.COLOR_RGB2BGR))
    print(f"    Guardado: {out_path}")

    # Imagen 2: Solo skeleton
    vis2 = np.zeros((h, w, 3), dtype=np.uint8)
    vis2[skeleton > 0] = [255, 255, 255]

    for i, (x, y) in enumerate(endpoints):
        cv2.circle(vis2, (x, y), 10, (0, 255, 0), -1)
        cv2.putText(vis2, str(i), (x+12, y), cv2.FONT_HERSHEY_SIMPLEX,
                   0.5, (0, 255, 255), 2)

    out_path2 = debug_path / "skeleton_clean.jpg"
    cv2.imwrite(str(out_path2), vis2)
    print(f"    Guardado: {out_path2}")

    print("\n" + "="*80)
    print("COMPLETADO")
    print("="*80)


if __name__ == "__main__":
    image_path = "data/captures/stereo_20251119_175650/left.jpg"
    if len(sys.argv) > 1:
        image_path = sys.argv[1]

    analyze_simple(image_path)
