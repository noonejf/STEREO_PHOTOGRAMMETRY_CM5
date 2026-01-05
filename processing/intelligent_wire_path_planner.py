#!/usr/bin/env python3
"""
Intelligent Wire Path Planner - Sistema avanzado de reconstrucción 2D de cuerdas.

Características:
- Detección inteligente de puntos de conflicto (cruces, bifurcaciones)
- Toma de decisiones geométrica basada en propiedades físicas
- Validación de cobertura con backtracking automático
- Prevención de garabatos y loops no naturales
"""

import cv2
import numpy as np
import matplotlib.pyplot as plt
from typing import List, Tuple, Dict, Optional, Set
from dataclasses import dataclass
from collections import deque
import heapq


@dataclass
class ConflictPoint:
    """Punto de conflicto detectado en la máscara."""
    location: Tuple[int, int]
    type: str  # 'junction', 'bifurcation', 'crossing', 'parallel_touch'
    options: List[Tuple[int, int]]  # Posibles direcciones
    confidence: float  # Confianza en la clasificación


@dataclass
class PathSegment:
    """Segmento de path con metadata."""
    points: List[Tuple[int, int]]
    curvature_score: float
    smoothness_score: float
    coverage_score: float

    def total_score(self) -> float:
        """Score total del segmento."""
        return (self.curvature_score * 0.4 +
                self.smoothness_score * 0.4 +
                self.coverage_score * 0.2)


class ConflictPointDetector:
    """Detecta y clasifica puntos de conflicto en la máscara."""

    def __init__(self, mask: np.ndarray):
        self.mask = mask
        self.skeleton = None
        self.conflict_points: List[ConflictPoint] = []

    def detect_conflicts(self) -> List[ConflictPoint]:
        """Detecta todos los puntos de conflicto en la máscara."""
        # Generar skeleton
        mask_binary = (self.mask > 0).astype(np.uint8)
        self.skeleton = cv2.ximgproc.thinning(mask_binary * 255)
        self.skeleton = (self.skeleton > 0).astype(np.uint8)

        conflicts = []
        coords = np.column_stack(np.where(self.skeleton > 0))

        for y, x in coords:
            num_neighbors = self._count_neighbors(x, y)

            # Punto de conflicto: más de 2 vecinos (bifurcación/cruce)
            if num_neighbors > 2:
                conflict = self._classify_conflict(x, y, num_neighbors)
                if conflict:
                    conflicts.append(conflict)

        self.conflict_points = conflicts
        print(f"  Detectados {len(conflicts)} puntos de conflicto")
        return conflicts

    def _count_neighbors(self, x: int, y: int) -> int:
        """Cuenta vecinos conectados en el skeleton."""
        h, w = self.skeleton.shape
        count = 0

        for dy in [-1, 0, 1]:
            for dx in [-1, 0, 1]:
                if dx == 0 and dy == 0:
                    continue
                nx, ny = x + dx, y + dy
                if 0 <= nx < w and 0 <= ny < h:
                    if self.skeleton[ny, nx] > 0:
                        count += 1
        return count

    def _classify_conflict(self, x: int, y: int, num_neighbors: int) -> Optional[ConflictPoint]:
        """Clasifica el tipo de conflicto."""
        # Obtener direcciones de vecinos
        h, w = self.skeleton.shape
        neighbor_dirs = []

        for dy in [-1, 0, 1]:
            for dx in [-1, 0, 1]:
                if dx == 0 and dy == 0:
                    continue
                nx, ny = x + dx, y + dy
                if 0 <= nx < w and 0 <= ny < h:
                    if self.skeleton[ny, nx] > 0:
                        neighbor_dirs.append((nx, ny))

        if len(neighbor_dirs) < 3:
            return None

        # Analizar ángulos entre vecinos para clasificar
        conflict_type = self._determine_conflict_type(x, y, neighbor_dirs)

        return ConflictPoint(
            location=(x, y),
            type=conflict_type,
            options=neighbor_dirs,
            confidence=0.8  # Por ahora fijo
        )

    def _determine_conflict_type(self, x: int, y: int,
                                 neighbors: List[Tuple[int, int]]) -> str:
        """Determina el tipo específico de conflicto."""
        if len(neighbors) == 3:
            # Analizar si es bifurcación real o cruce
            angles = []
            for n in neighbors:
                dx, dy = n[0] - x, n[1] - y
                angle = np.arctan2(dy, dx)
                angles.append(angle)

            angles = sorted(angles)
            angle_diffs = [angles[i+1] - angles[i] for i in range(len(angles)-1)]
            angle_diffs.append(2*np.pi - angles[-1] + angles[0])

            # Si hay dos ángulos ~180° aparte → probable crossing
            max_diff = max(angle_diffs)
            if max_diff > 2.5:  # ~143°
                return 'crossing'
            else:
                return 'bifurcation'

        elif len(neighbors) == 4:
            return 'crossing'  # Muy probable cruce real

        else:
            return 'junction'  # Unión compleja


