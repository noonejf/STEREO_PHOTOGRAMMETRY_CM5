#!/usr/bin/env python3
"""
Backtracking Wire Planner - Sistema con backtracking REAL y sin saltos.

Características:
1. Limpia máscara para eliminar conexiones falsas
2. Detecta componentes separados
3. NO permite saltos entre componentes desconectados
4. Guarda checkpoints en puntos de decisión
5. Cuando falla, REGRESA al checkpoint y prueba otra opción
6. Valida usando skeleton (no píxeles gruesos)
"""

import cv2
import numpy as np
import matplotlib.pyplot as plt
from typing import List, Tuple, Dict, Optional, Set
from dataclasses import dataclass
import copy


@dataclass
class Checkpoint:
    """Checkpoint guardado en punto de decisión."""
    path: List[Tuple[int, int]]
    visited_map: np.ndarray
    current_pos: Tuple[int, int]
    iteration: int
    options: List[Tuple[int, int]]  # Opciones disponibles
    tried_options: Set[Tuple[int, int]]  # Opciones ya probadas


class BacktrackingWirePlanner:
    """Planner con backtracking real."""

    def __init__(self, mask: np.ndarray, start: Tuple[int, int], end: Tuple[int, int]):
        self.original_mask = mask.copy()
        self.start = start
        self.end = end

        # PASO 1: Limpiar máscara
        print("\n[1/6] Limpiando mascara...")
        self.mask = self._clean_mask(mask)
        print(f"      Ruido eliminado: {np.sum(mask > 0) - np.sum(self.mask > 0)} px")

        # PASO 2: Detectar componentes
        print("\n[2/6] Detectando componentes...")
        self.num_components, self.component_labels = cv2.connectedComponents(self.mask)
        print(f"      Componentes: {self.num_components - 1}")

        # PASO 3: Generar skeleton
        print("\n[3/6] Generando skeleton...")
        mask_binary = (self.mask > 0).astype(np.uint8)
        self.skeleton = cv2.ximgproc.thinning(mask_binary * 255)
        self.skeleton = (self.skeleton > 0).astype(np.uint8)
        print(f"      Skeleton: {np.sum(self.skeleton > 0)} px")

        # Parámetros
        self.step_size = 5
        self.coverage_radius = 8
        self.total_skeleton_pixels = np.sum(self.skeleton > 0)

        # Estado
        self.path: List[Tuple[int, int]] = []
        self.visited_map = np.zeros_like(self.mask, dtype=np.uint8)
        self.checkpoints: List[Checkpoint] = []

        # Cache para skeleton coverage (se actualiza cada N iteraciones)
        self._skeleton_coverage_cache = 0.0
        self._coverage_cache_iter = 0

    def _clean_mask(self, mask: np.ndarray) -> np.ndarray:
        """Limpia máscara eliminando conexiones falsas."""
        _, binary = cv2.threshold(mask, 127, 255, cv2.THRESH_BINARY)
        kernel_erode = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
        eroded = cv2.erode(binary, kernel_erode, iterations=2)
        kernel_dilate = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
        dilated = cv2.dilate(eroded, kernel_dilate, iterations=1)
        return dilated

    def plan_path(self, max_iterations: int = 20000) -> Dict:
        """Planifica con backtracking real."""
        print("\n[4/6] Planificando path con backtracking...")
        print("="*70)

        attempt = 0
        max_attempts = 5

        while attempt < max_attempts:
            attempt += 1
            print(f"\n>>> INTENTO {attempt}/{max_attempts}")

            # Resetear estado
            self.path = [self.start]
            self.visited_map = np.zeros_like(self.mask, dtype=np.uint8)
            cv2.circle(self.visited_map, self.start, self.coverage_radius, 255, -1)
            self.checkpoints = []

            # Ejecutar path planning
            result = self._execute_path_planning(max_iterations)

            if result == 'reached_end':
                # Llegó al END, validar
                coverage = self._validate_skeleton_coverage()

                if coverage >= 0.95:  # 95% o más
                    print(f"\n[OK] Path VALIDO! Cobertura: {coverage*100:.1f}%")
                    return self._build_success_result(coverage)
                else:
                    print(f"\n[!] Path INVALIDO - Cobertura: {coverage*100:.1f}%")

                    # Intentar backtrack
                    if self.checkpoints:
                        print(f"[>>] Haciendo backtrack (quedan {len(self.checkpoints)} checkpoints)...")
                        backtrack_success = self._backtrack()
                        if not backtrack_success:
                            print("[!] No hay más opciones en checkpoints")
                            continue
                    else:
                        print("[!] No hay checkpoints para backtrack")
                        continue
            elif result == 'no_path':
                print("\n[!] Sin camino encontrado")
                if self.checkpoints:
                    self._backtrack()
                else:
                    break

        print("\n[X] No se pudo encontrar path válido después de todos los intentos")
        coverage = self._validate_skeleton_coverage()
        return self._build_failure_result(coverage)

    def _execute_path_planning(self, max_iterations: int) -> str:
        """
        Ejecuta path planning con salto a skeleton sin cubrir.

        Returns:
            'reached_end' si llegó al END
            'no_path' si se quedó sin opciones
        """
        current = self.start
        iteration = 0
        jumps_remaining = 10  # Máximo de saltos permitidos

        while iteration < max_iterations:
            iteration += 1

            # Actualizar cache de skeleton coverage cada 100 iteraciones
            if iteration % 100 == 0:
                self._skeleton_coverage_cache = self._validate_skeleton_coverage()
                self._coverage_cache_iter = iteration

            # ¿Llegamos al END? SOLO permitir si cobertura es alta (>90%)
            dist_to_end = np.linalg.norm(np.array(current) - np.array(self.end))
            if dist_to_end < self.step_size * 2 and self._skeleton_coverage_cache > 0.90:
                self.path.append(self.end)
                cv2.circle(self.visited_map, self.end, self.coverage_radius, 255, -1)
                return 'reached_end'

            # Obtener opciones (SOLO del mismo componente)
            options = self._get_movement_options_same_component(current)

            if not options:
                # SIN OPCIONES: Intentar saltar al skeleton sin cubrir
                if jumps_remaining > 0:
                    jump_target = self._find_nearest_uncovered_skeleton(current)
                    if jump_target is not None:
                        print(f"  [SALTO] Iter {iteration}: Saltando de {current} a {jump_target}")
                        current = jump_target
                        self.path.append(current)
                        cv2.circle(self.visited_map, current, self.coverage_radius, 255, -1)
                        jumps_remaining -= 1
                        continue
                return 'no_path'

            # Si hay múltiples opciones, guardar checkpoint
            if len(options) > 1 and iteration % 50 == 0:
                self._save_checkpoint(current, options, iteration)

            # Elegir mejor opción
            scored = self._score_options(current, options)
            next_pos = scored[0][0]

            # Avanzar
            self.path.append(next_pos)
            current = next_pos
            cv2.circle(self.visited_map, next_pos, self.coverage_radius, 255, -1)

            if iteration % 500 == 0:
                print(f"  Iter {iteration}: {len(self.path)} pts, skeleton: {self._skeleton_coverage_cache*100:.1f}%")

        return 'no_path'

    def _find_nearest_uncovered_skeleton(self, current: Tuple[int, int]) -> Optional[Tuple[int, int]]:
        """
        Encuentra el punto del skeleton sin cubrir más cercano al path.
        """
        # Dilatar visited para ver qué skeleton está cubierto
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE,
                                          (self.coverage_radius * 2, self.coverage_radius * 2))
        visited_dilated = cv2.dilate(self.visited_map, kernel, iterations=1)

        # Skeleton sin cubrir
        skeleton_uncovered = np.logical_and(self.skeleton > 0, visited_dilated == 0)
        uncovered_points = np.argwhere(skeleton_uncovered)

        if len(uncovered_points) == 0:
            return None

        # Convertir a (x, y)
        uncovered_points = uncovered_points[:, [1, 0]]

        # Encontrar el más cercano al punto actual
        current_arr = np.array(current)
        distances = np.linalg.norm(uncovered_points - current_arr, axis=1)
        nearest_idx = np.argmin(distances)
        nearest_point = tuple(uncovered_points[nearest_idx])

        # Verificar que esté en el mismo componente
        x, y = nearest_point
        if 0 <= y < self.component_labels.shape[0] and 0 <= x < self.component_labels.shape[1]:
            target_component = self.component_labels[y, x]
            current_component = self.component_labels[current[1], current[0]]

            if target_component == current_component and target_component > 0:
                return nearest_point

        # Si el más cercano no está en el mismo componente, buscar otro
        for idx in np.argsort(distances):
            point = tuple(uncovered_points[idx])
            x, y = point
            if 0 <= y < self.component_labels.shape[0] and 0 <= x < self.component_labels.shape[1]:
                target_component = self.component_labels[y, x]
                if target_component == current_component and target_component > 0:
                    return point

        return None

    def _get_movement_options_same_component(self, current: Tuple[int, int]) -> List[Tuple[int, int]]:
        """
        Obtiene opciones de movimiento SOLO dentro del mismo componente.

        CLAVE: No permite saltos entre componentes desconectados.
        """
        x, y = current

        # ¿En qué componente estamos?
        if 0 <= y < self.component_labels.shape[0] and 0 <= x < self.component_labels.shape[1]:
            current_component = self.component_labels[y, x]
        else:
            return []

        search_radius = self.step_size * 3

        y_min = max(0, y - search_radius)
        y_max = min(self.mask.shape[0], y + search_radius + 1)
        x_min = max(0, x - search_radius)
        x_max = min(self.mask.shape[1], x + search_radius + 1)

        mask_region = self.mask[y_min:y_max, x_min:x_max]
        visited_region = self.visited_map[y_min:y_max, x_min:x_max]
        component_region = self.component_labels[y_min:y_max, x_min:x_max]

        # Píxeles no visitados del MISMO componente
        same_component = (component_region == current_component)
        unvisited_wire = np.logical_and(
            np.logical_and(mask_region > 0, visited_region == 0),
            same_component
        )

        if not unvisited_wire.any():
            # Permitir re-visitar pero SOLO del mismo componente
            wire_pixels = np.logical_and(mask_region > 0, same_component)
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
        """Score balanceado entre momentum y exploración."""
        current_arr = np.array(current)
        momentum = self._get_momentum()
        coverage = self._compute_pixel_coverage()
        skeleton_coverage = self._skeleton_coverage_cache  # Usar cache

        scored = []

        for option in options:
            opt_arr = np.array(option)
            direction = opt_arr - current_arr
            dist = np.linalg.norm(direction)

            if dist < 1e-6:
                continue

            direction = direction / dist

            # SCORE 1: Momentum (dinámico: 40-60% según cobertura)
            if np.linalg.norm(momentum) > 0:
                alignment = np.dot(direction, momentum)
                momentum_score = max(0, alignment) ** 3
            else:
                momentum_score = 0.5

            # SCORE 2: Exploración (dinámico: 30-50% según cobertura)
            exploration_score = self._exploration_score(option)

            # SCORE 3: Skeleton proximity (bonus si opción está cerca de skeleton sin cubrir)
            skeleton_bonus = self._skeleton_proximity_score(option)

            # SCORE 4: Acercamiento al END (5-10%, solo si coverage > 90%)
            if skeleton_coverage > 0.90:
                dist_to_end_before = np.linalg.norm(current_arr - np.array(self.end))
                dist_to_end_after = np.linalg.norm(opt_arr - np.array(self.end))
                end_score = 1.0 if dist_to_end_after < dist_to_end_before else 0.2
            else:
                end_score = 0.5

            # Ajustar pesos según cobertura actual
            if skeleton_coverage < 0.50:
                # Baja cobertura: EXPLORAR AL MÁXIMO
                w_momentum = 0.20
                w_exploration = 0.50
                w_skeleton = 0.25
                w_end = 0.05
            elif skeleton_coverage < 0.70:
                # Media-baja cobertura: más exploración
                w_momentum = 0.25
                w_exploration = 0.50
                w_skeleton = 0.20
                w_end = 0.05
            elif skeleton_coverage < 0.85:
                # Media-alta cobertura: balancear
                w_momentum = 0.35
                w_exploration = 0.40
                w_skeleton = 0.20
                w_end = 0.05
            else:
                # Alta cobertura (>85%): priorizar llegar al END
                w_momentum = 0.45
                w_exploration = 0.30
                w_skeleton = 0.10
                w_end = 0.15

            total = (momentum_score * w_momentum +
                    exploration_score * w_exploration +
                    skeleton_bonus * w_skeleton +
                    end_score * w_end)

            scored.append((option, total))

        scored.sort(key=lambda x: x[1], reverse=True)
        return scored

    def _exploration_score(self, pos: Tuple[int, int]) -> float:
        """Score de exploración."""
        x, y = pos
        radius = 12

        y_min = max(0, y - radius)
        y_max = min(self.mask.shape[0], y + radius + 1)
        x_min = max(0, x - radius)
        x_max = min(self.mask.shape[1], x + radius + 1)

        mask_region = self.mask[y_min:y_max, x_min:x_max]
        visited_region = self.visited_map[y_min:y_max, x_min:x_max]

        unvisited = np.logical_and(mask_region > 0, visited_region == 0)
        total_wire = np.sum(mask_region > 0)

        if total_wire == 0:
            return 0.0

        return np.sum(unvisited) / total_wire

    def _skeleton_proximity_score(self, pos: Tuple[int, int]) -> float:
        """Score basado en proximidad a skeleton sin cubrir."""
        x, y = pos
        radius = 15

        y_min = max(0, y - radius)
        y_max = min(self.skeleton.shape[0], y + radius + 1)
        x_min = max(0, x - radius)
        x_max = min(self.skeleton.shape[1], x + radius + 1)

        skeleton_region = self.skeleton[y_min:y_max, x_min:x_max]
        visited_region = self.visited_map[y_min:y_max, x_min:x_max]

        # Dilatar visited para ver qué skeleton está cubierto
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE,
                                          (self.coverage_radius * 2, self.coverage_radius * 2))
        visited_dilated = cv2.dilate(visited_region, kernel, iterations=1)

        # Skeleton sin cubrir
        skeleton_uncovered = np.logical_and(skeleton_region > 0, visited_dilated == 0)
        total_skeleton = np.sum(skeleton_region > 0)

        if total_skeleton == 0:
            return 0.0

        # Mayor score si hay mucho skeleton sin cubrir cerca
        return np.sum(skeleton_uncovered) / total_skeleton

    def _get_momentum(self) -> np.ndarray:
        """Calcula momentum."""
        if len(self.path) < 2:
            return np.array([0.0, 0.0])

        window = min(20, len(self.path))
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
                weights.append(i ** 2)

        if not directions:
            return np.array([0.0, 0.0])

        directions = np.array(directions)
        weights = np.array(weights)
        weights = weights / weights.sum()

        momentum = np.sum(directions * weights[:, np.newaxis], axis=0)
        norm = np.linalg.norm(momentum)

        return momentum / norm if norm > 0 else np.array([0.0, 0.0])

    def _save_checkpoint(self, current: Tuple[int, int],
                        options: List[Tuple[int, int]],
                        iteration: int):
        """Guarda checkpoint."""
        checkpoint = Checkpoint(
            path=copy.deepcopy(self.path),
            visited_map=self.visited_map.copy(),
            current_pos=current,
            iteration=iteration,
            options=options.copy(),
            tried_options=set()
        )

        self.checkpoints.append(checkpoint)

        # Limitar stack
        if len(self.checkpoints) > 50:
            self.checkpoints.pop(0)

    def _backtrack(self) -> bool:
        """
        Hace backtrack REAL: regresa a checkpoint y prueba otra opción.

        Returns:
            True si hay otra opción para probar, False si no
        """
        while self.checkpoints:
            checkpoint = self.checkpoints[-1]

            # Encontrar opciones no probadas
            untried = [opt for opt in checkpoint.options
                      if opt not in checkpoint.tried_options]

            if untried:
                # Hay otra opción, restaurar y probarla
                print(f"   [>>] Backtrack a iter {checkpoint.iteration}, "
                      f"probando opcion {len(checkpoint.tried_options) + 1}/{len(checkpoint.options)}")

                self.path = copy.deepcopy(checkpoint.path)
                self.visited_map = checkpoint.visited_map.copy()

                # Marcar la primera opción original como probada
                if len(checkpoint.tried_options) == 0 and len(checkpoint.options) > 0:
                    checkpoint.tried_options.add(checkpoint.options[0])

                return True
            else:
                # Sin opciones, eliminar checkpoint y seguir
                self.checkpoints.pop()

        return False

    def _validate_skeleton_coverage(self) -> float:
        """Valida cobertura del skeleton."""
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE,
                                          (self.coverage_radius * 2, self.coverage_radius * 2))
        visited_dilated = cv2.dilate(self.visited_map, kernel, iterations=1)

        skeleton_covered = np.logical_and(self.skeleton > 0, visited_dilated > 0)
        covered_px = np.sum(skeleton_covered)

        coverage = covered_px / self.total_skeleton_pixels if self.total_skeleton_pixels > 0 else 0.0

        print(f"   Skeleton: {covered_px}/{self.total_skeleton_pixels} px cubiertos ({coverage*100:.1f}%)")

        return coverage

    def _compute_pixel_coverage(self) -> float:
        """Cobertura de píxeles (para scoring)."""
        total = np.sum(self.mask > 0)
        if total == 0:
            return 0.0
        covered = np.logical_and(self.mask > 0, self.visited_map > 0)
        return np.sum(covered) / total

    def _build_success_result(self, coverage: float) -> Dict:
        """Construye resultado exitoso."""
        return {
            'success': True,
            'path': self.path,
            'skeleton_coverage': coverage,
            'num_points': len(self.path)
        }

    def _build_failure_result(self, coverage: float) -> Dict:
        """Construye resultado fallido."""
        return {
            'success': False,
            'path': self.path,
            'skeleton_coverage': coverage,
            'num_points': len(self.path),
            'error': 'Could not find valid path'
        }

    def visualize(self, output_path: str):
        """Visualiza resultado."""
        vis = cv2.cvtColor(self.mask, cv2.COLOR_GRAY2BGR)

        # Skeleton sin cubrir en ROJO
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE,
                                          (self.coverage_radius * 2, self.coverage_radius * 2))
        visited_dilated = cv2.dilate(self.visited_map, kernel, iterations=1)
        skeleton_uncovered = np.logical_and(self.skeleton > 0, visited_dilated == 0)
        vis[skeleton_uncovered] = (0, 0, 255)

        # Path
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

        # START y END
        cv2.circle(vis, self.start, 15, (0, 255, 0), -1)
        cv2.circle(vis, self.end, 15, (0, 255, 255), -1)

        coverage = self._validate_skeleton_coverage()

        plt.figure(figsize=(16, 14))
        plt.imshow(cv2.cvtColor(vis, cv2.COLOR_BGR2RGB))

        status = "VALIDO" if coverage >= 0.95 else "INVALIDO"
        color_status = "green" if coverage >= 0.95 else "red"

        plt.title(f"Backtracking Wire Path - {len(self.path)} pts | "
                 f"Skeleton: {coverage*100:.1f}% | "
                 f"Status: {status}",
                 fontsize=14, weight='bold', color=color_status)
        plt.axis('off')
        plt.tight_layout()
        plt.savefig(output_path, dpi=150, bbox_inches='tight')
        print(f"\n[OK] Visualizacion guardada: {output_path}")
        plt.show()


def main():
    """Test del planner con backtracking."""
    mask_path = r"c:\Users\jf19s\Desktop\PROYECTOS\ACTUALES\STEREO_PHOTOGRAMMETRY_CM5\data\results\debug\cable_mask_left.png"

    mask = cv2.imread(mask_path, cv2.IMREAD_GRAYSCALE)
    _, mask = cv2.threshold(mask, 127, 255, cv2.THRESH_BINARY)

    start = (1248, 668)
    end = (1297, 945)

    planner = BacktrackingWirePlanner(mask, start, end)
    result = planner.plan_path(max_iterations=20000)

    print(f"\n[5/6] Resultado: {'EXITO' if result['success'] else 'FALLO'}")
    print(f"      Path: {result['num_points']} puntos")
    print(f"      Skeleton coverage: {result['skeleton_coverage']*100:.1f}%")

    print("\n[6/6] Generando visualizacion...")
    planner.visualize('data/results/debug/backtracking_wire_path.png')

    return result


if __name__ == "__main__":
    main()
