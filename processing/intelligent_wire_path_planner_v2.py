#!/usr/bin/env python3
"""
Intelligent Wire Path Planner V2 - Versión mejorada con backtracking real.

Mejoras sobre V1:
- Backtracking real cuando detecta decisiones incorrectas
- Validación progresiva de cobertura (cada N pasos)
- Mejor scoring que considera alcanzabilidad de END
- Stack de decisiones para poder retroceder
"""

import cv2
import numpy as np
import matplotlib.pyplot as plt
from typing import List, Tuple, Dict, Optional, Set
from dataclasses import dataclass
from collections import deque
import copy


@dataclass
class PathState:
    """Estado completo del path en un momento dado."""
    path: List[Tuple[int, int]]
    visited_map: np.ndarray
    coverage: float
    current_pos: Tuple[int, int]


@dataclass
class DecisionPoint:
    """Punto de decisión con alternativas."""
    state: PathState  # Estado del sistema en este punto
    options: List[Tuple[Tuple[int, int], float]]  # (next_pos, score)
    chosen_index: int  # Cuál se eligió
    iteration: int  # En qué iteración se tomó


class IntelligentWirePathPlannerV2:
    """Planner mejorado con backtracking real."""

    def __init__(self, mask: np.ndarray, start: Tuple[int, int], end: Tuple[int, int]):
        self.mask = mask
        self.start = start
        self.end = end

        # Parámetros
        self.step_size = 5
        self.coverage_radius = 3
        self.validation_interval = 50  # Validar cada N pasos

        # Estado
        self.path: List[Tuple[int, int]] = []
        self.visited_map = np.zeros_like(mask, dtype=np.uint8)
        self.decision_stack: List[DecisionPoint] = []

        # Métricas
        self.total_mask_pixels = np.sum(mask > 0)
        self.best_coverage = 0.0

    def plan_path(self, max_iterations: int = 10000) -> Dict:
        """
        Planifica path con backtracking automático.
        """
        print("\n" + "="*70)
        print("INTELLIGENT WIRE PATH PLANNER V2 - Con Backtracking")
        print("="*70)

        self.path = [self.start]
        current = self.start
        cv2.circle(self.visited_map, self.start, self.coverage_radius, 255, -1)

        iteration = 0
        backtracks = 0
        max_backtracks = 5

        while iteration < max_iterations:
            iteration += 1

            # Verificar si llegamos al END
            dist_to_end = np.linalg.norm(np.array(current) - np.array(self.end))
            if dist_to_end < self.step_size * 2:
                self.path.append(self.end)
                coverage = self._compute_coverage()
                print(f"\n[OK] Llegado al END en iteracion {iteration}")
                print(f"     Cobertura final: {coverage*100:.1f}%")

                # Si cobertura es baja, hacer backtrack
                if coverage < 0.75 and backtracks < max_backtracks:
                    print(f"     [!] Cobertura baja ({coverage*100:.1f}%), intentando backtrack...")
                    backtrack_result = self._backtrack()
                    if backtrack_result:
                        current, iteration = backtrack_result
                        backtracks += 1
                        continue
                    else:
                        print("     [!] No se puede hacer backtrack, terminando")
                        break
                else:
                    break

            # Calcular siguiente paso
            options = self._get_movement_options(current)

            if not options:
                print(f"\n[!] Sin opciones en iter {iteration}, intentando backtrack...")
                backtrack_result = self._backtrack()
                if backtrack_result and backtracks < max_backtracks:
                    current, iteration = backtrack_result
                    backtracks += 1
                    continue
                else:
                    print("[!] No se puede hacer backtrack, terminando")
                    break

            # Evaluar opciones
            scored_options = self._score_options(current, options)

            # Si hay múltiples opciones buenas, guardar como decision point
            if len(scored_options) > 1 and scored_options[1][1] > 0.3:
                self._save_decision_point(current, scored_options, iteration)

            # Elegir mejor opción
            next_pos, score = scored_options[0]

            # Avanzar
            self.path.append(next_pos)
            current = next_pos
            cv2.circle(self.visited_map, next_pos, self.coverage_radius, 255, -1)

            # Validación progresiva
            if iteration % self.validation_interval == 0:
                coverage = self._compute_coverage()
                self.best_coverage = max(self.best_coverage, coverage)

                print(f"  Iter {iteration}: {len(self.path)} pts, coverage: {coverage*100:.1f}%, "
                      f"decisions: {len(self.decision_stack)}, backtracks: {backtracks}")

                # Si cobertura no está mejorando, considerar backtrack
                if iteration > self.validation_interval * 2:
                    if coverage < self.best_coverage * 0.95 and len(self.decision_stack) > 0:
                        if backtracks < max_backtracks:
                            print(f"     [!] Cobertura no mejora, haciendo backtrack...")
                            backtrack_result = self._backtrack()
                            if backtrack_result:
                                current, iteration = backtrack_result
                                backtracks += 1
                                continue

        final_coverage = self._compute_coverage()

        print(f"\n[OK] Path completado: {len(self.path)} puntos")
        print(f"     Cobertura final: {final_coverage*100:.1f}%")
        print(f"     Backtracks realizados: {backtracks}")

        return {
            'success': True,
            'path': self.path,
            'coverage': final_coverage,
            'num_decisions': len(self.decision_stack),
            'backtracks': backtracks
        }

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
        current_arr = np.array(current)

        for wx, wy in zip(wire_x, wire_y):
            dist = np.linalg.norm(np.array([wx - x, wy - y]))
            if self.step_size * 0.7 < dist < self.step_size * 2.5:
                options.append((wx, wy))

        return options

    def _score_options(self, current: Tuple[int, int],
                      options: List[Tuple[int, int]]) -> List[Tuple[Tuple[int, int], float]]:
        """
        Evalúa y puntúa todas las opciones.

        Scoring mejorado que considera:
        1. Momentum (continuar dirección)
        2. Acercamiento al END
        3. Evitar loops
        4. Alcanzabilidad (¿puedo llegar al END desde esta opción?)
        """
        current_arr = np.array(current)
        end_arr = np.array(self.end)

        # Calcular momentum
        momentum = self._get_momentum()

        scored = []

        for option in options:
            opt_arr = np.array(option)

            # Vector dirección
            direction = opt_arr - current_arr
            dist = np.linalg.norm(direction)

            if dist < 1e-6:
                continue

            direction = direction / dist

            # SCORE 1: Alineación con momentum (40%)
            if np.linalg.norm(momentum) > 0:
                alignment = np.dot(direction, momentum)
                momentum_score = max(0, alignment) ** 2
            else:
                momentum_score = 0.5

            # SCORE 2: Acercamiento al END (30%)
            dist_before = np.linalg.norm(current_arr - end_arr)
            dist_after = np.linalg.norm(opt_arr - end_arr)

            if dist_after < dist_before:
                end_score = 1.0
            else:
                # Penalizar alejarse del END
                end_score = max(0, 1.0 - (dist_after - dist_before) / dist_before)

            # SCORE 3: Evitar loops (10%)
            loop_penalty = 0.0
            if len(self.path) > 20:
                recent = np.array(self.path[-50:])
                dists = np.linalg.norm(recent - opt_arr, axis=1)
                min_dist = np.min(dists[:-3])  # Excluir últimos 3

                if min_dist < 10:
                    loop_penalty = -0.5

            # SCORE 4: Alcanzabilidad del END (20%)
            # ¿Hay un camino razonable de option a END?
            reachability_score = self._estimate_reachability(option, self.end)

            # Score total
            total = (momentum_score * 0.40 +
                    end_score * 0.30 +
                    reachability_score * 0.20 +
                    loop_penalty * 0.10)

            scored.append((option, total))

        # Ordenar por score descendente
        scored.sort(key=lambda x: x[1], reverse=True)

        return scored

    def _estimate_reachability(self, from_pos: Tuple[int, int],
                               to_pos: Tuple[int, int]) -> float:
        """
        Estima si es alcanzable llegar de from_pos a to_pos.

        Usa una heurística rápida: ¿hay suficiente máscara en el camino directo?
        """
        # Línea de Bresenham
        line_points = self._bresenham_line(from_pos[0], from_pos[1],
                                          to_pos[0], to_pos[1])

        if not line_points:
            return 0.5

        # Contar cuántos puntos de la línea están en máscara
        on_mask = 0
        for x, y in line_points:
            if 0 <= y < self.mask.shape[0] and 0 <= x < self.mask.shape[1]:
                if self.mask[y, x] > 0:
                    on_mask += 1

        ratio = on_mask / len(line_points)

        # Si > 50% de la línea directa está en máscara, es alcanzable
        return min(1.0, ratio * 2.0)

    def _bresenham_line(self, x0: int, y0: int, x1: int, y1: int) -> List[Tuple[int, int]]:
        """Algoritmo de Bresenham para línea."""
        points = []
        dx = abs(x1 - x0)
        dy = abs(y1 - y0)
        sx = 1 if x0 < x1 else -1
        sy = 1 if y0 < y1 else -1
        err = dx - dy

        x, y = x0, y0

        while True:
            points.append((x, y))
            if x == x1 and y == y1:
                break
            e2 = 2 * err
            if e2 > -dy:
                err -= dy
                x += sx
            if e2 < dx:
                err += dx
                y += sy

        return points

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

    def _save_decision_point(self, current: Tuple[int, int],
                            scored_options: List[Tuple[Tuple[int, int], float]],
                            iteration: int):
        """Guarda un decision point para posible backtrack."""
        # Solo guardar si hay opciones alternativas razonables
        if len(scored_options) < 2:
            return

        # Solo guardar si la segunda opción tiene score > 30% de la primera
        if scored_options[1][1] < scored_options[0][1] * 0.3:
            return

        # Guardar estado actual
        state = PathState(
            path=copy.deepcopy(self.path),
            visited_map=self.visited_map.copy(),
            coverage=self._compute_coverage(),
            current_pos=current
        )

        decision = DecisionPoint(
            state=state,
            options=scored_options[:3],  # Guardar top 3 opciones
            chosen_index=0,
            iteration=iteration
        )

        self.decision_stack.append(decision)

        # Limitar tamaño del stack
        if len(self.decision_stack) > 10:
            self.decision_stack.pop(0)

    def _backtrack(self) -> Optional[Tuple[Tuple[int, int], int]]:
        """
        Hace backtrack al último decision point y prueba otra opción.

        Returns:
            (new_current_pos, new_iteration) si backtrack exitoso, None si no
        """
        if not self.decision_stack:
            return None

        # Buscar decision point con opciones no exploradas
        for i in range(len(self.decision_stack) - 1, -1, -1):
            decision = self.decision_stack[i]

            # Si ya probamos todas las opciones, continuar
            if decision.chosen_index >= len(decision.options) - 1:
                continue

            # Probar siguiente opción
            decision.chosen_index += 1
            next_option = decision.options[decision.chosen_index]

            print(f"     [>>] Backtrack a iter {decision.iteration}, "
                  f"probando opcion {decision.chosen_index + 1}/{len(decision.options)} "
                  f"(score: {next_option[1]:.2f})")

            # Restaurar estado
            self.path = copy.deepcopy(decision.state.path)
            self.visited_map = decision.state.visited_map.copy()

            # Agregar la nueva opción
            new_pos = next_option[0]
            self.path.append(new_pos)
            cv2.circle(self.visited_map, new_pos, self.coverage_radius, 255, -1)

            # Eliminar decision points posteriores
            self.decision_stack = self.decision_stack[:i+1]

            return (new_pos, decision.iteration + 1)

        return None

    def _compute_coverage(self) -> float:
        """Calcula cobertura actual."""
        covered = np.logical_and(self.mask > 0, self.visited_map > 0)
        return np.sum(covered) / self.total_mask_pixels

    def visualize(self, output_path: str):
        """Visualiza el resultado."""
        vis = cv2.cvtColor(self.mask, cv2.COLOR_GRAY2BGR)

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
        cv2.circle(vis, self.end, 15, (0, 0, 255), -1)

        coverage = self._compute_coverage()

        plt.figure(figsize=(16, 14))
        plt.imshow(cv2.cvtColor(vis, cv2.COLOR_BGR2RGB))
        plt.title(f"Intelligent Wire Path V2 - {len(self.path)} pts | "
                 f"Coverage: {coverage*100:.1f}%",
                 fontsize=14, weight='bold')
        plt.axis('off')
        plt.tight_layout()
        plt.savefig(output_path, dpi=150, bbox_inches='tight')
        print(f"\n[OK] Visualizacion guardada: {output_path}")
        plt.show()


def main():
    """Test del planner V2."""
    mask_path = r"c:\Users\jf19s\Desktop\PROYECTOS\ACTUALES\STEREO_PHOTOGRAMMETRY_CM5\data\results\debug\cable_mask_left.png"

    mask = cv2.imread(mask_path, cv2.IMREAD_GRAYSCALE)
    _, mask = cv2.threshold(mask, 127, 255, cv2.THRESH_BINARY)

    start = (1248, 668)
    end = (1297, 945)

    planner = IntelligentWirePathPlannerV2(mask, start, end)
    result = planner.plan_path(max_iterations=10000)

    if result['success']:
        planner.visualize('data/results/debug/intelligent_wire_path_v2.png')

    return result


if __name__ == "__main__":
    main()