class GeometricDecisionMaker:
    """Toma decisiones geométricas en puntos de conflicto."""

    def __init__(self, mask: np.ndarray):
        self.mask = mask
        self.history_window = 10  # Ventana para calcular momentum

    def score_options(self, current_pos: Tuple[int, int],
                     path_history: List[Tuple[int, int]],
                     options: List[Tuple[int, int]],
                     conflict: ConflictPoint) -> List[Tuple[Tuple[int, int], float]]:
        """
        Evalúa y puntúa todas las opciones disponibles.

        Returns:
            Lista de (opción, score) ordenada por score descendente
        """
        scored_options = []

        # Calcular dirección de momentum
        momentum_dir = self._compute_momentum(path_history)

        for option in options:
            # Ya visitado? Penalizar fuertemente
            if option in path_history[-20:]:  # Últimos 20 puntos
                score = -1000.0
            else:
                score = self._score_single_option(
                    current_pos, option, momentum_dir,
                    path_history, conflict
                )

            scored_options.append((option, score))

        # Ordenar por score descendente
        scored_options.sort(key=lambda x: x[1], reverse=True)
        return scored_options

    def _compute_momentum(self, path_history: List[Tuple[int, int]]) -> np.ndarray:
        """Calcula la dirección de momentum del path."""
        if len(path_history) < 2:
            return np.array([0.0, 0.0])

        # Usar últimos N puntos
        window = min(self.history_window, len(path_history))
        recent = path_history[-window:]

        # Dirección promedio ponderada (más peso a puntos recientes)
        directions = []
        weights = []

        for i in range(1, len(recent)):
            p1 = np.array(recent[i-1])
            p2 = np.array(recent[i])
            direction = p2 - p1
            norm = np.linalg.norm(direction)

            if norm > 0:
                directions.append(direction / norm)
                weights.append(i)  # Más peso a puntos recientes

        if not directions:
            return np.array([0.0, 0.0])

        # Promedio ponderado
        directions = np.array(directions)
        weights = np.array(weights)
        weights = weights / weights.sum()

        momentum = np.sum(directions * weights[:, np.newaxis], axis=0)
        norm = np.linalg.norm(momentum)

        return momentum / norm if norm > 0 else np.array([0.0, 0.0])

    def _score_single_option(self, current_pos: Tuple[int, int],
                            option: Tuple[int, int],
                            momentum_dir: np.ndarray,
                            path_history: List[Tuple[int, int]],
                            conflict: ConflictPoint) -> float:
        """Puntúa una opción individual."""
        current = np.array(current_pos)
        opt = np.array(option)

        # Vector hacia la opción
        to_option = opt - current
        dist = np.linalg.norm(to_option)

        if dist < 1e-6:
            return -1000.0

        direction = to_option / dist

        # SCORE 1: Alineación con momentum (muy importante)
        if np.linalg.norm(momentum_dir) > 0:
            alignment = np.dot(direction, momentum_dir)
            alignment_score = max(0, alignment) ** 3  # Penalizar fuertemente desalineación
        else:
            alignment_score = 0.5

        # SCORE 2: Curvatura (penalizar cambios bruscos)
        curvature_score = self._compute_curvature_score(path_history, option)

        # SCORE 3: Continuidad del flujo (la opción debe seguir la máscara)
        flow_score = self._compute_flow_score(current_pos, option)

        # SCORE 4: Evitar loops/garabatos (detectar si forma loop pequeño)
        loop_penalty = self._detect_loop_penalty(path_history, option)

        # Combinar scores
        total = (alignment_score * 0.40 +
                curvature_score * 0.25 +
                flow_score * 0.25 +
                loop_penalty * 0.10)

        return total

    def _compute_curvature_score(self, path_history: List[Tuple[int, int]],
                                option: Tuple[int, int]) -> float:
        """Calcula score basado en curvatura (penaliza cambios bruscos)."""
        if len(path_history) < 3:
            return 1.0

        # Usar últimos 3 puntos + opción
        recent = path_history[-3:]
        points = [np.array(p) for p in recent] + [np.array(option)]

        # Calcular curvatura aproximada
        curvatures = []
        for i in range(1, len(points)-1):
            v1 = points[i] - points[i-1]
            v2 = points[i+1] - points[i]

            n1 = np.linalg.norm(v1)
            n2 = np.linalg.norm(v2)

            if n1 < 1e-6 or n2 < 1e-6:
                continue

            v1 = v1 / n1
            v2 = v2 / n2

            # Ángulo entre vectores
            dot = np.clip(np.dot(v1, v2), -1.0, 1.0)
            angle = np.arccos(dot)
            curvatures.append(angle)

        if not curvatures:
            return 1.0

        avg_curvature = np.mean(curvatures)

        # Penalizar alta curvatura (garabatos)
        # Curvatura baja (< 30°) → score alto
        # Curvatura alta (> 90°) → score bajo
        score = np.exp(-avg_curvature * 2.0)  # Decay exponencial
        return max(0.0, min(1.0, score))

    def _compute_flow_score(self, current_pos: Tuple[int, int],
                           option: Tuple[int, int]) -> float:
        """Evalúa si la opción sigue el flujo natural de la máscara."""
        # Verificar que el camino hacia la opción esté mayormente en la máscara
        x1, y1 = current_pos
        x2, y2 = option

        # Usar Bresenham para obtener píxeles en la línea
        line_points = self._bresenham_line(x1, y1, x2, y2)

        if not line_points:
            return 0.0

        # Contar cuántos están en la máscara
        on_mask = sum(1 for x, y in line_points
                     if 0 <= y < self.mask.shape[0] and
                        0 <= x < self.mask.shape[1] and
                        self.mask[y, x] > 0)

        ratio = on_mask / len(line_points)
        return ratio

    def _detect_loop_penalty(self, path_history: List[Tuple[int, int]],
                            option: Tuple[int, int]) -> float:
        """Detecta si la opción crearía un loop/garabato."""
        if len(path_history) < 10:
            return 0.0

        opt = np.array(option)

        # Verificar si option está muy cerca de puntos recientes
        # (pero no inmediatos - esos son válidos)
        recent_window = path_history[-30:-5]  # Excluir últimos 5

        if not recent_window:
            return 0.0

        recent = np.array(recent_window)
        distances = np.linalg.norm(recent - opt, axis=1)
        min_dist = np.min(distances) if len(distances) > 0 else 1000

        # Si está muy cerca de punto reciente → probable loop
        if min_dist < 10:
            return -0.5  # Penalización

        return 0.0

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


