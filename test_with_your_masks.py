#!/usr/bin/env python3
"""
Test de deteccion de endpoints usando TUS mascaras manuales
"""

import cv2
import numpy as np
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent))

from processing.curve_tracker import CurveTracker
from utils.logger import get_logger

logger = get_logger(__name__)


def test_with_manual_masks():
    """
    Test usando las mascaras manuales que ya tienes creadas
    """

    print("="*80)
    print("TEST: Deteccion de Endpoints con MASCARAS MANUALES")
    print("="*80)

    # Rutas a TUS archivos
    left_img_path = "data/captures/stereo_20251119_175650/left.jpg"
    left_mask_path = "data/results/debug/cable_mask_left.png"
    right_mask_path = "data/results/debug/cable_mask_right.png"

    print(f"\nCargando archivos:")
    print(f"  Imagen:       {left_img_path}")
    print(f"  Mascara LEFT:  {left_mask_path}")
    print(f"  Mascara RIGHT: {right_mask_path}")

    # Cargar imagen original
    left_img = cv2.imread(left_img_path)
    if left_img is None:
        print(f"\nERROR: No se pudo cargar imagen: {left_img_path}")
        return

    # Cargar TU mascara manual
    left_mask = cv2.imread(left_mask_path, cv2.IMREAD_GRAYSCALE)
    if left_mask is None:
        print(f"\nERROR: No se pudo cargar mascara: {left_mask_path}")
        return

    right_mask = cv2.imread(right_mask_path, cv2.IMREAD_GRAYSCALE)
    if right_mask is None:
        print(f"\nERROR: No se pudo cargar mascara: {right_mask_path}")
        return

    h, w = left_mask.shape
    print(f"\nResolucion: {w}x{h}")
    print(f"Pixeles de cable en mascara LEFT:  {np.sum(left_mask > 0)}")
    print(f"Pixeles de cable en mascara RIGHT: {np.sum(right_mask > 0)}")

    # USAR CURVE TRACKER con TU mascara manual
    print("\n[1] Extrayendo skeleton y endpoints de MASCARA LEFT...")
    tracker = CurveTracker()
    result = tracker.extract_and_order_skeleton(left_mask, sample_spacing=3)

    if not result['success']:
        print(f"\nERROR: {result['error']}")
        return

    print(f"\n  OK Curva extraida: {result['num_points']} puntos")
    print(f"  Endpoints detectados: {result['endpoints']}")

    start_point, end_point = result['endpoints']
    dist = np.linalg.norm(np.array(start_point) - np.array(end_point))
    print(f"  Distancia entre endpoints: {dist:.1f} px")

    # Visualizar
    print("\n[2] Guardando visualizaciones...")
    debug_path = Path("data/results/debug/manual_mask_test")
    debug_path.mkdir(parents=True, exist_ok=True)

    # Visualizacion 1: Mascara original
    cv2.imwrite(str(debug_path / "01_your_mask.png"), left_mask)
    print(f"  Guardado: {debug_path / '01_your_mask.png'}")

    # Visualizacion 2: Skeleton sobre mascara
    vis_mask = cv2.cvtColor(left_mask, cv2.COLOR_GRAY2BGR)
    skeleton = result['skeleton']
    vis_mask[skeleton > 0] = [0, 255, 255]  # Cyan para skeleton

    # Marcar endpoints
    cv2.circle(vis_mask, start_point, 12, (0, 255, 0), 3)  # Verde
    cv2.circle(vis_mask, end_point, 12, (255, 0, 255), 3)  # Magenta
    cv2.putText(vis_mask, "START", (start_point[0]+15, start_point[1]),
               cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
    cv2.putText(vis_mask, "END", (end_point[0]+15, end_point[1]),
               cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 0, 255), 2)

    cv2.imwrite(str(debug_path / "02_skeleton_on_mask.png"), vis_mask)
    print(f"  Guardado: {debug_path / '02_skeleton_on_mask.png'}")

    # Visualizacion 3: Curva ordenada con flujo de color sobre imagen original
    tracker.visualize_curve(left_img, result['ordered_points'],
                          debug_path / "03_curve_flow_on_image.jpg")
    print(f"  Guardado: {debug_path / '03_curve_flow_on_image.jpg'}")

    # Visualizacion 4: Endpoints sobre imagen original
    vis_img = left_img.copy()
    cv2.circle(vis_img, start_point, 15, (0, 255, 0), 3)
    cv2.circle(vis_img, start_point, 5, (0, 255, 0), -1)
    cv2.circle(vis_img, end_point, 15, (255, 0, 255), 3)
    cv2.circle(vis_img, end_point, 5, (255, 0, 255), -1)
    cv2.line(vis_img, start_point, end_point, (255, 255, 0), 2)
    cv2.putText(vis_img, "START", (start_point[0]+20, start_point[1]),
               cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)
    cv2.putText(vis_img, "END", (end_point[0]+20, end_point[1]),
               cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 0, 255), 2)

    cv2.imwrite(str(debug_path / "04_endpoints_on_image.jpg"), vis_img)
    print(f"  Guardado: {debug_path / '04_endpoints_on_image.jpg'}")

    print("\n" + "="*80)
    print("RESULTADO")
    print("="*80)
    print(f"Usando TU mascara manual:")
    print(f"  Skeleton: {np.sum(skeleton > 0)} pixeles")
    print(f"  Curva ordenada: {result['num_points']} puntos")
    print(f"  Endpoint START: {start_point}")
    print(f"  Endpoint END:   {end_point}")
    print(f"  Distancia:      {dist:.1f} px")
    print(f"\nVisualizaciones guardadas en: {debug_path}")
    print("="*80)


if __name__ == "__main__":
    test_with_manual_masks()
