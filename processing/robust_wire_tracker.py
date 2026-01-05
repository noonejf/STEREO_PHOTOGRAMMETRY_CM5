#!/usr/bin/env python3
"""
Robust Wire Tracker - Sistema robusto de tracking pixel-a-pixel.

Estrategia:
1. Distance Transform para encontrar centerline (esqueleto natural)
2. Tracking pixel-a-pixel en el centerline (como A*/Dijkstra)
3. Marcado de área de influencia: cada pixel del centerline "posee" los píxeles
   de cuerda cercanos basándose en el distance transform
4. Detección robusta de intersecciones analizando topología local
5. Backtracking inteligente con memoria de decisiones
"""

import cv2
import numpy as np
import matplotlib.pyplot as plt
from typing import List, Tuple, Dict, Optional, Set
from dataclasses import dataclass
from collections import deque
from scipy import ndimage


@dataclass
class IntersectionPoint:
    """Punto de intersección/bifurcación con múltiples direcciones."""
    location: Tuple[int, int]
    directions: List[Tuple[int, int]]  # Vectores de dirección normalizados
    chosen_index: int
    path_index: int  # Índice en el path donde ocurrió la decisión


class RobustWireTracker:
    """Tracker robusto que recorre pixel-a-pixel el centerline de la cuerda."""

    def __init__(self, mask: np.ndarray, start: Tuple[int, int], end: Tuple[int, int]):
        self.mask = mask.astype(np.uint8)
        self.start = start
        self.end = end

        # Estado del tracking
        self.path: List[Tuple[int, int]] = []
        self.visited_centerline = np.zeros_like(mask, dtype=np.uint8)
        self.visited_area = np.zeros_like(mask, dtype=np.uint8)
        self.intersections: List[IntersectionPoint] = []

        # --- PASO 1: Calcular Distance Transform y Centerline ---
        print("Calculando Distance Transform...")
        self.distance_transform = cv2.distanceTransform(mask, cv2.DIST_L2, 5)

        # Normalizar para visualización
        self.dt_normalized = cv2.normalize(self.distance_transform, None, 0, 255, cv2.NORM_MINMAX).astype(np.uint8)

        # Calcular centerline (píxeles de máxima distancia local)
        self.centerline = self._compute_centerline()

        print(f"Centerline: {np.sum(self.centerline > 0)} píxeles")
        print(f"Máscara total: {np.sum(mask > 0)} píxeles")

        # --- PARÁMETROS ---
        self.step_size = 1  # Pixel a pixel en el centerline
        self.search_radius = 15  # Radio para buscar siguiente punto
        self.intersection_threshold = 4  # Mínimo de direcciones para considerar intersección (más estricto)

        # Estadísticas
        self.total_mask_pixels = np.sum(mask > 0)
        self.total_centerline_pixels = np.sum(self.centerline > 0)

    def _compute_centerline(self) -> np.ndarray:
        """
        Calcula el centerline usando Distance Transform.
        El centerline es la "columna vertebral" de píxeles de alta distancia en la cuerda.
        """
        # Método: Píxeles localmente máximos en distance transform
        dt = self.distance_transform.copy()

        # Umbral balanceado: mantener píxeles centrales (al menos 30% del máximo)
        dt_max = np.max(dt)
        threshold = dt_max * 0.3
        centerline = (dt >= threshold).astype(np.uint8) * 255

        # Adelgazar agresivamente para obtener línea de 1-2 píxeles
        kernel = np.ones((3, 3), np.uint8)
        centerline_thin = cv2.morphologyEx(centerline, cv2.MORPH_CLOSE, kernel)

        # Aplicar erosión iterativa para adelgazar más
        kernel_small = np.array([[0, 1, 0], [1, 1, 1], [0, 1, 0]], dtype=np.uint8)
        centerline_thin = cv2.erode(centerline_thin, kernel_small, iterations=2)

        # Eliminar píxeles aislados (ruido)
        centerline_thin = cv2.morphologyEx(centerline_thin, cv2.MORPH_OPEN, kernel_small)

        return centerline_thin

    def track_wire(self, max_iterations: int = 50000) -> Dict:
        """Recorrido principal del wire."""
        print("\n" + "="*70)
        print("ROBUST WIRE TRACKER - Pixel-a-pixel en Centerline")
        print("="*70)

        # Inicializar desde el start
        current = self._snap_to_centerline(self.start)
        if current is None:
            print("[ERROR] Start point no está en centerline")
            return {'success': False, 'path': [], 'coverage': 0.0}

        self.path = [current]
        self._mark_visited(current)

        iteration = 0
        stuck_count = 0

        while iteration < max_iterations:
            iteration += 1

            # 1. Verificar llegada al END
            dist_to_end = np.linalg.norm(np.array(current) - np.array(self.end))
            if dist_to_end < self.search_radius:
                self.path.append(self.end)
                self._mark_visited(self.end)
                print(f"\n[OK] LLEGADA AL END en iteración {iteration}")
                break

            # 2. Encontrar vecinos en el centerline
            neighbors = self._find_centerline_neighbors(current)

            # 3. Filtrar vecinos ya visitados
            unvisited = [n for n in neighbors if self.visited_centerline[n[1], n[0]] == 0]

            # 4. Análisis de la situación
            if len(unvisited) == 0:
                # Sin vecinos no visitados: BACKTRACKING
                if self._perform_backtracking():
                    current = self.path[-1]
                    stuck_count = 0
                    if iteration % 100 == 0:
                        print(f"  [<] Backtracking en iter {iteration}")
                    continue
                else:
                    print(f"\n[!] ATASCADO: No hay más caminos. Iter {iteration}")
                    break

            elif len(unvisited) == 1:
                # Camino único: seguir
                next_point = unvisited[0]
                stuck_count = 0

            else:
                # Múltiples opciones: INTERSECCIÓN
                next_point = self._handle_intersection(current, unvisited)
                stuck_count = 0

            # 5. Avanzar
            self.path.append(next_point)
            current = next_point
            self._mark_visited(current)

            # 6. Logging
            if iteration % 500 == 0:
                cov = self._compute_coverage()
                print(f"  Iter {iteration}: Path={len(self.path)} | Cov={cov*100:.1f}%")

            # 7. Detectar estancamiento
            if len(self.path) > 100:
                recent = self.path[-50:]
                if len(set(recent)) < 10:  # Dando vueltas en círculo
                    stuck_count += 1
                    if stuck_count > 20:
                        print(f"\n[!] ESTANCADO en círculo. Iter {iteration}")
                        break

        # Resultados finales
        final_coverage = self._compute_coverage()
        centerline_coverage = self._compute_centerline_coverage()

        print(f"\n[FIN]")
        print(f"  Path length: {len(self.path)} puntos")
        print(f"  Cobertura de área: {final_coverage*100:.1f}%")
        print(f"  Cobertura de centerline: {centerline_coverage*100:.1f}%")
        print(f"  Intersecciones detectadas: {len(self.intersections)}")

        return {
            'success': True,
            'path': self.path,
            'coverage': final_coverage,
            'centerline_coverage': centerline_coverage,
            'intersections': len(self.intersections)
        }

    def _snap_to_centerline(self, point: Tuple[int, int]) -> Optional[Tuple[int, int]]:
        """Encuentra el punto más cercano en el centerline."""
        x, y = point

        # Probar con radios incrementales
        for search_r in [20, 40, 60, 100]:
            y_min = max(0, y - search_r)
            y_max = min(self.centerline.shape[0], y + search_r)
            x_min = max(0, x - search_r)
            x_max = min(self.centerline.shape[1], x + search_r)

            roi = self.centerline[y_min:y_max, x_min:x_max]
            ys, xs = np.where(roi > 0)

            if len(xs) > 0:
                # Encontrar el más cercano
                global_xs = xs + x_min
                global_ys = ys + y_min
                dists = np.hypot(global_xs - x, global_ys - y)
                min_idx = np.argmin(dists)

                snapped = (int(global_xs[min_idx]), int(global_ys[min_idx]))
                print(f"  Snapped {point} -> {snapped} (dist: {dists[min_idx]:.1f}px, radius: {search_r})")
                return snapped

        # Si no encontró nada, buscar en toda la imagen
        ys, xs = np.where(self.centerline > 0)
        if len(xs) == 0:
            print(f"  [WARNING] No centerline pixels found at all!")
            return None

        dists = np.hypot(xs - x, ys - y)
        min_idx = np.argmin(dists)
        snapped = (int(xs[min_idx]), int(ys[min_idx]))
        print(f"  Snapped {point} -> {snapped} (dist: {dists[min_idx]:.1f}px, global search)")
        return snapped

    def _find_centerline_neighbors(self, current: Tuple[int, int]) -> List[Tuple[int, int]]:
        """Encuentra vecinos en el centerline dentro del search_radius."""
        x, y = current
        search_r = self.search_radius

        y_min = max(0, y - search_r)
        y_max = min(self.centerline.shape[0], y + search_r)
        x_min = max(0, x - search_r)
        x_max = min(self.centerline.shape[1], x + search_r)

        roi = self.centerline[y_min:y_max, x_min:x_max]
        ys, xs = np.where(roi > 0)

        neighbors = []
        for nx, ny in zip(xs + x_min, ys + y_min):
            dist = np.hypot(nx - x, ny - y)
            if self.step_size <= dist <= search_r:
                # Verificar conectividad en el centerline
                if self._check_centerline_connectivity(current, (int(nx), int(ny))):
                    neighbors.append((int(nx), int(ny)))

        return neighbors

    def _check_centerline_connectivity(self, p1: Tuple[int, int], p2: Tuple[int, int]) -> bool:
        """Verifica que hay camino en centerline entre p1 y p2."""
        x1, y1 = p1
        x2, y2 = p2
        dist = np.hypot(x2 - x1, y2 - y1)

        if dist < 2:
            return True

        # Samplear puntos a lo largo de la línea
        steps = int(dist * 2)
        for i in range(steps + 1):
            t = i / steps
            x = int(x1 + (x2 - x1) * t)
            y = int(y1 + (y2 - y1) * t)

            if not (0 <= y < self.mask.shape[0] and 0 <= x < self.mask.shape[1]):
                return False

            # Debe haber máscara (no necesariamente centerline exacto)
            if self.mask[y, x] == 0:
                return False

        return True

    def _handle_intersection(self, current: Tuple[int, int], candidates: List[Tuple[int, int]]) -> Tuple[int, int]:
        """
        Maneja una intersección con múltiples opciones.
        Analiza direcciones y prioriza según momentum y distancia al END.
        """
        # Calcular direcciones de cada candidato
        directions = []
        current_arr = np.array(current, dtype=float)

        for cand in candidates:
            cand_arr = np.array(cand, dtype=float)
            direction = cand_arr - current_arr
            norm = np.linalg.norm(direction)
            if norm > 0:
                direction = direction / norm
            directions.append(direction)

        # Agrupar direcciones similares (umbral de ángulo)
        groups = self._group_directions(candidates, directions)

        if len(groups) >= self.intersection_threshold:
            print(f"  [X] Intersección en {current} con {len(groups)} direcciones")

        # Calcular momentum (dirección reciente del path)
        momentum = self._get_momentum()
        end_direction = self._get_direction_to_end(current)

        # Puntuar cada opción
        scores = []
        for i, cand in enumerate(candidates):
            cand_arr = np.array(cand, dtype=float)

            # Score 1: Momentum (continuar en la misma dirección)
            mom_score = 0
            if np.linalg.norm(momentum) > 0:
                mom_score = max(0, np.dot(directions[i], momentum))

            # Score 2: Dirección hacia el END
            end_score = 0
            if np.linalg.norm(end_direction) > 0:
                end_score = max(0, np.dot(directions[i], end_direction))

            # Score 3: Distancia euclidiana al END (negativa para minimizar)
            dist_to_end = np.linalg.norm(cand_arr - np.array(self.end))
            dist_score = -dist_to_end / 1000.0  # Normalizar

            total_score = mom_score * 2.0 + end_score * 1.5 + dist_score
            scores.append((total_score, i, cand))

        # Ordenar por score descendente
        scores.sort(key=lambda x: x[0], reverse=True)

        # Si hay múltiples grupos, guardar como intersección
        if len(groups) >= 2:
            alternatives = [scores[j][2] for j in range(1, len(scores))]
            intersection = IntersectionPoint(
                location=current,
                directions=[directions[scores[j][1]] for j in range(len(scores))],
                chosen_index=0,  # Elegimos la mejor
                path_index=len(self.path)
            )
            # Guardar alternativas para backtracking
            intersection.alternatives = alternatives
            self.intersections.append(intersection)

        # Devolver la mejor opción
        return scores[0][2]

    def _group_directions(self, candidates: List[Tuple[int, int]], directions: List[np.ndarray]) -> List[List[int]]:
        """Agrupa direcciones similares (ángulo < 30°)."""
        groups = []
        used = [False] * len(directions)

        for i in range(len(directions)):
            if used[i]:
                continue

            group = [i]
            used[i] = True

            for j in range(i+1, len(directions)):
                if used[j]:
                    continue

                # Calcular ángulo entre direcciones
                dot = np.dot(directions[i], directions[j])
                angle = np.arccos(np.clip(dot, -1.0, 1.0))

                if angle < np.pi / 6:  # 30 grados
                    group.append(j)
                    used[j] = True

            groups.append(group)

        return groups

    def _perform_backtracking(self) -> bool:
        """Retrocede a la última intersección con opciones disponibles."""
        while self.intersections:
            last_int = self.intersections[-1]

            if not hasattr(last_int, 'alternatives') or len(last_int.alternatives) == 0:
                self.intersections.pop()
                continue

            # Tenemos una alternativa
            # 1. Desmarcar el segmento desde la intersección hasta el final actual
            cut_index = last_int.path_index + 1
            bad_segment = self.path[cut_index:]

            for p in bad_segment:
                self._unmark_visited(p)

            # 2. Cortar el path
            self.path = self.path[:cut_index]

            # 3. Tomar la siguiente alternativa
            next_option = last_int.alternatives.pop(0)
            self.path.append(next_option)
            self._mark_visited(next_option)

            return True

        return False

    def _mark_visited(self, point: Tuple[int, int]):
        """
        Marca como visitado:
        1. El punto en el centerline
        2. Todos los píxeles de la cuerda en su área de influencia
        """
        x, y = point

        # Marcar el punto del centerline
        self.visited_centerline[y, x] = 255

        # Marcar el área de influencia basándose en distance transform
        # El radio de influencia es la distancia al borde en ese punto
        radius = int(self.distance_transform[y, x])
        if radius < 3:
            radius = 5  # Mínimo

        # Crear máscara circular
        y_min = max(0, y - radius)
        y_max = min(self.mask.shape[0], y + radius)
        x_min = max(0, x - radius)
        x_max = min(self.mask.shape[1], x + radius)

        roi_mask = self.mask[y_min:y_max, x_min:x_max]
        roi_visited = self.visited_area[y_min:y_max, x_min:x_max]

        roi_h, roi_w = roi_mask.shape
        cy_local = y - y_min
        cx_local = x - x_min

        yy, xx = np.ogrid[0:roi_h, 0:roi_w]
        circle_mask = (xx - cx_local)**2 + (yy - cy_local)**2 <= radius**2

        # Marcar píxeles de cuerda en el área
        pixels_to_mark = np.logical_and(roi_mask > 0, circle_mask)
        roi_visited[pixels_to_mark] = 255

        self.visited_area[y_min:y_max, x_min:x_max] = roi_visited

    def _unmark_visited(self, point: Tuple[int, int]):
        """Desmarca un punto (para backtracking)."""
        x, y = point

        self.visited_centerline[y, x] = 0

        radius = int(self.distance_transform[y, x])
        if radius < 3:
            radius = 5

        y_min = max(0, y - radius)
        y_max = min(self.mask.shape[0], y + radius)
        x_min = max(0, x - radius)
        x_max = min(self.mask.shape[1], x + radius)

        roi_visited = self.visited_area[y_min:y_max, x_min:x_max]
        roi_mask = self.mask[y_min:y_max, x_min:x_max]

        roi_h, roi_w = roi_mask.shape
        cy_local = y - y_min
        cx_local = x - x_min

        yy, xx = np.ogrid[0:roi_h, 0:roi_w]
        circle_mask = (xx - cx_local)**2 + (yy - cy_local)**2 <= radius**2

        pixels_to_unmark = np.logical_and(roi_mask > 0, circle_mask)
        roi_visited[pixels_to_unmark] = 0

        self.visited_area[y_min:y_max, x_min:x_max] = roi_visited

    def _get_momentum(self) -> np.ndarray:
        """Dirección promedio de los últimos N puntos del path."""
        if len(self.path) < 10:
            return np.array([0.0, 0.0])

        recent = np.array(self.path[-10:])
        direction = recent[-1] - recent[0]
        norm = np.linalg.norm(direction)

        return direction / norm if norm > 0 else np.array([0.0, 0.0])

    def _get_direction_to_end(self, current: Tuple[int, int]) -> np.ndarray:
        """Vector normalizado hacia el END."""
        direction = np.array(self.end) - np.array(current)
        norm = np.linalg.norm(direction)
        return direction / norm if norm > 0 else np.array([0.0, 0.0])

    def _compute_coverage(self) -> float:
        """Porcentaje del área de la cuerda visitada."""
        covered = np.logical_and(self.mask > 0, self.visited_area > 0)
        return np.sum(covered) / self.total_mask_pixels if self.total_mask_pixels > 0 else 0.0

    def _compute_centerline_coverage(self) -> float:
        """Porcentaje del centerline visitado."""
        covered = np.logical_and(self.centerline > 0, self.visited_centerline > 0)
        total = np.sum(self.centerline > 0)
        return np.sum(covered) / total if total > 0 else 0.0

    def visualize(self, output_path: str):
        """Genera visualización completa."""
        fig, axes = plt.subplots(2, 2, figsize=(16, 14))

        # 1. Máscara original
        axes[0, 0].imshow(self.mask, cmap='gray')
        axes[0, 0].set_title("Máscara Original")
        axes[0, 0].axis('off')

        # 2. Distance Transform
        axes[0, 1].imshow(self.dt_normalized, cmap='hot')
        axes[0, 1].set_title("Distance Transform")
        axes[0, 1].axis('off')

        # 3. Centerline
        centerline_viz = cv2.cvtColor(self.mask.copy(), cv2.COLOR_GRAY2BGR)
        # Marcar máscara en gris
        mask_gray_indices = np.where(self.mask > 0)
        centerline_viz[mask_gray_indices[0], mask_gray_indices[1]] = [80, 80, 80]
        # Marcar centerline en cian
        centerline_indices = np.where(self.centerline > 0)
        centerline_viz[centerline_indices[0], centerline_indices[1]] = [255, 255, 0]
        axes[1, 0].imshow(cv2.cvtColor(centerline_viz, cv2.COLOR_BGR2RGB))
        axes[1, 0].set_title("Centerline (Cian)")
        axes[1, 0].axis('off')

        # 4. Resultado final: Visitado + Path
        result = cv2.cvtColor(self.mask.copy(), cv2.COLOR_GRAY2BGR)
        # Marcar máscara no visitada en gris
        mask_indices = np.where(self.mask > 0)
        result[mask_indices[0], mask_indices[1]] = [100, 100, 100]

        # Área visitada en rojo (overlay semitransparente)
        overlay = result.copy()
        visited_indices = np.where(self.visited_area > 0)
        overlay[visited_indices[0], visited_indices[1]] = [0, 0, 255]
        cv2.addWeighted(overlay, 0.6, result, 0.4, 0, result)

        # Path en cian brillante
        if len(self.path) > 1:
            pts = np.array(self.path, np.int32).reshape((-1, 1, 2))
            cv2.polylines(result, [pts], False, (255, 255, 0), 2)

        # Intersecciones en amarillo
        for inter in self.intersections:
            cv2.circle(result, inter.location, 8, (0, 255, 255), -1)

        # Start/End
        cv2.circle(result, self.start, 10, (0, 255, 0), -1)  # Verde
        cv2.circle(result, self.end, 10, (0, 0, 255), -1)    # Rojo oscuro

        axes[1, 1].imshow(cv2.cvtColor(result, cv2.COLOR_BGR2RGB))
        cov = self._compute_coverage() * 100
        cl_cov = self._compute_centerline_coverage() * 100
        axes[1, 1].set_title(f"Resultado | Área: {cov:.1f}% | CL: {cl_cov:.1f}%")
        axes[1, 1].axis('off')

        plt.tight_layout()
        plt.savefig(output_path, dpi=150, bbox_inches='tight')
        print(f"\n[OK] Visualización guardada: {output_path}")
        plt.show()


def main():
    """Test del tracker robusto."""
    mask_path = r"c:\Users\jf19s\Desktop\PROYECTOS\ACTUALES\STEREO_PHOTOGRAMMETRY_CM5\data\results\debug\cable_mask_left.png"

    # Cargar máscara
    mask = cv2.imread(mask_path, cv2.IMREAD_GRAYSCALE)
    if mask is None:
        print(f"[ERROR] No se pudo cargar {mask_path}")
        return None

    _, mask = cv2.threshold(mask, 127, 255, cv2.THRESH_BINARY)

    # Endpoints
    start = (1248, 668)
    end = (1297, 945)

    # Crear tracker
    tracker = RobustWireTracker(mask, start, end)

    # Ejecutar tracking
    result = tracker.track_wire(max_iterations=50000)

    # Visualizar
    if result['success']:
        tracker.visualize('data/results/debug/robust_wire_tracking.png')

    return result


if __name__ == "__main__":
    main()
