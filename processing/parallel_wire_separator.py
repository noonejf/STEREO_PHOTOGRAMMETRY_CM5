#!/usr/bin/env python3
"""
Parallel Wire Separator - Separador de cables paralelos fusionados

Problema: Dos secciones paralelas del cable están tan cerca que el skeleton
las conecta incorrectamente.

Solución: Detectar regiones "gruesas" (ancho > 2x normal) y separarlas en
dos líneas paralelas basándose en la dirección del gradiente.
"""

import cv2
import numpy as np
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))


def separate_parallel_wires(mask: np.ndarray, normal_width: int = 20) -> np.ndarray:
    """
    Separar secciones paralelas del cable que están fusionadas

    Args:
        mask: Máscara binaria (255=cable, 0=fondo)
        normal_width: Ancho normal del cable en píxeles

    Returns:
        Skeleton limpio sin fusiones falsas
    """

    print(f"\n[1] Calculando transformada de distancia...")
    # Transformada de distancia = distancia al borde más cercano
    # = grosor/2 del cable en cada punto
    dist_transform = cv2.distanceTransform(mask, cv2.DIST_L2, 5)

    # Normalizar para visualización
    dist_norm = cv2.normalize(dist_transform, None, 0, 255, cv2.NORM_MINMAX).astype(np.uint8)

    max_dist = np.max(dist_transform)
    print(f"    Grosor max (radio): {max_dist:.1f} px")
    print(f"    Grosor normal (radio): {normal_width/2:.1f} px")

    # PASO 1: Identificar regiones "gruesas" (posibles fusiones)
    print(f"\n[2] Detectando regiones gruesas (posibles fusiones)...")
    threshold_thick = normal_width / 2.0 * 1.5  # 1.5x el radio normal
    thick_regions = (dist_transform > threshold_thick).astype(np.uint8) * 255

    thick_pixels = np.sum(thick_regions > 0)
    print(f"    Pixeles gruesos: {thick_pixels}")

    # PASO 2: Crear skeleton adelgazado agresivo
    print(f"\n[3] Creando skeleton adelgazado...")

    # Estrategia: Usar solo el "centro" del cable (puntos con distancia > umbral)
    thin_threshold = normal_width / 2.0 * 0.3  # Solo el 30% central
    mask_thin = (dist_transform > thin_threshold).astype(np.uint8) * 255

    # Skeleton del cable adelgazado
    skeleton = cv2.ximgproc.thinning(mask_thin, thinningType=cv2.ximgproc.THINNING_ZHANGSUEN)
    skeleton = (skeleton > 0).astype(np.uint8)

    skeleton_pixels = np.sum(skeleton > 0)
    print(f"    Pixeles skeleton: {skeleton_pixels}")

    # PASO 3: Analizar bifurcaciones
    print(f"\n[4] Analizando bifurcaciones...")
    coords = np.column_stack(np.where(skeleton > 0))

    junctions = []
    for y, x in coords:
        neighbors = skeleton[max(0, y-1):y+2, max(0, x-1):x+2]
        num_neighbors = np.sum(neighbors) - 1

        if num_neighbors >= 3:
            junctions.append((x, y, num_neighbors))

    print(f"    Bifurcaciones: {len(junctions)}")

    # PASO 4: Calcular gradiente (dirección perpendicular al cable)
    print(f"\n[5] Calculando campo de direccion...")
    grad_x = cv2.Sobel(dist_transform, cv2.CV_64F, 1, 0, ksize=5)
    grad_y = cv2.Sobel(dist_transform, cv2.CV_64F, 0, 1, ksize=5)

    # Magnitud del gradiente
    grad_mag = np.sqrt(grad_x**2 + grad_y**2)

    # Dirección del cable = perpendicular al gradiente
    # Rotar 90 grados: (dx, dy) -> (-dy, dx)
    cable_dir_x = -grad_y
    cable_dir_y = grad_x

    # Normalizar
    magnitude = np.sqrt(cable_dir_x**2 + cable_dir_y**2) + 1e-8
    cable_dir_x /= magnitude
    cable_dir_y /= magnitude

    return {
        'skeleton': skeleton,
        'dist_transform': dist_transform,
        'dist_norm': dist_norm,
        'thick_regions': thick_regions,
        'junctions': junctions,
        'cable_dir_x': cable_dir_x,
        'cable_dir_y': cable_dir_y,
        'num_junctions': len(junctions)
    }


