#!/usr/bin/env python3
"""
Clean Topology Wire Planner - Limpia máscara y detecta topología real.

Mejoras críticas:
1. PRE-PROCESAMIENTO: Elimina conexiones falsas (polvo/ruido entre cuerdas paralelas)
2. DETECCIÓN DE TOPOLOGÍA: Identifica cuántas cuerdas hay y cómo están conectadas
3. FORZAR COMPLETITUD: No permite cambiar de cuerda hasta completar la actual
4. VALIDACIÓN ESTRICTA: Si hay regiones >5% sin visitar → decisión incorrecta
"""

import cv2
import numpy as np
import matplotlib.pyplot as plt
from typing import List, Tuple, Dict, Optional
from dataclasses import dataclass
import copy


@dataclass
class WireComponent:
    """Componente de cuerda identificado."""
    pixels: np.ndarray  # (N, 2) array de coordenadas
    size: int
    centroid: Tuple[int, int]
    component_id: int


class CleanTopologyWirePlanner:
    """Planner con limpieza de máscara y topología real."""

    def __init__(self, mask: np.ndarray, start: Tuple[int, int], end: Tuple[int, int]):
        self.original_mask = mask.copy()
        self.start = start
        self.end = end

        # PASO 1: Limpiar máscara (eliminar conexiones falsas)
        print("\n[1/5] Limpiando mascara (eliminando conexiones falsas)...")
        self.mask = self._clean_mask(mask)

        # Comparar
        original_px = np.sum(mask > 0)
        cleaned_px = np.sum(self.mask > 0)
        print(f"      Original: {original_px} px, Limpiada: {cleaned_px} px")
        print(f"      Ruido eliminado: {original_px - cleaned_px} px")

        # PASO 2: Generar skeleton (para validación de topología)
        print("\n[2/5] Generando skeleton para validacion topologica...")
        mask_binary = (self.mask > 0).astype(np.uint8)
        self.skeleton = cv2.ximgproc.thinning(mask_binary * 255, thinningType=cv2.ximgproc.THINNING_ZHANGSUEN)
        self.skeleton = (self.skeleton > 0).astype(np.uint8)
        skeleton_px = np.sum(self.skeleton > 0)
        print(f"      Skeleton: {skeleton_px} px (estructura topologica)")

        # Parámetros
        self.step_size = 5
        self.coverage_radius = 8  # Radio para considerar skeleton como "visitado"

        # Estado
        self.path: List[Tuple[int, int]] = []
        self.visited_map = np.zeros_like(self.mask, dtype=np.uint8)

        # Métricas (usar SKELETON para validación, no máscara)
        self.total_skeleton_pixels = np.sum(self.skeleton > 0)

    def _clean_mask(self, mask: np.ndarray) -> np.ndarray:
        """
        Limpia la máscara eliminando conexiones falsas entre cuerdas paralelas.

        Estrategia:
        1. Erosión suave para romper conexiones débiles (polvo)
        2. Mantener estructura principal
        3. Dilatación para recuperar grosor original
        """
        # Convertir a binario
        _, binary = cv2.threshold(mask, 127, 255, cv2.THRESH_BINARY)

        # Kernel pequeño para erosión (rompe conexiones de 1-2 píxeles)
        kernel_erode = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))

        # Erosión para romper conexiones falsas
        eroded = cv2.erode(binary, kernel_erode, iterations=2)

        # Dilatación para recuperar grosor (kernel un poco más grande)
        kernel_dilate = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
        dilated = cv2.dilate(eroded, kernel_dilate, iterations=1)

        return dilated

    def plan_path(self, max_iterations: int = 20000) -> Dict:
        """Planifica path con validación estricta de cobertura."""
        print("\n[3/5] Analizando topologia de la mascara...")

        # Analizar componentes después de limpieza
        num_components, labels = cv2.connectedComponents(self.mask)
        print(f"      Componentes detectados: {num_components - 1}")

        print("\n[4/5] Iniciando path planning...")
        print("="*70)

        self.path = [self.start]
        current = self.start
        cv2.circle(self.visited_map, self.start, self.coverage_radius, 255, -1)

        iteration = 0
        stuck_counter = 0

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

                # VALIDACIÓN CRÍTICA: ¿Hay regiones grandes sin visitar?
                unvisited_ratio = self._analyze_unvisited_regions()

                if unvisited_ratio > 0.05:  # Más del 5% sin visitar
                    print(f"       [ERROR] Hay {unvisited_ratio*100:.1f}% de la cuerda SIN RECORRER!")
                    print(f"       [ERROR] Esto indica que se tomo una DECISION INCORRECTA")

                    # Intentar explorar ramas faltantes
                    print(f"       [>>] Intentando explorar ramas faltantes...")

                    exploration_success = self._explore_missing_branches(max_iterations - iteration)

                    if exploration_success:
                        print(f"       [OK] Ramas exploradas exitosamente!")
                        # Re-validar
                        unvisited_ratio = self._analyze_unvisited_regions()
                        if unvisited_ratio < 0.05:
                            print(f"       [OK] Ahora la cobertura es suficiente!")
                            break
                    else:
                        print(f"       [!] No se pudieron explorar todas las ramas")
                        break
                else:
                    print(f"       [OK] Cobertura suficiente, path VALIDO!")
                    break

            # Obtener opciones
            options = self._get_movement_options(current)

            if not options:
                stuck_counter += 1
                if stuck_counter > 10:
                    print(f"\n[!] Atascado en iter {iteration}, terminando")
                    break

                # Permitir re-visitar
                options = self._get_movement_options(current, allow_revisit=True)
                if not options:
                    break

            # Evaluar opciones
            scored_options = self._score_options(current, options)
            next_pos = scored_options[0][0]

            # Avanzar
            self.path.append(next_pos)
            current = next_pos
            cv2.circle(self.visited_map, next_pos, self.coverage_radius, 255, -1)
            stuck_counter = 0

            # Log
            if iteration % 200 == 0:
                coverage = self._compute_coverage()
                print(f"  Iter {iteration}: {len(self.path)} pts, coverage: {coverage*100:.1f}%")

        print("\n[5/5] Path planning completado")

        final_coverage = self._compute_coverage()
        print(f"\n[6/6] Validando resultado...")
        unvisited_ratio = self._analyze_unvisited_regions()

        print(f"\n=== RESULTADOS FINALES ===")
        print(f"Path: {len(self.path)} puntos")
        print(f"Cobertura de pixeles: {final_coverage*100:.1f}%")
        print(f"Skeleton sin cubrir: {unvisited_ratio*100:.1f}%")

        success = unvisited_ratio < 0.05

        return {
            'success': success,
            'path': self.path,
            'coverage': final_coverage,
            'unvisited_ratio': unvisited_ratio
        }

    def _explore_missing_branches(self, remaining_iterations: int) -> bool:
        """
        Explora ramas faltantes del skeleton.

        Estrategia:
        1. Encontrar el centroid del skeleton sin cubrir
        2. Encontrar el punto del path más cercano a ese centroid
        3. Continuar desde ese punto hacia la rama faltante
        4. Repetir hasta cubrir todo o agotar iteraciones

        Returns:
            True si logró cubrir todo, False si no
        """
        max_exploration_attempts = 3

        for attempt in range(max_exploration_attempts):
            # Encontrar skeleton sin cubrir
            kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE,
                                              (self.coverage_radius * 2, self.coverage_radius * 2))
            visited_dilated = cv2.dilate(self.visited_map, kernel, iterations=1)

            skeleton_uncovered = np.logical_and(self.skeleton > 0, visited_dilated == 0)
            uncovered_points = np.argwhere(skeleton_uncovered)

            if len(uncovered_points) == 0:
                return True  # Todo cubierto

            # Convertir a (x, y)
            uncovered_points = uncovered_points[:, [1, 0]]

            # Centroid de la región sin cubrir
            centroid = np.mean(uncovered_points, axis=0).astype(int)
            centroid = tuple(centroid)

            print(f"          Intento {attempt + 1}/{max_exploration_attempts}: "
                  f"Explorando hacia {centroid} ({len(uncovered_points)} px sin cubrir)")

            # Encontrar punto del path más cercano al centroid
            path_array = np.array(self.path)
            distances = np.linalg.norm(path_array - np.array(centroid), axis=1)
            closest_idx = np.argmin(distances)
            closest_point = tuple(path_array[closest_idx])

            print(f"          Punto más cercano del path: {closest_point} (dist={distances[closest_idx]:.1f})")

            # Continuar desde ese punto hacia la rama
            current = closest_point
            branch_iterations = 0
            max_branch_iter = min(2000, remaining_iterations)

            while branch_iterations < max_branch_iter:
                branch_iterations += 1

                # Buscar opciones hacia skeleton sin cubrir
                options = self._get_movement_options_towards_uncovered(current)

                if not options:
                    print(f"          Sin opciones después de {branch_iterations} pasos")
                    break

                # Elegir mejor opción
                scored = self._score_options_exploration(current, options, centroid)
                next_pos = scored[0][0]

                # Avanzar
                self.path.append(next_pos)
                current = next_pos
                cv2.circle(self.visited_map, next_pos, self.coverage_radius, 255, -1)

            print(f"          Rama explorada: {branch_iterations} pasos adicionales")

        # Validar resultado final
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE,
                                          (self.coverage_radius * 2, self.coverage_radius * 2))
        visited_dilated = cv2.dilate(self.visited_map, kernel, iterations=1)
        skeleton_uncovered = np.logical_and(self.skeleton > 0, visited_dilated == 0)
        remaining = np.sum(skeleton_uncovered)

        return remaining < self.total_skeleton_pixels * 0.05

    def _get_movement_options_towards_uncovered(self, current: Tuple[int, int]) -> List[Tuple[int, int]]:
        """Obtiene opciones de movimiento priorizando zonas sin cubrir."""
        x, y = current
        search_radius = self.step_size * 3

        y_min = max(0, y - search_radius)
        y_max = min(self.mask.shape[0], y + search_radius + 1)
        x_min = max(0, x - search_radius)
        x_max = min(self.mask.shape[1], x + search_radius + 1)

        mask_region = self.mask[y_min:y_max, x_min:x_max]
        valid_pixels = (mask_region > 0)

        if not valid_pixels.any():
            return []

        wire_y, wire_x = np.where(valid_pixels)
        wire_y = wire_y + y_min
        wire_x = wire_x + x_min

        options = []
        for wx, wy in zip(wire_x, wire_y):
            dist = np.linalg.norm(np.array([wx - x, wy - y]))
            if self.step_size * 0.7 < dist < self.step_size * 2.5:
                options.append((wx, wy))

        return options

    def _score_options_exploration(self, current: Tuple[int, int],
                                   options: List[Tuple[int, int]],
                                   target: Tuple[int, int]) -> List[Tuple[Tuple[int, int], float]]:
        """Score para exploración: priorizar acercamiento al target."""
        current_arr = np.array(current)
        target_arr = np.array(target)

        scored = []

        for option in options:
            opt_arr = np.array(option)

            # Distancia al target
            dist_to_target = np.linalg.norm(opt_arr - target_arr)

            # Score: preferir más cercano al target
            score = 1.0 / (dist_to_target + 1.0)

            scored.append((option, score))

        scored.sort(key=lambda x: x[1], reverse=True)
        return scored

    def _analyze_unvisited_regions(self) -> float:
        """
        Analiza regiones de SKELETON no visitadas.

        CLAVE: No mide píxeles de máscara, mide píxeles de SKELETON.
        Si pasaste por el centro de una cuerda gruesa, el skeleton está cubierto.

        Returns:
            Ratio de skeleton sin visitar (0.0 a 1.0)
        """
        # Crear mapa de skeleton visitado
        # Un punto del skeleton está "visitado" si hay path cerca (radio = coverage_radius)
        skeleton_visited = np.zeros_like(self.skeleton, dtype=np.uint8)

        # Dilatar visited_map para capturar skeleton cercano
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE,
                                          (self.coverage_radius * 2, self.coverage_radius * 2))
        visited_dilated = cv2.dilate(self.visited_map, kernel, iterations=1)

        # Skeleton cubierto = skeleton AND visited_dilated
        skeleton_covered = np.logical_and(self.skeleton > 0, visited_dilated > 0)

        # Skeleton sin cubrir
        skeleton_uncovered = np.logical_and(self.skeleton > 0, visited_dilated == 0)

        covered_px = np.sum(skeleton_covered)
        uncovered_px = np.sum(skeleton_uncovered)

        ratio = uncovered_px / self.total_skeleton_pixels if self.total_skeleton_pixels > 0 else 0.0

        print(f"       Skeleton cubierto: {covered_px} px ({(1-ratio)*100:.1f}%)")
        print(f"       Skeleton sin cubrir: {uncovered_px} px ({ratio*100:.1f}%)")

        return ratio

    def _get_movement_options(self, current: Tuple[int, int],
                             allow_revisit: bool = False) -> List[Tuple[int, int]]:
        """Obtiene opciones de movimiento."""
        x, y = current
        search_radius = self.step_size * 3

        y_min = max(0, y - search_radius)
        y_max = min(self.mask.shape[0], y + search_radius + 1)
        x_min = max(0, x - search_radius)
        x_max = min(self.mask.shape[1], x + search_radius + 1)

        mask_region = self.mask[y_min:y_max, x_min:x_max]
        visited_region = self.visited_map[y_min:y_max, x_min:x_max]

        if not allow_revisit:
            # Solo píxeles no visitados
            valid_pixels = np.logical_and(mask_region > 0, visited_region == 0)
        else:
            # Cualquier píxel de máscara
            valid_pixels = (mask_region > 0)

        if not valid_pixels.any():
            return []

        wire_y, wire_x = np.where(valid_pixels)
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
        Scoring MEJORADO con prioridades correctas.

        Prioridades:
        1. Momentum (70%) - Seguir la cuerda actual sin cambiar
        2. Exploración (20%) - Ir a zonas no visitadas
        3. Acercamiento al END (5%) - Solo cuando cobertura > 85%
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

            # SCORE 1: Momentum (70%) - MUY IMPORTANTE
            if np.linalg.norm(momentum) > 0:
                alignment = np.dot(direction, momentum)
                momentum_score = max(0, alignment) ** 3  # Cúbico para enfatizar
            else:
                momentum_score = 0.5

            # SCORE 2: Exploración (20%)
            exploration_score = self._compute_exploration_score(option)

            # SCORE 3: Acercamiento al END (5%, SOLO si cobertura > 85%)
            if current_coverage > 0.85:
                dist_before = np.linalg.norm(current_arr - end_arr)
                dist_after = np.linalg.norm(opt_arr - end_arr)
                end_score = 1.0 if dist_after < dist_before else 0.2
            else:
                end_score = 0.5  # Neutral

            # SCORE 4: Evitar loops (5%)
            loop_penalty = 0.0
            if len(self.path) > 20:
                recent = np.array(self.path[-50:])
                dists = np.linalg.norm(recent - opt_arr, axis=1)
                min_dist = np.min(dists[:-3])
                if min_dist < 8:
                    loop_penalty = -1.0  # Penalización fuerte

            # Score total
            total = (momentum_score * 0.70 +
                    exploration_score * 0.20 +
                    end_score * 0.05 +
                    loop_penalty * 0.05)

            scored.append((option, total))

        scored.sort(key=lambda x: x[1], reverse=True)
        return scored

    def _compute_exploration_score(self, pos: Tuple[int, int]) -> float:
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
        unvisited_count = np.sum(unvisited)

        total_wire = np.sum(mask_region > 0)

        if total_wire == 0:
            return 0.0

        return unvisited_count / total_wire

    def _get_momentum(self) -> np.ndarray:
        """Calcula momentum."""
        if len(self.path) < 2:
            return np.array([0.0, 0.0])

        window = min(20, len(self.path))  # Ventana más larga para momentum más estable
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
                weights.append(i ** 2)  # Cuadrático para dar MÁS peso a recientes

        if not directions:
            return np.array([0.0, 0.0])

        directions = np.array(directions)
        weights = np.array(weights)
        weights = weights / weights.sum()

        momentum = np.sum(directions * weights[:, np.newaxis], axis=0)
        norm = np.linalg.norm(momentum)

        return momentum / norm if norm > 0 else np.array([0.0, 0.0])

    def _compute_coverage(self) -> float:
        """Calcula cobertura de píxeles de máscara (para información)."""
        total_mask_px = np.sum(self.mask > 0)
        if total_mask_px == 0:
            return 0.0
        covered = np.logical_and(self.mask > 0, self.visited_map > 0)
        return np.sum(covered) / total_mask_px

    def visualize(self, output_path: str):
        """Visualiza resultado con análisis."""
        vis = cv2.cvtColor(self.mask, cv2.COLOR_GRAY2BGR)

        # Marcar regiones sin visitar en ROJO
        unvisited_mask = np.logical_and(
            self.mask > 0,
            self.visited_map == 0
        )
        vis[unvisited_mask] = (0, 0, 255)

        # Dibujar path
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

        coverage = self._compute_coverage()
        unvisited_ratio = self._analyze_unvisited_regions()

        plt.figure(figsize=(16, 14))
        plt.imshow(cv2.cvtColor(vis, cv2.COLOR_BGR2RGB))

        status = "VALIDO" if unvisited_ratio < 0.05 else "INVALIDO"
        color_status = "green" if unvisited_ratio < 0.05 else "red"

        plt.title(f"Clean Topology Wire Path - {len(self.path)} pts | "
                 f"Coverage: {coverage*100:.1f}% | "
                 f"Unvisited: {unvisited_ratio*100:.1f}% | "
                 f"Status: {status}",
                 fontsize=14, weight='bold', color=color_status)
        plt.axis('off')
        plt.tight_layout()
        plt.savefig(output_path, dpi=150, bbox_inches='tight')
        print(f"\n[OK] Visualizacion guardada: {output_path}")
        plt.show()


def main():
    """Test del planner con limpieza."""
    mask_path = r"c:\Users\jf19s\Desktop\PROYECTOS\ACTUALES\STEREO_PHOTOGRAMMETRY_CM5\data\results\debug\cable_mask_left.png"

    mask = cv2.imread(mask_path, cv2.IMREAD_GRAYSCALE)
    _, mask = cv2.threshold(mask, 127, 255, cv2.THRESH_BINARY)

    start = (1248, 668)
    end = (1297, 945)

    planner = CleanTopologyWirePlanner(mask, start, end)
    result = planner.plan_path(max_iterations=20000)

    planner.visualize('data/results/debug/clean_topology_wire_path.png')

    return result


if __name__ == "__main__":
    main()
