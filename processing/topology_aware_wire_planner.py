#!/usr/bin/env python3
"""
Topology-Aware Wire Planner - Detecta automáticamente la topología y explora TODAS las ramas.

Estrategia:
1. Analiza la topología de la máscara (detecta "brazos" de la X)
2. Durante el tracking, valida que TODAS las regiones conectadas fueron visitadas
3. Si llega al END pero hay regiones grandes sin visitar, hace backtrack al punto de decisión
4. Explora las ramas faltantes antes de declarar el path completo
"""

import cv2
import numpy as np
import matplotlib.pyplot as plt
from typing import List, Tuple, Dict, Optional, Set
from dataclasses import dataclass
from collections import deque
import copy


@dataclass
class UnvisitedRegion:
    """Región de máscara no visitada."""
    pixels: np.ndarray  # Coordenadas (N, 2)
    size: int
    centroid: Tuple[int, int]
    nearest_visited_point: Tuple[int, int]  # Punto visitado más cercano
    distance_to_visited: float


@dataclass
class PathState:
    """Estado completo del path."""
    path: List[Tuple[int, int]]
    visited_map: np.ndarray
    coverage: float
    current_pos: Tuple[int, int]
    iteration: int


class TopologyAwareWirePlanner:
    """Planner que entiende la topología y explora todas las ramas."""

    def __init__(self, mask: np.ndarray, start: Tuple[int, int], end: Tuple[int, int]):
        self.mask = mask
        self.start = start
        self.end = end

        # Parámetros
        self.step_size = 5
        self.coverage_radius = 3
        self.min_region_size = 100  # Región mínima significativa

        # Estado
        self.path: List[Tuple[int, int]] = []
        self.visited_map = np.zeros_like(mask, dtype=np.uint8)
        self.states_stack: List[PathState] = []  # Stack para backtracking

        # Métricas
        self.total_mask_pixels = np.sum(mask > 0)

    def plan_path(self, max_iterations: int = 20000) -> Dict:
        """Planifica path explorando TODAS las ramas."""
        print("\n" + "="*70)
        print("TOPOLOGY-AWARE WIRE PLANNER")
        print("="*70)

        self.path = [self.start]
        current = self.start
        cv2.circle(self.visited_map, self.start, self.coverage_radius, 255, -1)

        iteration = 0
        exploration_attempts = 0
        max_exploration_attempts = 10

        while iteration < max_iterations:
            iteration += 1

            # Verificar si llegamos al END
            dist_to_end = np.linalg.norm(np.array(current) - np.array(self.end))
            if dist_to_end < self.step_size * 2:
                self.path.append(self.end)
                cv2.circle(self.visited_map, self.end, self.coverage_radius, 255, -1)

                coverage = self._compute_coverage()
                print(f"\n[INFO] Llegado al END en iteracion {iteration}")
                print(f"       Cobertura: {coverage*100:.1f}%")

                # CLAVE: Verificar si hay regiones grandes sin visitar
                unvisited_regions = self._find_unvisited_regions()

                if unvisited_regions and exploration_attempts < max_exploration_attempts:
                    print(f"       [!] Hay {len(unvisited_regions)} regiones sin visitar!")
                    print(f"       [>>] Haciendo backtrack para explorar ramas faltantes...")

                    # Encontrar el mejor punto para hacer backtrack
                    backtrack_result = self._backtrack_to_explore_region(unvisited_regions)

                    if backtrack_result:
                        current, iteration = backtrack_result
                        exploration_attempts += 1
                        print(f"       [OK] Continuando exploracion (intento {exploration_attempts}/{max_exploration_attempts})...")
                        continue
                    else:
                        print("       [!] No se puede hacer backtrack, terminando")
                        break
                else:
                    print("       [OK] Todas las regiones exploradas!")
                    break

            # Guardar estado cada N pasos (para backtracking)
            if iteration % 20 == 0:
                self._save_state(current, iteration)

            # Obtener opciones de movimiento
            options = self._get_movement_options(current)

            if not options:
                # Sin opciones, intentar backtrack
                print(f"\n[!] Sin opciones en iter {iteration}")
                backtrack_result = self._backtrack_for_deadend()
                if backtrack_result:
                    current, iteration = backtrack_result
                    continue
                else:
                    break

            # Evaluar y elegir mejor opción
            scored_options = self._score_options(current, options)
            next_pos = scored_options[0][0]

            # Avanzar
            self.path.append(next_pos)
            current = next_pos
            cv2.circle(self.visited_map, next_pos, self.coverage_radius, 255, -1)

            # Log progreso
            if iteration % 100 == 0:
                coverage = self._compute_coverage()
                print(f"  Iter {iteration}: {len(self.path)} pts, coverage: {coverage*100:.1f}%")

        final_coverage = self._compute_coverage()
        final_unvisited = self._find_unvisited_regions()

        print(f"\n[OK] Path completado: {len(self.path)} puntos")
        print(f"     Cobertura final: {final_coverage*100:.1f}%")
        print(f"     Regiones sin visitar: {len(final_unvisited)}")

        return {
            'success': True,
            'path': self.path,
            'coverage': final_coverage,
            'unvisited_regions': len(final_unvisited)
        }

    def _find_unvisited_regions(self) -> List[UnvisitedRegion]:
        """
        Encuentra regiones grandes de máscara que no han sido visitadas.

        Returns:
            Lista de regiones significativas sin visitar
        """
        # Máscara de píxeles no visitados
        unvisited_mask = np.logical_and(
            self.mask > 0,
            self.visited_map == 0
        ).astype(np.uint8) * 255

        # Encontrar componentes conexas
        num_regions, labels, stats, centroids = cv2.connectedComponentsWithStats(
            unvisited_mask, connectivity=8
        )

        regions = []

        for region_id in range(1, num_regions):  # Saltar background (0)
            size = stats[region_id, cv2.CC_STAT_AREA]

            # Solo regiones significativas
            if size < self.min_region_size:
                continue

            # Obtener píxeles de la región
            region_pixels = np.argwhere(labels == region_id)
            region_pixels = region_pixels[:, [1, 0]]  # (x, y)

            centroid = tuple(centroids[region_id].astype(int))

            # Encontrar punto visitado más cercano
            visited_points = np.argwhere(self.visited_map > 0)
            if len(visited_points) == 0:
                continue

            visited_points = visited_points[:, [1, 0]]  # (x, y)

            # Calcular distancias de centroid a todos los puntos visitados
            dists = np.linalg.norm(visited_points - np.array(centroid), axis=1)
            min_idx = np.argmin(dists)
            nearest_visited = tuple(visited_points[min_idx])
            min_dist = dists[min_idx]

            regions.append(UnvisitedRegion(
                pixels=region_pixels,
                size=size,
                centroid=centroid,
                nearest_visited_point=nearest_visited,
                distance_to_visited=min_dist
            ))

        # Ordenar por tamaño (más grandes primero)
        regions.sort(key=lambda r: r.size, reverse=True)

        return regions

    def _backtrack_to_explore_region(self, unvisited_regions: List[UnvisitedRegion]) -> Optional[Tuple[Tuple[int, int], int]]:
        """
        Hace backtrack al punto más cercano a la región sin visitar más grande.

        Estrategia:
        1. Tomar la región más grande sin visitar
        2. Encontrar el punto visitado más cercano a esa región
        3. Restaurar el estado en ese punto
        4. Continuar desde ahí hacia la región
        """
        if not unvisited_regions or not self.states_stack:
            return None

        # Región más importante (más grande)
        target_region = unvisited_regions[0]

        print(f"       Target region: size={target_region.size} px, centroid={target_region.centroid}")

        # Encontrar el estado guardado más cercano a la región
        best_state = None
        best_dist = float('inf')

        for state in self.states_stack:
            dist = np.linalg.norm(
                np.array(state.current_pos) - np.array(target_region.centroid)
            )

            # Debe estar razonablemente cerca Y haber cobertura menor
            # (queremos volver a un punto ANTES de tomar la decisión incorrecta)
            if dist < best_dist and state.coverage < self._compute_coverage():
                best_dist = dist
                best_state = state

        if best_state is None:
            return None

        # Restaurar estado
        print(f"       Restaurando estado en iter {best_state.iteration}, "
              f"pos={best_state.current_pos}, dist={best_dist:.1f}")

        self.path = copy.deepcopy(best_state.path)
        self.visited_map = best_state.visited_map.copy()

        # Remover el END del path si estaba
        if self.path[-1] == self.end:
            self.path.pop()

        return (best_state.current_pos, best_state.iteration)

    def _backtrack_for_deadend(self) -> Optional[Tuple[Tuple[int, int], int]]:
        """Hace backtrack cuando llega a deadend."""
        if not self.states_stack:
            return None

        # Retroceder al último estado guardado
        state = self.states_stack.pop()

        print(f"       [>>] Backtrack a iter {state.iteration}")

        self.path = copy.deepcopy(state.path)
        self.visited_map = state.visited_map.copy()

        return (state.current_pos, state.iteration)

    def _save_state(self, current: Tuple[int, int], iteration: int):
        """Guarda el estado actual para posible backtrack."""
        state = PathState(
            path=copy.deepcopy(self.path),
            visited_map=self.visited_map.copy(),
            coverage=self._compute_coverage(),
            current_pos=current,
            iteration=iteration
        )

        self.states_stack.append(state)

        # Limitar tamaño del stack
        if len(self.states_stack) > 200:
            self.states_stack.pop(0)

    def _get_movement_options(self, current: Tuple[int, int]) -> List[Tuple[int, int]]:
        """Obtiene opciones de movimiento válidas."""
        x, y = current
        search_radius = self.step_size * 3

        y_min = max(0, y - search_radius)
        y_max = min(self.mask.shape[0], y + search_radius + 1)
        x_min = max(0, x - search_radius)
        x_max = min(self.mask.shape[1], x + search_radius + 1)

        mask_region = self.mask[y_min:y_max, x_min:x_max]
        visited_region = self.visited_map[y_min:y_max, x_min:x_max]

        # Preferir píxeles no visitados
        unvisited_wire = np.logical_and(mask_region > 0, visited_region == 0)

        if not unvisited_wire.any():
            wire_pixels = (mask_region > 0)
        else:
            wire_pixels = unvisited_wire

        if not wire_pixels.any():
            return []

        wire_y, wire_x = np.where(wire_pixels)
        wire_y = wire_y + y_min
        wire_x = wire_x + x_min

        # Filtrar por distancia
        options = []
        for wx, wy in zip(wire_x, wire_y):
            dist = np.linalg.norm(np.array([wx - x, wy - y]))
            if self.step_size * 0.7 < dist < self.step_size * 2.5:
                options.append((wx, wy))

        return options

    def _score_options(self, current: Tuple[int, int],
                      options: List[Tuple[int, int]]) -> List[Tuple[Tuple[int, int], float]]:
        """
        Evalúa opciones con scoring balanceado.

        Prioridades:
        1. Momentum (60%) - Continuar dirección
        2. Exploración (25%) - Ir a zonas no visitadas
        3. Acercamiento al END (10%) - Solo si cobertura > 75%
        4. Evitar loops (5%)
        """
        current_arr = np.array(current)
        end_arr = np.array(self.end)

        momentum = self._get_momentum()
        current_coverage = self._compute_coverage()

        scored = []

        for option in options:
            opt_arr = np.array(option)

            direction = opt_arr - current_arr
            dist = np.linalg.norm(direction)

            if dist < 1e-6:
                continue

            direction = direction / dist

            # SCORE 1: Momentum (60%)
            if np.linalg.norm(momentum) > 0:
                alignment = np.dot(direction, momentum)
                momentum_score = max(0, alignment) ** 2
            else:
                momentum_score = 0.5

            # SCORE 2: Exploración - preferir zonas no visitadas (25%)
            exploration_score = self._compute_exploration_score(option)

            # SCORE 3: Acercamiento al END (10%, solo si cobertura > 75%)
            if current_coverage > 0.75:
                dist_before = np.linalg.norm(current_arr - end_arr)
                dist_after = np.linalg.norm(opt_arr - end_arr)
                end_score = 1.0 if dist_after < dist_before else 0.3
            else:
                end_score = 0.5  # Neutral

            # SCORE 4: Evitar loops (5%)
            loop_penalty = 0.0
            if len(self.path) > 20:
                recent = np.array(self.path[-50:])
                dists = np.linalg.norm(recent - opt_arr, axis=1)
                min_dist = np.min(dists[:-3])
                if min_dist < 10:
                    loop_penalty = -0.5

            # Score total
            total = (momentum_score * 0.60 +
                    exploration_score * 0.25 +
                    end_score * 0.10 +
                    loop_penalty * 0.05)

            scored.append((option, total))

        scored.sort(key=lambda x: x[1], reverse=True)
        return scored

    def _compute_exploration_score(self, pos: Tuple[int, int]) -> float:
        """
        Calcula score de exploración: qué tan cerca está de zonas no visitadas.

        Mayor score = más cerca de píxeles no visitados
        """
        x, y = pos
        radius = 15

        y_min = max(0, y - radius)
        y_max = min(self.mask.shape[0], y + radius + 1)
        x_min = max(0, x - radius)
        x_max = min(self.mask.shape[1], x + radius + 1)

        mask_region = self.mask[y_min:y_max, x_min:x_max]
        visited_region = self.visited_map[y_min:y_max, x_min:x_max]

        # Contar píxeles de cuerda no visitados en la vecindad
        unvisited = np.logical_and(mask_region > 0, visited_region == 0)
        unvisited_count = np.sum(unvisited)

        total_wire = np.sum(mask_region > 0)

        if total_wire == 0:
            return 0.0

        # Ratio de píxeles no visitados
        ratio = unvisited_count / total_wire

        return ratio

    def _get_momentum(self) -> np.ndarray:
        """Calcula momentum direction."""
        if len(self.path) < 2:
            return np.array([0.0, 0.0])

        window = min(15, len(self.path))
        recent = self.path[-window:]

        directions = []
        weights = []

        for i in range(1, len(recent)):
            p1 = np.array(recent[i-1])
            p2 = np.array(recent[i])
            direction = p2 - p1
            norm = np.linalg.norm(direction)

            if norm > 0:
                directions.append(direction / norm)
                weights.append(i)

        if not directions:
            return np.array([0.0, 0.0])

        directions = np.array(directions)
        weights = np.array(weights)
        weights = weights / weights.sum()

        momentum = np.sum(directions * weights[:, np.newaxis], axis=0)
        norm = np.linalg.norm(momentum)

        return momentum / norm if norm > 0 else np.array([0.0, 0.0])

    def _compute_coverage(self) -> float:
        """Calcula cobertura actual."""
        covered = np.logical_and(self.mask > 0, self.visited_map > 0)
        return np.sum(covered) / self.total_mask_pixels

    def visualize(self, output_path: str):
        """Visualiza el resultado con regiones sin visitar marcadas."""
        vis = cv2.cvtColor(self.mask, cv2.COLOR_GRAY2BGR)

        # Marcar regiones sin visitar en rojo
        unvisited_regions = self._find_unvisited_regions()
        for region in unvisited_regions:
            for px, py in region.pixels:
                if 0 <= py < vis.shape[0] and 0 <= px < vis.shape[1]:
                    vis[py, px] = (0, 0, 255)  # Rojo

        # Dibujar path con gradiente
        path_array = np.array(self.path, dtype=np.int32)

        for i in range(len(path_array) - 1):
            p1 = tuple(path_array[i])
            p2 = tuple(path_array[i+1])

            ratio = i / len(path_array)
            color_val = int(ratio * 255)
            color = cv2.applyColorMap(np.array([[color_val]], dtype=np.uint8),
                                     cv2.COLORMAP_VIRIDIS)[0, 0]
            color = tuple(map(int, color))

            cv2.line(vis, p1, p2, color, 3)

        # Marcar START y END
        cv2.circle(vis, self.start, 15, (0, 255, 0), -1)
        cv2.circle(vis, self.end, 15, (255, 255, 0), -1)

        coverage = self._compute_coverage()

        plt.figure(figsize=(16, 14))
        plt.imshow(cv2.cvtColor(vis, cv2.COLOR_BGR2RGB))
        plt.title(f"Topology-Aware Wire Path - {len(self.path)} pts | "
                 f"Coverage: {coverage*100:.1f}% | "
                 f"Unvisited Regions: {len(unvisited_regions)}",
                 fontsize=14, weight='bold')
        plt.axis('off')
        plt.tight_layout()
        plt.savefig(output_path, dpi=150, bbox_inches='tight')
        print(f"\n[OK] Visualizacion guardada: {output_path}")
        plt.show()


def main():
    """Test del planner topology-aware."""
    mask_path = r"c:\Users\jf19s\Desktop\PROYECTOS\ACTUALES\STEREO_PHOTOGRAMMETRY_CM5\data\results\debug\cable_mask_left.png"

    mask = cv2.imread(mask_path, cv2.IMREAD_GRAYSCALE)
    _, mask = cv2.threshold(mask, 127, 255, cv2.THRESH_BINARY)

    start = (1248, 668)
    end = (1297, 945)

    planner = TopologyAwareWirePlanner(mask, start, end)
    result = planner.plan_path(max_iterations=20000)

    if result['success']:
        planner.visualize('data/results/debug/topology_aware_wire_path.png')

    return result


if __name__ == "__main__":
    main()