class CoverageValidator:
    """Valida cobertura del path y detecta regiones no visitadas."""

    def __init__(self, mask: np.ndarray):
        self.mask = mask
        self.total_mask_pixels = np.sum(mask > 0)

    def validate_coverage(self, path: List[Tuple[int, int]],
                         radius: int = 5) -> Dict:
        """
        Valida la cobertura del path sobre la máscara.

        Returns:
            Dict con métricas de cobertura
        """
        # Crear mapa de visitados
        visited_map = np.zeros_like(self.mask, dtype=np.uint8)

        for x, y in path:
            cv2.circle(visited_map, (x, y), radius, 255, -1)

        # Calcular píxeles cubiertos
        covered = np.logical_and(self.mask > 0, visited_map > 0)
        covered_pixels = np.sum(covered)
        coverage_ratio = covered_pixels / self.total_mask_pixels

        # Detectar regiones no visitadas
        unvisited = np.logical_and(self.mask > 0, visited_map == 0)
        unvisited_pixels = np.sum(unvisited)

        # Encontrar componentes conexas de regiones no visitadas
        unvisited_uint8 = unvisited.astype(np.uint8) * 255
        num_regions, labels = cv2.connectedComponents(unvisited_uint8)

        # Analizar tamaño de regiones no visitadas
        large_unvisited_regions = 0
        for region_id in range(1, num_regions):
            region_size = np.sum(labels == region_id)
            if region_size > 50:  # Región significativa
                large_unvisited_regions += 1

        return {
            'coverage_ratio': coverage_ratio,
            'covered_pixels': covered_pixels,
            'unvisited_pixels': unvisited_pixels,
            'num_unvisited_regions': num_regions - 1,
            'large_unvisited_regions': large_unvisited_regions,
            'is_valid': coverage_ratio > 0.85 and large_unvisited_regions == 0
        }