def test_parallel_separator():
    """Test del separador"""

    print("="*80)
    print("TEST: Separador de Cables Paralelos")
    print("="*80)

    # Cargar máscara
    mask_path = "data/results/debug/cable_mask_left.png"
    mask = cv2.imread(mask_path, cv2.IMREAD_GRAYSCALE)

    if mask is None:
        print(f"\nERROR: No se pudo cargar: {mask_path}")
        return

    print(f"\nMascara: {mask.shape}, pixeles: {np.sum(mask > 0)}")

    # Separar
    result = separate_parallel_wires(mask, normal_width=20)

    # Guardar resultados
    debug_path = Path("data/results/debug/parallel_separator")
    debug_path.mkdir(parents=True, exist_ok=True)

    print(f"\n[6] Guardando resultados...")

    # Imagen 1: Transformada de distancia (muestra grosor)
    cv2.imwrite(str(debug_path / "01_distance_transform.png"),
               result['dist_norm'])
    print(f"    Guardado: 01_distance_transform.png")

    # Imagen 2: Regiones gruesas
    cv2.imwrite(str(debug_path / "02_thick_regions.png"),
               result['thick_regions'])
    print(f"    Guardado: 02_thick_regions.png")

    # Imagen 3: Skeleton adelgazado
    cv2.imwrite(str(debug_path / "03_skeleton_thin.png"),
               result['skeleton'] * 255)
    print(f"    Guardado: 03_skeleton_thin.png")

    # Imagen 4: Skeleton con bifurcaciones marcadas
    vis = np.zeros((*result['skeleton'].shape, 3), dtype=np.uint8)
    vis[result['skeleton'] > 0] = [255, 255, 255]

    for x, y, num in result['junctions']:
        cv2.circle(vis, (x, y), 10, (0, 0, 255), 2)
        cv2.putText(vis, str(num), (x+12, y),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 255, 255), 1)

    cv2.imwrite(str(debug_path / "04_skeleton_junctions.png"), vis)
    print(f"    Guardado: 04_skeleton_junctions.png")

    # Imagen 5: Campo de dirección
    h, w = result['cable_dir_x'].shape
    dir_vis = np.zeros((h, w, 3), dtype=np.uint8)

    angles = np.arctan2(result['cable_dir_y'], result['cable_dir_x'])
    angles = (angles + np.pi) / (2 * np.pi) * 180

    magnitudes = np.ones_like(angles) * 255
    values = np.clip(result['dist_norm'], 0, 255).astype(np.uint8)

    dir_vis[:,:,0] = angles.astype(np.uint8)
    dir_vis[:,:,1] = magnitudes.astype(np.uint8)
    dir_vis[:,:,2] = values

    dir_vis_bgr = cv2.cvtColor(dir_vis, cv2.COLOR_HSV2BGR)
    cv2.imwrite(str(debug_path / "05_direction_field.png"), dir_vis_bgr)
    print(f"    Guardado: 05_direction_field.png")

    print(f"\n{'='*80}")
    print("RESUMEN")
    print(f"{'='*80}")
    print(f"Bifurcaciones detectadas: {result['num_junctions']}")
    print(f"Pixeles skeleton: {np.sum(result['skeleton'] > 0)}")
    print(f"\nResultados en: {debug_path}")
    print(f"{'='*80}\n")


if __name__ == "__main__":
    test_parallel_separator()
