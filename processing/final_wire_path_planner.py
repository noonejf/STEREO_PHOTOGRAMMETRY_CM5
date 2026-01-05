#!/usr/bin/env python3
"""
Final Wire Path Planner - Basado en wire_path_tracker original + validación skeleton.

Approach:
1. Usa el algoritmo original de flow_direction que SÍ llega al END
2. Limpia máscara para eliminar ruido
3. Valida con skeleton (no píxeles gruesos)
4. Si detecta ramas faltantes, las explora antes de terminar
"""

import cv2
import numpy as np
import matplotlib.pyplot as plt
from typing import List, Tuple, Dict, Optional


class FinalWirePathPlanner:
    """Planner final con validación de skeleton."""

    def __init__(self, mask: np.ndarray, start: Tuple[int, int], end: Tuple[int, int]):
        self.original_mask = mask.copy()
        self.start = start
        self.end = end

        # Limpiar máscara
        print("\n[1/4] Limpiando mascara...")
        self.mask = self._clean_mask(mask)
        print(f"      Ruido eliminado: {np.sum(mask > 0) - np.sum(self.mask > 0)} px")

        # Generar skeleton
        print("\n[2/4] Generando skeleton...")
        mask_binary = (self.mask > 0).astype(np.uint8)
        self.skeleton = cv2.ximgproc.thinning(mask_binary * 255)
        self.skeleton = (self.skeleton > 0).astype(np.uint8)
        self.total_skeleton_pixels = np.sum(self.skeleton > 0)
        print(f"      Skeleton: {self.total_skeleton_pixels} px")

        # Parámetros
        self.step_size = 5
        self.coverage_radius = 8

    def _clean_mask(self, mask: np.ndarray) -> np.ndarray:
        """Limpia máscara eliminando ruido."""
        _, binary = cv2.threshold(mask, 127, 255, cv2.THRESH_BINARY)
        kernel_erode = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
        eroded = cv2.erode(binary, kernel_erode, iterations=2)
        kernel_dilate = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
        dilated = cv2.dilate(eroded, kernel_dilate, iterations=1)
        return dilated

    def plan_path(self, max_iterations: int = 20000) -> Dict:
        """Planifica path completo."""
        print("\n[3/4] Planificando path...")
        print("="*70)

        # PASO 1: Path inicial (START → END)
        path, visited_map = self._track_main_path(max_iterations)

        if path[-1] != self.end:
            print("\n[!] No llego al END")
            return self._build_result(path, visited_map, success=False)

        print(f"\n[OK] Llego al END con {len(path)} puntos")

        # PASO 2: Validar skeleton
        coverage = self._validate_skeleton_coverage(visited_map)
        print(f"      Skeleton coverage: {coverage*100:.1f}%")

        if coverage >= 0.95:
            print("[OK] Path VALIDO!")
            return self._build_result(path, visited_map, success=True)

        # PASO 3: Explorar ramas faltantes
        print(f"\n[!] Path INVALIDO - {(1-coverage)*100:.1f}% sin cubrir")
        print("[>>] Explorando ramas faltantes...")

        path, visited_map = self._explore_missing_branches(
            path, visited_map, max_iterations=5000
        )

        # Re-validar
        final_coverage = self._validate_skeleton_coverage(visited_map)
        print(f"\n      Skeleton coverage final: {final_coverage*100:.1f}%")

        success = final_coverage >= 0.95

        return self._build_result(path, visited_map, success)

    def _track_main_path(self, max_iterations: int) -> Tuple[List[Tuple[int, int]], np.ndarray]:
        """Track principal desde START a END."""
        path = [self.start]
        current_pos = np.array(self.start, dtype=float)
        visited_map = np.zeros_like(self.mask, dtype=np.uint8)
        cv2.circle(visited_map, self.start, self.coverage_radius, 255, -1)

        for iteration in range(max_iterations):
            # Calcular dirección de flujo
            flow_direction = self._compute_flow_direction(
                current_pos,
                path[-2] if len(path) > 1 else None,
                visited_map
            )

            if flow_direction is None:
                break

            # Avanzar
            next_pos = current_pos + flow_direction * self.step_size
            next_pos_int = tuple(next_pos.astype(int))

            # ¿Llegamos al END?
            dist_to_end = np.linalg.norm(next_pos - np.array(self.end))
            if dist_to_end < self.step_size * 2:
                path.append(self.end)
                cv2.circle(visited_map, self.end, self.coverage_radius, 255, -1)
                break

            path.append(next_pos_int)
            current_pos = next_pos
            cv2.circle(visited_map, next_pos_int, self.coverage_radius // 2, 255, -1)

            if iteration % 500 == 0:
                print(f"  Iter {iteration}: {len(path)} pts")

        return path, visited_map

    def _compute_flow_direction(self, current_pos, previous_pos, visited_map):
        """Calcula dirección de flujo (del wire_path_tracker original)."""
        x, y = int(current_pos[0]), int(current_pos[1])
        search_radius = self.step_size * 3

        y_min = max(0, y - search_radius)
        y_max = min(self.mask.shape[0], y + search_radius + 1)
        x_min = max(0, x - search_radius)
        x_max = min(self.mask.shape[1], x + search_radius + 1)

        mask_region = self.mask[y_min:y_max, x_min:x_max]
        visited_region = visited_map[y_min:y_max, x_min:x_max]

        # Píxeles no visitados preferentemente
        unvisited_wire = (mask_region > 0) & (visited_region == 0)

        if not unvisited_wire.any():
            wire_pixels = (mask_region > 0)
        else:
            wire_pixels = unvisited_wire

        if not wire_pixels.any():
            return None

        wire_y, wire_x = np.where(wire_pixels)
        wire_y = wire_y + y_min
        wire_x = wire_x + x_min

        # Vectores
        vectors = np.column_stack([wire_x - x, wire_y - y])
        distances = np.linalg.norm(vectors, axis=1)

        far_enough = distances > self.step_size * 0.7
        if not far_enough.any():
            return None

        vectors = vectors[far_enough]
        distances = distances[far_enough]
        wire_x = wire_x[far_enough]
        wire_y = wire_y[far_enough]

        directions = vectors / (distances[:, np.newaxis] + 1e-6)

        # Momentum
        if previous_pos is not None:
            prev_direction = current_pos - np.array(previous_pos)
            prev_direction = prev_direction / (np.linalg.norm(prev_direction) + 1e-6)

            alignment = np.dot(directions, prev_direction)
            alignment_score = np.maximum(alignment, 0) ** 4

            distance_score = 1.0 / (distances + 1e-6)
            weights = alignment_score * distance_score
            weights[alignment < 0] = 0

            if weights.sum() == 0:
                weights = distance_score
        else:
            weights = 1.0 / (distances + 1e-6)

        weights = weights / (weights.sum() + 1e-6)

        # Mejor opción
        best_idx = np.argmax(weights)
        target_x = wire_x[best_idx]
        target_y = wire_y[best_idx]

        direction = np.array([target_x - x, target_y - y], dtype=float)
        direction_norm = np.linalg.norm(direction)

        if direction_norm < 1e-6:
            return None

        return direction / direction_norm

    def _explore_missing_branches(self, path: List[Tuple[int, int]],
                                  visited_map: np.ndarray,
                                  max_iterations: int) -> Tuple[List[Tuple[int, int]], np.ndarray]:
        """Explora ramas faltantes del skeleton."""
        for attempt in range(3):
            # Skeleton sin cubrir
            kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE,
                                              (self.coverage_radius * 2, self.coverage_radius * 2))
            visited_dilated = cv2.dilate(visited_map, kernel, iterations=1)
            skeleton_uncovered = np.logical_and(self.skeleton > 0, visited_dilated == 0)

            uncovered_points = np.argwhere(skeleton_uncovered)
            if len(uncovered_points) == 0:
                break

            uncovered_points = uncovered_points[:, [1, 0]]  # (x, y)
            centroid = tuple(np.mean(uncovered_points, axis=0).astype(int))

            print(f"  Intento {attempt + 1}: Explorando hacia {centroid}")

            # Punto del path más cercano
            path_array = np.array(path)
            distances = np.linalg.norm(path_array - np.array(centroid), axis=1)
            closest_idx = np.argmin(distances)
            current = tuple(path_array[closest_idx])

            # Continuar desde ahí
            branch_path, visited_map = self._track_towards_target(
                current, centroid, visited_map, max_iterations
            )

            path.extend(branch_path)
            print(f"     +{len(branch_path)} puntos")

        return path, visited_map

    def _track_towards_target(self, start_pos: Tuple[int, int],
                             target: Tuple[int, int],
                             visited_map: np.ndarray,
                             max_iterations: int) -> Tuple[List[Tuple[int, int]], np.ndarray]:
        """Track hacia un target específico."""
        path = []
        current_pos = np.array(start_pos, dtype=float)

        for _ in range(max_iterations):
            # Dirección hacia target
            to_target = np.array(target) - current_pos
            dist_to_target = np.linalg.norm(to_target)

            if dist_to_target < self.step_size:
                break

            # Buscar opciones
            flow_direction = self._compute_flow_direction(
                current_pos,
                path[-1] if len(path) > 0 else None,
                visited_map
            )

            if flow_direction is None:
                break

            next_pos = current_pos + flow_direction * self.step_size
            next_pos_int = tuple(next_pos.astype(int))

            path.append(next_pos_int)
            current_pos = next_pos
            cv2.circle(visited_map, next_pos_int, self.coverage_radius // 2, 255, -1)

        return path, visited_map

    def _validate_skeleton_coverage(self, visited_map: np.ndarray) -> float:
        """Valida cobertura del skeleton."""
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE,
                                          (self.coverage_radius * 2, self.coverage_radius * 2))
        visited_dilated = cv2.dilate(visited_map, kernel, iterations=1)

        skeleton_covered = np.logical_and(self.skeleton > 0, visited_dilated > 0)
        covered_px = np.sum(skeleton_covered)

        return covered_px / self.total_skeleton_pixels if self.total_skeleton_pixels > 0 else 0.0

    def _build_result(self, path: List[Tuple[int, int]],
                     visited_map: np.ndarray,
                     success: bool) -> Dict:
        """Construye resultado."""
        coverage = self._validate_skeleton_coverage(visited_map)

        return {
            'success': success,
            'path': path,
            'skeleton_coverage': coverage,
            'num_points': len(path)
        }

    def visualize(self, result: Dict, output_path: str):
        """Visualiza resultado."""
        path = result['path']
        coverage = result['skeleton_coverage']

        vis = cv2.cvtColor(self.mask, cv2.COLOR_GRAY2BGR)

        # Skeleton sin cubrir en ROJO
        visited_map = np.zeros_like(self.mask, dtype=np.uint8)
        for p in path:
            cv2.circle(visited_map, p, self.coverage_radius, 255, -1)

        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE,
                                          (self.coverage_radius * 2, self.coverage_radius * 2))
        visited_dilated = cv2.dilate(visited_map, kernel, iterations=1)
        skeleton_uncovered = np.logical_and(self.skeleton > 0, visited_dilated == 0)
        vis[skeleton_uncovered] = (0, 0, 255)

        # Path
        path_array = np.array(path, dtype=np.int32)

        for i in range(len(path_array) - 1):
            p1 = tuple(path_array[i])
            p2 = tuple(path_array[i+1])

            ratio = i / len(path_array)
            color_val = int(ratio * 255)
            color = cv2.applyColorMap(np.array([[color_val]], dtype=np.uint8),
                                     cv2.COLORMAP_VIRIDIS)[0, 0]
            color = tuple(map(int, color))

            cv2.line(vis, p1, p2, color, 3)

        # START y END
        cv2.circle(vis, self.start, 15, (0, 255, 0), -1)
        cv2.circle(vis, self.end, 15, (0, 255, 255), -1)

        status = "VALIDO" if result['success'] else "INVALIDO"
        color_status = "green" if result['success'] else "red"

        plt.figure(figsize=(16, 14))
        plt.imshow(cv2.cvtColor(vis, cv2.COLOR_BGR2RGB))
        plt.title(f"Final Wire Path - {len(path)} pts | "
                 f"Skeleton: {coverage*100:.1f}% | "
                 f"Status: {status}",
                 fontsize=14, weight='bold', color=color_status)
        plt.axis('off')
        plt.tight_layout()
        plt.savefig(output_path, dpi=150, bbox_inches='tight')
        print(f"\n[4/4] Visualizacion guardada: {output_path}")
        plt.show()


def main():
    """Test del planner final."""
    mask_path = r"c:\Users\jf19s\Desktop\PROYECTOS\ACTUALES\STEREO_PHOTOGRAMMETRY_CM5\data\results\debug\cable_mask_left.png"

    mask = cv2.imread(mask_path, cv2.IMREAD_GRAYSCALE)
    _, mask = cv2.threshold(mask, 127, 255, cv2.THRESH_BINARY)

    start = (1248, 668)
    end = (1297, 945)

    planner = FinalWirePathPlanner(mask, start, end)
    result = planner.plan_path(max_iterations=20000)

    print(f"\n=== RESULTADO FINAL ===")
    print(f"Exito: {result['success']}")
    print(f"Path: {result['num_points']} puntos")
    print(f"Skeleton coverage: {result['skeleton_coverage']*100:.1f}%")

    planner.visualize(result, 'data/results/debug/final_wire_path.png')

    return result


if __name__ == "__main__":
    main()