class IntelligentWirePathPlanner:
    """Planner principal que orquesta todo el sistema."""

    def __init__(self, mask: np.ndarray, start: Tuple[int, int], end: Tuple[int, int]):
        self.mask = mask
        self.start = start
        self.end = end

        self.conflict_detector = ConflictPointDetector(mask)
        self.decision_maker = GeometricDecisionMaker(mask)
        self.validator = CoverageValidator(mask)

        self.conflicts: List[ConflictPoint] = []
        self.best_path: Optional[List[Tuple[int, int]]] = None
        self.best_coverage: float = 0.0

    def plan_path(self, max_attempts: int = 3) -> Dict:
        """
        Planifica el path con backtracking si es necesario.

        Returns:
            Dict con el mejor path y métricas
        """
        print("\n" + "="*70)
        print("INTELLIGENT WIRE PATH PLANNER")
        print("="*70)

        # Detectar puntos de conflicto
        print("\n[1] Detectando puntos de conflicto...")
        self.conflicts = self.conflict_detector.detect_conflicts()

        # Intentar planificar path (con posible backtracking)
        print(f"\n[2] Planificando path (max {max_attempts} intentos)...")

        for attempt in range(max_attempts):
            print(f"\n  Intento {attempt + 1}/{max_attempts}...")

            path = self._plan_single_attempt(attempt)

            if not path:
                print("    [X] Path no encontrado")
                continue

            # Validar cobertura
            print(f"    Path generado: {len(path)} puntos")
            coverage = self.validator.validate_coverage(path)

            print(f"    Cobertura: {coverage['coverage_ratio']*100:.1f}%")
            print(f"    Regiones grandes no visitadas: {coverage['large_unvisited_regions']}")

            # Guardar si es mejor
            if coverage['coverage_ratio'] > self.best_coverage:
                self.best_path = path
                self.best_coverage = coverage['coverage_ratio']

            # Si es válido, terminar
            if coverage['is_valid']:
                print("    [OK] Path valido encontrado!")
                break

        # Resultado final
        print("\n" + "="*70)
        if self.best_path:
            final_coverage = self.validator.validate_coverage(self.best_path)
            print(f"[OK] MEJOR PATH: {len(self.best_path)} puntos")
            print(f"     Cobertura: {final_coverage['coverage_ratio']*100:.1f}%")

            return {
                'success': True,
                'path': self.best_path,
                'coverage': final_coverage,
                'num_conflicts': len(self.conflicts)
            }
        else:
            print("[X] No se encontro path valido")
            return {
                'success': False,
                'error': 'No valid path found'
            }

    def _plan_single_attempt(self, attempt: int) -> Optional[List[Tuple[int, int]]]:
        """Planifica un intento de path."""
        path = [self.start]
        visited = np.zeros_like(self.mask, dtype=np.uint8)
        cv2.circle(visited, self.start, 3, 255, -1)

        current = self.start
        max_iterations = 10000
        step_size = 5

        for iteration in range(max_iterations):
            # Verificar si llegamos al END
            dist_to_end = np.linalg.norm(np.array(current) - np.array(self.end))
            if dist_to_end < step_size * 2:
                path.append(self.end)
                return path

            # Obtener opciones de movimiento
            options = self._get_movement_options(current, visited, step_size)

            if not options:
                # Sin opciones, intento fallido
                return None

            # Verificar si estamos en punto de conflicto
            in_conflict = self._is_near_conflict(current)

            if in_conflict and len(options) > 1:
                # Usar decision maker para elegir
                conflict = in_conflict
                scored = self.decision_maker.score_options(
                    current, path, options, conflict
                )

                # Elegir mejor opción (con algo de aleatoriedad en intentos posteriores)
                if attempt > 0 and len(scored) > 1:
                    # Intentos posteriores: explorar opciones alternativas
                    idx = min(attempt, len(scored) - 1)
                    next_pos = scored[idx][0]
                else:
                    next_pos = scored[0][0]
            else:
                # Fuera de conflicto: greedy simple con momentum
                next_pos = self._greedy_next_step(current, path, options)

            # Avanzar
            path.append(next_pos)
            current = next_pos
            cv2.circle(visited, next_pos, step_size // 2, 255, -1)

        return path

    def _get_movement_options(self, current: Tuple[int, int],
                             visited: np.ndarray,
                             step_size: int) -> List[Tuple[int, int]]:
        """Obtiene opciones de movimiento desde posición actual."""
        x, y = current
        search_radius = step_size * 3

        # Región de búsqueda
        y_min = max(0, y - search_radius)
        y_max = min(self.mask.shape[0], y + search_radius + 1)
        x_min = max(0, x - search_radius)
        x_max = min(self.mask.shape[1], x + search_radius + 1)

        mask_region = self.mask[y_min:y_max, x_min:x_max]
        visited_region = visited[y_min:y_max, x_min:x_max]

        # Píxeles de cuerda no visitados
        unvisited_wire = np.logical_and(mask_region > 0, visited_region == 0)

        if not unvisited_wire.any():
            # Permitir visitados (para cruces)
            wire_pixels = (mask_region > 0)
        else:
            wire_pixels = unvisited_wire

        if not wire_pixels.any():
            return []

        # Obtener coordenadas
        wire_y, wire_x = np.where(wire_pixels)
        wire_y = wire_y + y_min
        wire_x = wire_x + x_min

        # Filtrar por distancia
        options = []
        for wx, wy in zip(wire_x, wire_y):
            dist = np.linalg.norm(np.array([wx - x, wy - y]))
            if step_size * 0.7 < dist < step_size * 2.5:
                options.append((wx, wy))

        return options

    def _is_near_conflict(self, pos: Tuple[int, int]) -> Optional[ConflictPoint]:
        """Verifica si la posición está cerca de un punto de conflicto."""
        pos_arr = np.array(pos)

        for conflict in self.conflicts:
            conf_pos = np.array(conflict.location)
            dist = np.linalg.norm(pos_arr - conf_pos)

            if dist < 15:  # Radio de influencia
                return conflict

        return None

    def _greedy_next_step(self, current: Tuple[int, int],
                         path: List[Tuple[int, int]],
                         options: List[Tuple[int, int]]) -> Tuple[int, int]:
        """Selección greedy con momentum para áreas sin conflicto."""
        if len(path) < 2:
            # Sin momentum, elegir más cercano al END
            end_arr = np.array(self.end)
            distances = [np.linalg.norm(np.array(opt) - end_arr) for opt in options]
            return options[np.argmin(distances)]

        # Con momentum
        momentum = self.decision_maker._compute_momentum(path)
        current_arr = np.array(current)

        best_score = -1000
        best_option = options[0]

        for opt in options:
            opt_arr = np.array(opt)
            direction = opt_arr - current_arr
            norm = np.linalg.norm(direction)

            if norm < 1e-6:
                continue

            direction = direction / norm

            # Score: alineación con momentum
            alignment = np.dot(direction, momentum) if np.linalg.norm(momentum) > 0 else 0

            # También considerar cercanía al END
            dist_to_end = np.linalg.norm(opt_arr - np.array(self.end))
            end_score = 1.0 / (dist_to_end + 1.0)

            total = alignment * 0.7 + end_score * 0.3

            if total > best_score:
                best_score = total
                best_option = opt

        return best_option

    def visualize_result(self, output_path: str):
        """Visualiza el resultado final."""
        if not self.best_path:
            print("[!] No hay path para visualizar")
            return

        # Crear visualización
        vis = cv2.cvtColor(self.mask, cv2.COLOR_GRAY2BGR)

        # Dibujar path con gradiente
        path_array = np.array(self.best_path, dtype=np.int32)

        for i in range(len(path_array) - 1):
            p1 = tuple(path_array[i])
            p2 = tuple(path_array[i+1])

            # Color gradiente (azul → verde → amarillo)
            ratio = i / len(path_array)
            color_val = int(ratio * 255)
            color = cv2.applyColorMap(np.array([[color_val]], dtype=np.uint8),
                                     cv2.COLORMAP_VIRIDIS)[0, 0]
            color = tuple(map(int, color))

            cv2.line(vis, p1, p2, color, 2)

        # Marcar START y END
        cv2.circle(vis, self.start, 12, (0, 255, 0), -1)
        cv2.circle(vis, self.end, 12, (0, 0, 255), -1)

        # Marcar puntos de conflicto
        for conflict in self.conflicts:
            color = (255, 255, 0) if conflict.type == 'crossing' else (255, 0, 255)
            cv2.circle(vis, conflict.location, 8, color, 2)

        # Info
        coverage = self.validator.validate_coverage(self.best_path)

        plt.figure(figsize=(16, 14))
        plt.imshow(cv2.cvtColor(vis, cv2.COLOR_BGR2RGB))
        plt.title(f"Intelligent Wire Path - {len(self.best_path)} pts | "
                 f"Coverage: {coverage['coverage_ratio']*100:.1f}% | "
                 f"Conflicts: {len(self.conflicts)}",
                 fontsize=14, weight='bold')
        plt.axis('off')
        plt.tight_layout()
        plt.savefig(output_path, dpi=150, bbox_inches='tight')
        print(f"\n[OK] Visualizacion guardada: {output_path}")
        plt.show()


def main():
    """Test del planner."""
    mask_path = r"c:\Users\jf19s\Desktop\PROYECTOS\ACTUALES\STEREO_PHOTOGRAMMETRY_CM5\data\results\debug\cable_mask_left.png"

    # Cargar máscara
    mask = cv2.imread(mask_path, cv2.IMREAD_GRAYSCALE)
    _, mask = cv2.threshold(mask, 127, 255, cv2.THRESH_BINARY)

    # Endpoints conocidos
    start = (1248, 668)
    end = (1297, 945)

    # Crear planner
    planner = IntelligentWirePathPlanner(mask, start, end)

    # Planificar
    result = planner.plan_path(max_attempts=3)

    # Visualizar
    if result['success']:
        planner.visualize_result('data/results/debug/intelligent_wire_path.png')

    return result


if __name__ == "__main__":
    main()
