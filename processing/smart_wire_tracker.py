#!/usr/bin/env python3
"""
Smart Wire Tracker - Path planning inteligente SIN skeleton.

Estrategia:
- Trabaja directamente sobre la máscara (no skeleton)
- Sigue el flujo del centro de masa local de la cuerda
- Detecta bifurcaciones/cruces analizando cambios en la topología local
- Backtracking cuando detecta decisión incorrecta (cobertura baja)
"""

import cv2
import numpy as np
import matplotlib.pyplot as plt
from typing import List, Tuple, Dict, Optional
from dataclasses import dataclass
from collections import deque


@dataclass
class DecisionPoint:
    """Punto donde se tomó una decisión de path."""
    location: Tuple[int, int]
    alternatives: List[Tuple[int, int]]
    chosen_index: int


class SmartWireTracker:
    """Tracker inteligente con Backtracking (DFS) y verificación de conectividad."""

    def __init__(self, mask: np.ndarray, start: Tuple[int, int], end: Tuple[int, int]):
        self.mask = mask
        self.start = start
        self.end = end

        # Estado del tracking
        self.path: List[Tuple[int, int]] = []
        # Mapa de visitados (será nuestra "memoria" visual)
        self.visited_map = np.zeros_like(mask, dtype=np.uint8)
        self.decision_points: List[DecisionPoint] = []

        # --- CALCULAR DISTANCE TRANSFORM para ancho adaptativo ---
        print("Calculando Distance Transform para ancho adaptativo...")
        self.distance_transform = cv2.distanceTransform(mask, cv2.DIST_L2, 5)

        # --- PARÁMETROS AJUSTADOS ---
        self.step_size = 5         # Pasos un poco más largos para no atascarse en ruido
        self.search_radius = 20    # Buscar un poco más lejos
        self.wire_radius = 9       # Estimación del grosor (para otros cálculos)
        self.min_coverage_radius = 8   # Radio mínimo para zonas delgadas
        self.max_coverage_radius = 30  # Radio máximo para zonas anchas

        # Estadísticas
        self.total_mask_pixels = np.sum(mask > 0)

    def track_wire(self, max_iterations: int = 5000, step_callback=None) -> Dict:
        print("\n" + "="*70)
        print("SMART WIRE TRACKER (CON BACKTRACKING)")
        print("="*70)

        self.path = [self.start]
        current = self.start
        self._mark_visited(current)

        iteration = 0
        while iteration < max_iterations:
            iteration += 1
            
            # 1. Verificar si llegamos al END
            dist_to_end = np.linalg.norm(np.array(current) - np.array(self.end))
            if dist_to_end < self.step_size * 3:
                self.path.append(self.end)
                print(f"\n[OK] LLEGADA EXITOSA al END en iteración {iteration}")
                break

            # 2. Calcular opciones
            candidates = self._find_candidates(current)

            # 3. Filtrar candidatos: preferir no-visitados, pero permitir
            #    cruzar una zona visitada si la trayectoria es recta (crossing exception)
            momentum = self._get_momentum_direction()
            valid_candidates = []
            visited_crossing_candidates = []

            for c in candidates:
                if self.visited_map[c[1], c[0]] == 0:
                    valid_candidates.append(c)
                else:
                    # Candidato visitado: evaluar si es un cruce legítimo
                    # Solo permitir si hay momentum claro y la dirección está alineada
                    if np.linalg.norm(momentum) > 0.1:
                        direction = np.array(c, dtype=np.float64) - np.array(current, dtype=np.float64)
                        norm = np.linalg.norm(direction)
                        if norm > 0:
                            direction /= norm
                            dot = np.dot(direction, momentum)
                            # Umbral alto (0.85): solo cruzar si va muy recto
                            if dot > 0.85:
                                visited_crossing_candidates.append(c)

            # Usar candidatos visitados SOLO si los no-visitados son escasos
            if len(valid_candidates) < 3 and len(visited_crossing_candidates) > 0:
                valid_candidates.extend(visited_crossing_candidates)
            
            # 4. Análisis de Flujo (Momentum y Agrupación)
            # (momentum ya calculado arriba para crossing check)
            end_direction = self._get_direction_to_end(current)
            
            flow_options = self._analyze_flow_options(
                current, np.array(valid_candidates), momentum, end_direction
            )

            next_step = None

            # CASO A: Camino único o mejor opción clara
            if len(flow_options) == 1:
                next_step = flow_options[0]
            
            # CASO B: Bifurcación (Cruce o Paralelas)
            elif len(flow_options) > 1:
                # Crear punto de decisión
                # Ordenamos las opciones por "calidad" para probar la mejor primero
                sorted_options = self._sort_options(current, flow_options, momentum)
                
                # Elegimos la primera, guardamos las demás
                next_step = sorted_options[0]
                alternatives = sorted_options[1:]
                
                # Guardamos el índice actual del path para saber dónde volver
                dp = DecisionPoint(
                    location=current,
                    alternatives=alternatives, # Las que quedan pendientes
                    chosen_index=len(self.path) # Indice en el path donde ocurrió
                )
                self.decision_points.append(dp)
                print(f"  [+] Bifurcación en {current}. Opciones: {len(flow_options)}. Guardando checkpoint.")

            # CASO C: Sin camino (Atascado) -> BACKTRACKING
            if next_step is None:
                if self._perform_backtracking():
                    current = self.path[-1] # El path se ha rebobinado
                    print(f"  [<] Retrocediendo a {current}...")
                    continue # Siguiente iteración desde el punto restaurado
                else:
                    print(f"\n[!] ATASCADO FINAL. No quedan puntos de decisión.")
                    break

            # Avanzar
            self.path.append(next_step)
            current = next_step
            self._mark_visited(next_step)

            # Notificar progreso para visualizacion en tiempo real
            if step_callback and iteration % 5 == 0:
                step_callback(list(self.path), iteration)

            if iteration % 200 == 0:
                print(f"  Iter {iteration}: Path len {len(self.path)}")

        # Métricas finales
        final_coverage = self._compute_coverage()
        print(f"\n[FIN] Path: {len(self.path)} pts | Cobertura: {final_coverage*100:.1f}%")
        
        return {
            'success': True,
            'path': self.path,
            'coverage': final_coverage
        }

    def _perform_backtracking(self) -> bool:
        """
        Retrocede al último punto de decisión con opciones disponibles.
        Devuelve True si logró retroceder, False si no hay más opciones.
        """
        while self.decision_points:
            last_dp = self.decision_points[-1]
            
            if not last_dp.alternatives:
                # Si este punto ya no tiene opciones, lo descartamos y seguimos buscando atrás
                self.decision_points.pop()
                continue
            
            # Tenemos un punto con opciones!
            
            # 1. Identificar el segmento "malo" (desde el DP hasta el final actual)
            # El path index guardado es donde estaba el current cuando se creó el DP
            cut_index = last_dp.chosen_index + 1 
            bad_segment = self.path[cut_index:]
            
            # 2. "Des-visitar" el segmento malo en el mapa
            # Esto permite que otros caminos crucen por aquí si es necesario,
            # o simplemente limpia el mapa.
            for p in bad_segment:
                self._unmark_visited(p)
            
            # 3. Cortar el path
            self.path = self.path[:cut_index]
            
            # 4. Tomar la siguiente alternativa disponible
            next_option = last_dp.alternatives.pop(0) # Sacamos la siguiente opción
            
            # 5. Agregar la nueva opción al path y marcarla
            self.path.append(next_option)
            self._mark_visited(next_option)
            
            return True # Backtracking exitoso
            
        return False # No hay dónde volver

    def _mark_visited(self, point: Tuple[int, int]):
        """
        Marca el área alrededor del punto como visitada.
        CLAVE: Usa Distance Transform para adaptar el radio al grosor local de la cuerda.
        """
        x, y = point

        # ESTRATEGIA HÍBRIDA:
        # 1. DT del punto actual (puede ser bajo si estamos en el borde)
        # 2. DT máximo en área pequeña (grosor real de la cuerda aquí)
        # Usamos un promedio ponderado para no ser ni muy conservador ni muy agresivo

        dt_point = self.distance_transform[y, x]

        search_size = 8
        y_min_search = max(0, y - search_size)
        y_max_search = min(self.distance_transform.shape[0], y + search_size)
        x_min_search = max(0, x - search_size)
        x_max_search = min(self.distance_transform.shape[1], x + search_size)

        roi_dt = self.distance_transform[y_min_search:y_max_search, x_min_search:x_max_search]
        dt_max_local = np.max(roi_dt)

        # Promedio ponderado: 70% del punto actual + 30% del máximo local
        # Esto da cobertura sin bloquear demasiado
        effective_distance = dt_point * 0.7 + dt_max_local * 0.3

        # Radio: 1.5x la distancia efectiva + pequeño margen
        adaptive_radius = int(effective_distance * 1.5) + 4

        # Limitar entre min y max
        adaptive_radius = max(self.min_coverage_radius, min(self.max_coverage_radius, adaptive_radius))

        # Crear una máscara circular del área a marcar
        y_min = max(0, y - adaptive_radius)
        y_max = min(self.mask.shape[0], y + adaptive_radius)
        x_min = max(0, x - adaptive_radius)
        x_max = min(self.mask.shape[1], x + adaptive_radius)

        # Extraer la región de interés
        roi_mask = self.mask[y_min:y_max, x_min:x_max]
        roi_visited = self.visited_map[y_min:y_max, x_min:x_max]

        # Crear máscara circular
        roi_h, roi_w = roi_mask.shape
        cy_local = y - y_min
        cx_local = x - x_min

        yy, xx = np.ogrid[0:roi_h, 0:roi_w]
        circle_mask = (xx - cx_local)**2 + (yy - cy_local)**2 <= adaptive_radius**2

        # Marcar como visitados SOLO los píxeles que son cuerda (blancos) Y están en el círculo
        pixels_to_mark = np.logical_and(roi_mask > 0, circle_mask)
        roi_visited[pixels_to_mark] = 255

        # Actualizar la región en el mapa global
        self.visited_map[y_min:y_max, x_min:x_max] = roi_visited

    def _unmark_visited(self, point: Tuple[int, int]):
        """Desmarca un punto visitado (para backtracking), usando radio adaptativo."""
        x, y = point

        # Usar el mismo radio adaptativo que en _mark_visited
        dt_point = self.distance_transform[y, x]

        search_size = 8
        y_min_search = max(0, y - search_size)
        y_max_search = min(self.distance_transform.shape[0], y + search_size)
        x_min_search = max(0, x - search_size)
        x_max_search = min(self.distance_transform.shape[1], x + search_size)

        roi_dt = self.distance_transform[y_min_search:y_max_search, x_min_search:x_max_search]
        dt_max_local = np.max(roi_dt)

        effective_distance = dt_point * 0.7 + dt_max_local * 0.3
        adaptive_radius = int(effective_distance * 1.5) + 4
        adaptive_radius = max(self.min_coverage_radius, min(self.max_coverage_radius, adaptive_radius))

        # Crear región
        y_min = max(0, y - adaptive_radius)
        y_max = min(self.mask.shape[0], y + adaptive_radius)
        x_min = max(0, x - adaptive_radius)
        x_max = min(self.mask.shape[1], x + adaptive_radius)

        roi_mask = self.mask[y_min:y_max, x_min:x_max]
        roi_visited = self.visited_map[y_min:y_max, x_min:x_max]

        # Máscara circular
        roi_h, roi_w = roi_mask.shape
        cy_local = y - y_min
        cx_local = x - x_min

        yy, xx = np.ogrid[0:roi_h, 0:roi_w]
        circle_mask = (xx - cx_local)**2 + (yy - cy_local)**2 <= adaptive_radius**2

        # Desmarcar píxeles de cuerda en el círculo
        pixels_to_unmark = np.logical_and(roi_mask > 0, circle_mask)
        roi_visited[pixels_to_unmark] = 0

        # Actualizar
        self.visited_map[y_min:y_max, x_min:x_max] = roi_visited

    def _find_candidates(self, current: Tuple[int, int]) -> List[Tuple[int, int]]:
        """Busca píxeles de cuerda en el radio, verificando conectividad."""
        x, y = current
        y_min = max(0, y - self.search_radius)
        y_max = min(self.mask.shape[0], y + self.search_radius + 1)
        x_min = max(0, x - self.search_radius)
        x_max = min(self.mask.shape[1], x + self.search_radius + 1)

        mask_slice = self.mask[y_min:y_max, x_min:x_max]
        if not (mask_slice > 0).any():
            return []

        # Obtener coordenadas globales
        ys, xs = np.where(mask_slice > 0)
        global_xs = xs + x_min
        global_ys = ys + y_min
        
        candidates = []
        for cx, cy in zip(global_xs, global_ys):
            dist = np.hypot(cx - x, cy - y)
            if self.step_size * 0.5 < dist < self.search_radius:
                # AQUÍ LA CLAVE: Chequeo estricto de no saltar vacío
                if self._check_connectivity(current, (cx, cy)):
                    candidates.append((cx, cy))
        return candidates

    def _check_connectivity(self, p1: Tuple[int, int], p2: Tuple[int, int]) -> bool:
        """Verifica línea de visión sin saltar huecos negros."""
        x1, y1 = p1
        x2, y2 = p2
        dist = np.hypot(x2 - x1, y2 - y1)
        if dist < 1.0: return True
        
        steps = int(dist * 2.0) # Mayor resolución
        for i in range(steps + 1):
            t = i / steps
            x = int(x1 + (x2 - x1) * t)
            y = int(y1 + (y2 - y1) * t)
            
            if not (0 <= y < self.mask.shape[0] and 0 <= x < self.mask.shape[1]):
                return False
            if self.mask[y, x] == 0:
                return False
        return True

    def _sort_options(self, current, options, momentum) -> List[Tuple[int, int]]:
        """
        Ordena las opciones usando análisis de continuidad para distinguir entre:
        - U-turns reales (cambio de dirección legítimo)
        - Líneas paralelas (evitar saltos entre líneas)
        - Intersecciones reales (cambio de trayectoria)

        VERSIÓN 3 MEJORADA: Mantiene solución de paralelas + mejora fluidez
        """
        if len(options) == 0:
            return []

        scores = []
        current_arr = np.array(current)
        end_arr = np.array(self.end)

        # Obtener el grosor del cable en el punto actual
        current_thickness = self.distance_transform[current[1], current[0]]

        for opt in options:
            opt_arr = np.array(opt)
            direction = (opt_arr - current_arr).astype(np.float32)
            norm = np.linalg.norm(direction)
            if norm > 0:
                direction /= norm

            # 1. CONTINUIDAD GEOMÉTRICA: qué tan suave es el cambio de dirección
            geometric_score = 0
            if np.linalg.norm(momentum) > 0:
                geometric_score = np.dot(direction, momentum)  # -1 (reversa) a +1 (recto)

            # 2. CONTINUIDAD DE GROSOR: qué tan similar es el grosor
            opt_thickness = self.distance_transform[opt[1], opt[0]]
            thickness_diff = abs(current_thickness - opt_thickness)
            # Normalizar: diferencia pequeña = score alto
            thickness_score = np.exp(-thickness_diff / 5.0)  # 0 a 1

            # 3. CONTINUIDAD DE LÍNEA (penalización lateral moderada para paralelas)
            parallel_groups = self._detect_parallel_lines(current, options, momentum)
            lateral_penalty = 0
            if len(parallel_groups) > 1:
                lateral_dist = self._get_lateral_distance(current, opt, momentum)
                # Penalización suave basada en distancia lateral
                if lateral_dist > self.wire_radius * 1.1:
                    lateral_penalty = -800  # Penalización suave

            # 4. BONUS POR ESTAR EN EL CENTRO (Distance Transform alto = centro del cable)
            # Esto ayuda a que el path se quede en el centro y no se vaya al borde
            centeredness_score = opt_thickness / max(self.wire_radius, 1.0)  # 0 a ~1+

            # 5. DIRECCIÓN AL DESTINO (menor peso que antes)
            dist_to_end = -np.linalg.norm(opt_arr - end_arr)

            # 6. COMBINACIÓN DE SCORES
            total_score = (
                geometric_score * 1200 +      # Continuidad geométrica
                thickness_score * 600 +       # Continuidad de grosor
                centeredness_score * 300 +    # ALTA PRIORIDAD: Preferencia por el centro del cable
                dist_to_end * 0.5 +           # Progreso hacia el final
                lateral_penalty               # Penalización suave por salto lateral (paralelas)
            )

            scores.append((total_score, opt))

        # Ordenar descendente (mayor score primero)
        scores.sort(key=lambda x: x[0], reverse=True)
        return [x[1] for x in scores]

    def _detect_parallel_lines(self, current, options, momentum) -> List[List[Tuple[int, int]]]:
        """
        Detecta si las opciones se agrupan en múltiples líneas paralelas.
        Retorna grupos de opciones que están en la misma línea.
        """
        if len(options) < 2 or np.linalg.norm(momentum) < 0.1:
            return [options]  # No hay suficiente info para detectar paralelas

        # Calcular vector perpendicular al momentum (dirección lateral)
        perp = np.array([-momentum[1], momentum[0]])
        perp_norm = np.linalg.norm(perp)
        if perp_norm > 0:
            perp /= perp_norm

        # Proyectar cada opción en la dirección perpendicular
        projections = []
        for opt in options:
            opt_vec = np.array(opt) - np.array(current)
            lateral_proj = np.dot(opt_vec, perp)
            # También calcular proyección en dirección del momentum (para ver si va adelante)
            forward_proj = np.dot(opt_vec, momentum / np.linalg.norm(momentum))
            projections.append((lateral_proj, forward_proj, opt))

        # Agrupar por distancia lateral (opciones con proyección similar están en la misma línea)
        projections.sort(key=lambda x: x[0])

        groups = []
        current_group = [projections[0][2]]

        # Debug info - comentado para versión final
        # if len(options) == 2:
        #     print(f"    [DEBUG] Detectando paralelas en path_len={len(self.path)}, pos={current}:")
        #     for lat, fwd, opt in projections:
        #         print(f"      opt {opt}: lateral={lat:.1f}px, forward={fwd:.1f}px")

        for i in range(1, len(projections)):
            lateral_diff = abs(projections[i][0] - projections[i-1][0])

            # Umbral más estricto para agrupar: si están separados >0.8 diámetros, son líneas diferentes
            if lateral_diff < self.wire_radius * 0.8:
                current_group.append(projections[i][2])
            else:
                # Nueva línea paralela
                groups.append(current_group)
                current_group = [projections[i][2]]

        groups.append(current_group)

        # Debug - comentado para versión final
        # if len(options) == 2:
        #     print(f"    [DEBUG] Encontrados {len(groups)} grupos paralelos: {[len(g) for g in groups]}")

        return groups

    def _get_lateral_distance(self, current, option, momentum) -> float:
        """
        Calcula la distancia lateral de una opción respecto a la dirección del momentum.
        Esto nos dice qué tan lejos está la opción "al lado" de la trayectoria actual.
        """
        if np.linalg.norm(momentum) < 0.1:
            return 0.0

        # Vector perpendicular al momentum
        perp = np.array([-momentum[1], momentum[0]])
        perp_norm = np.linalg.norm(perp)
        if perp_norm > 0:
            perp /= perp_norm

        # Vector hacia la opción
        opt_vec = np.array(option) - np.array(current)

        # Proyección en dirección perpendicular = distancia lateral
        lateral_distance = abs(np.dot(opt_vec, perp))

        return lateral_distance

    # --- MÉTODOS DE APOYO (Traer los que ya tenías o usar estos simplificados) ---
    
    def _get_momentum_direction(self) -> np.ndarray:
        if len(self.path) < 5: return np.array([0., 0.])
        pts = np.array(self.path[-5:])
        vec = pts[-1] - pts[0]
        norm = np.linalg.norm(vec)
        return vec / norm if norm > 0 else np.array([0., 0.])

    def _get_direction_to_end(self, current):
        vec = np.array(self.end) - np.array(current)
        norm = np.linalg.norm(vec)
        return vec / norm if norm > 0 else np.array([0., 0.])

    def _analyze_flow_options(self, current, candidates, momentum, end_dir) -> List[Tuple[int, int]]:
        if len(candidates) == 0: return []
        
        centers = []
        visited_cand = [False] * len(candidates)
        
        for i in range(len(candidates)):
            if visited_cand[i]: continue
            
            group = [candidates[i]]
            visited_cand[i] = True
            
            for j in range(i+1, len(candidates)):
                if visited_cand[j]: continue
                dist = np.linalg.norm(candidates[i] - candidates[j])
                
                # UMBRAL DINÁMICO: Si están más cerca que el diámetro del cable, son el mismo grupo
                if dist < self.wire_radius * 2.0: 
                    group.append(candidates[j])
                    visited_cand[j] = True
            
            # Calcular centro del grupo
            group = np.array(group)
            center = tuple(np.mean(group, axis=0).astype(int))
            centers.append(center)
            
        return centers

    def _compute_coverage(self) -> float:
        covered = np.logical_and(self.mask > 0, self.visited_map > 0)
        return np.sum(covered) / self.total_mask_pixels

    def visualize(self, output_path: str):
        # 1. Crear imagen base (Máscara original en gris suave)
        base = cv2.cvtColor(self.mask, cv2.COLOR_GRAY2BGR)
        base[np.where((base==[255,255,255]).all(axis=2))] = [100, 100, 100] # Gris oscuro
        
        # 2. Superponer lo VISITADO en ROJO (semitransparente)
        overlay = base.copy()
        # Donde visited_map es blanco, pintamos de rojo en el overlay
        overlay[self.visited_map > 0] = [0, 0, 255] 
        
        # Mezclar para ver transparencia
        cv2.addWeighted(overlay, 0.6, base, 0.4, 0, base)
        
        # 3. Dibujar PATH en CIAN brillante
        if len(self.path) > 1:
            pts = np.array(self.path, np.int32)
            pts = pts.reshape((-1, 1, 2))
            cv2.polylines(base, [pts], False, (255, 255, 0), 2)
        
        # 4. Dibujar puntos de decisión y Start/End
        for dp in self.decision_points:
            cv2.circle(base, dp.location, 6, (0, 255, 255), -1) # Amarillo para decisiones

        cv2.circle(base, self.start, 8, (0, 255, 0), -1) # Verde Start
        cv2.circle(base, self.end, 8, (0, 0, 255), -1)   # Rojo End
        
        # Usar backend no interactivo para evitar bloqueos desde threads
        import matplotlib
        matplotlib.use('Agg')  # Backend sin GUI

        fig = plt.figure(figsize=(14, 12))
        plt.imshow(cv2.cvtColor(base, cv2.COLOR_BGR2RGB))
        plt.axis('off')

        coverage_pct = self._compute_coverage() * 100
        plt.title(f"Tracker Debug | Red=Covered Area | Blue=Path | Cov: {coverage_pct:.1f}%")
        plt.savefig(output_path)
        print(f"Imagen guardada en {output_path}")
        plt.close(fig)  # Cerrar figura sin mostrar

def main():
    """Test del tracker."""
    mask_path = r"c:\Users\jf19s\Desktop\PROYECTOS\ACTUALES\STEREO_PHOTOGRAMMETRY_CM5\data\results\debug\cable_mask_left.png"

    # Cargar máscara
    mask = cv2.imread(mask_path, cv2.IMREAD_GRAYSCALE)
    _, mask = cv2.threshold(mask, 127, 255, cv2.THRESH_BINARY)

    # Endpoints
    start = (1248, 668)
    end = (1297, 945)

    # Crear tracker
    tracker = SmartWireTracker(mask, start, end)

    # Trackear
    result = tracker.track_wire(max_iterations=10000)

    # Visualizar
    if result['success']:
        tracker.visualize('data/results/debug/smart_wire_path.png')

    return result


if __name__ == "__main__":
    main()
