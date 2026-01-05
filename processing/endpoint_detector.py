#!/usr/bin/env python3
"""
Detector automático de endpoints (extremos) en máscaras de cables.
Identifica los puntos de inicio y final para el wire tracker.
"""

import cv2
import numpy as np
from typing import Tuple, List, Optional
from scipy import ndimage


class EndpointDetector:
    """Detecta endpoints automáticamente en máscaras de cables."""

    def __init__(self, mask: np.ndarray):
        """
        Args:
            mask: Máscara binaria del cable (255=cable, 0=fondo)
        """
        self.mask = mask.astype(np.uint8)
        self.mask_binary = (self.mask > 127).astype(np.uint8)

    def detect_endpoints(self, method: str = "skeleton") -> Tuple[Tuple[int, int], Tuple[int, int]]:
        """
        Detecta los dos endpoints principales del cable.

        Args:
            method: Método de detección ("skeleton", "contour", or "distance_transform")

        Returns:
            Tupla con (start_point, end_point) en formato (x, y)
        """
        if method == "skeleton":
            return self._detect_endpoints_skeleton()
        elif method == "contour":
            return self._detect_endpoints_contour()
        elif method == "distance_transform":
            return self._detect_endpoints_distance_transform()
        else:
            raise ValueError(f"Método desconocido: {method}")

    def _detect_endpoints_skeleton(self) -> Tuple[Tuple[int, int], Tuple[int, int]]:
        """
        Detecta endpoints usando skeleton y análisis de conectividad.
        Un endpoint tiene exactamente 1 vecino en el skeleton.
        """
        # Crear skeleton
        skeleton = self._create_skeleton()

        # Contar vecinos de cada píxel del skeleton
        kernel = np.ones((3, 3), np.uint8)
        kernel[1, 1] = 0  # No contar el píxel central

        # Convolución para contar vecinos
        neighbors = cv2.filter2D(skeleton.astype(np.uint8), -1, kernel)
        neighbors = neighbors * skeleton  # Solo en píxeles del skeleton

        # Endpoints tienen exactamente 1 vecino
        endpoints = (neighbors == 255).astype(np.uint8)

        # Obtener coordenadas de endpoints
        endpoint_coords = np.column_stack(np.where(endpoints > 0))

        if len(endpoint_coords) < 2:
            # Fallback a método de contornos si no se encontraron endpoints
            print("⚠️ No se encontraron endpoints con skeleton, usando método de contornos...")
            return self._detect_endpoints_contour()

        # Tomar los dos endpoints más alejados entre sí
        if len(endpoint_coords) > 2:
            # Calcular distancias entre todos los pares
            max_dist = 0
            best_pair = (endpoint_coords[0], endpoint_coords[1])

            for i in range(len(endpoint_coords)):
                for j in range(i + 1, len(endpoint_coords)):
                    dist = np.linalg.norm(endpoint_coords[i] - endpoint_coords[j])
                    if dist > max_dist:
                        max_dist = dist
                        best_pair = (endpoint_coords[i], endpoint_coords[j])

            endpoint_coords = np.array(best_pair)

        # Convertir de (y, x) a (x, y)
        start = (int(endpoint_coords[0][1]), int(endpoint_coords[0][0]))
        end = (int(endpoint_coords[1][1]), int(endpoint_coords[1][0]))

        return start, end

    def _detect_endpoints_contour(self) -> Tuple[Tuple[int, int], Tuple[int, int]]:
        """
        Detecta endpoints usando análisis de contornos.
        Los endpoints son los puntos extremos del contorno principal.
        """
        # Encontrar contornos
        contours, _ = cv2.findContours(self.mask_binary * 255,
                                       cv2.RETR_EXTERNAL,
                                       cv2.CHAIN_APPROX_NONE)

        if not contours:
            raise ValueError("No se encontraron contornos en la máscara")

        # Tomar el contorno más grande
        main_contour = max(contours, key=cv2.contourArea)

        # Simplificar contorno para obtener puntos clave
        epsilon = 0.001 * cv2.arcLength(main_contour, True)
        approx = cv2.approxPolyDP(main_contour, epsilon, True)

        # Aplanar puntos
        points = approx.reshape(-1, 2)

        # Encontrar los dos puntos más alejados (endpoints)
        max_dist = 0
        best_pair = (points[0], points[1])

        for i in range(len(points)):
            for j in range(i + 1, len(points)):
                dist = np.linalg.norm(points[i] - points[j])
                if dist > max_dist:
                    max_dist = dist
                    best_pair = (points[i], points[j])

        start = tuple(best_pair[0])
        end = tuple(best_pair[1])

        return start, end

    def _detect_endpoints_distance_transform(self) -> Tuple[Tuple[int, int], Tuple[int, int]]:
        """
        Detecta endpoints usando distance transform.
        Los endpoints están en regiones de alta distancia al borde.
        """
        # Calcular distance transform
        dist_transform = cv2.distanceTransform(self.mask_binary, cv2.DIST_L2, 5)

        # Crear centerline (píxeles de alta distancia)
        dt_max = np.max(dist_transform)
        threshold = dt_max * 0.5
        centerline = (dist_transform >= threshold).astype(np.uint8)

        # Adelgazar centerline
        skeleton = self._thin_image(centerline * 255)

        # Usar método de skeleton sobre este centerline
        temp_detector = EndpointDetector(skeleton)
        return temp_detector._detect_endpoints_skeleton()

    def _create_skeleton(self) -> np.ndarray:
        """Crea skeleton de la máscara."""
        return self._thin_image(self.mask_binary * 255)

    def _thin_image(self, img: np.ndarray) -> np.ndarray:
        """
        Adelgaza imagen binaria usando morfología.
        Alternativa a cv2.ximgproc.thinning que puede no estar disponible.
        """
        # Método 1: Usar cv2.ximgproc si está disponible
        try:
            skeleton = cv2.ximgproc.thinning(img, thinningType=cv2.ximgproc.THINNING_ZHANGSUEN)
            return skeleton
        except (AttributeError, cv2.error):
            pass

        # Método 2: Morfología iterativa
        kernel = cv2.getStructuringElement(cv2.MORPH_CROSS, (3, 3))
        skeleton = np.zeros_like(img)
        temp = img.copy()

        while True:
            eroded = cv2.erode(temp, kernel)
            temp_opened = cv2.dilate(eroded, kernel)
            temp_skeleton = cv2.subtract(temp, temp_opened)
            skeleton = cv2.bitwise_or(skeleton, temp_skeleton)
            temp = eroded.copy()

            if cv2.countNonZero(temp) == 0:
                break

        return skeleton

    def visualize_endpoints(self, start: Tuple[int, int], end: Tuple[int, int],
                           output_path: Optional[str] = None) -> np.ndarray:
        """
        Visualiza los endpoints detectados sobre la máscara.

        Args:
            start: Punto de inicio (x, y)
            end: Punto final (x, y)
            output_path: Ruta para guardar imagen (opcional)

        Returns:
            Imagen visualizada
        """
        # Crear imagen RGB
        vis = cv2.cvtColor(self.mask, cv2.COLOR_GRAY2BGR)

        # Dibujar endpoints
        cv2.circle(vis, start, 10, (0, 255, 0), -1)  # Verde para start
        cv2.circle(vis, end, 10, (0, 0, 255), -1)    # Rojo para end

        # Añadir etiquetas
        cv2.putText(vis, "START", (start[0] + 15, start[1]),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
        cv2.putText(vis, "END", (end[0] + 15, end[1]),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)

        if output_path:
            cv2.imwrite(output_path, vis)
            print(f"Visualización guardada en: {output_path}")

        return vis


def detect_wire_endpoints(mask: np.ndarray,
                         method: str = "skeleton",
                         visualize: bool = False,
                         vis_output_path: Optional[str] = None) -> Tuple[Tuple[int, int], Tuple[int, int]]:
    """
    Función de utilidad para detectar endpoints de un cable.

    Args:
        mask: Máscara binaria del cable
        method: Método de detección ("skeleton", "contour", "distance_transform")
        visualize: Si True, crea visualización
        vis_output_path: Ruta para guardar visualización

    Returns:
        (start_point, end_point) en formato (x, y)
    """
    detector = EndpointDetector(mask)
    start, end = detector.detect_endpoints(method=method)

    if visualize:
        detector.visualize_endpoints(start, end, vis_output_path)

    return start, end


if __name__ == "__main__":
    # Test del detector
    import sys

    if len(sys.argv) < 2:
        print("Uso: python endpoint_detector.py <ruta_mascara>")
        sys.exit(1)

    mask_path = sys.argv[1]
    mask = cv2.imread(mask_path, cv2.IMREAD_GRAYSCALE)

    if mask is None:
        print(f"Error: No se pudo cargar {mask_path}")
        sys.exit(1)

    print(f"Detectando endpoints en {mask_path}...")
    start, end = detect_wire_endpoints(mask, method="skeleton", visualize=True,
                                      vis_output_path="endpoint_detection_result.png")

    print(f"✓ Start: {start}")
    print(f"✓ End: {end}")
    print(f"✓ Distancia: {np.linalg.norm(np.array(start) - np.array(end)):.1f} px")
