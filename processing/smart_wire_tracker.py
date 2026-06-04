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
        # --- AUTO-SCALE: si el cable es demasiado grueso, escalar la máscara ---
        # Los parámetros del tracker (step=5, search=20) fueron diseñados para
        # cables de ~10-20px de radio. Si la máscara tiene cables más gruesos
        # (p.ej. upscaleada desde preview), escalar hacia abajo.
        self._internal_scale = 1.0
        _dt_init = cv2.distanceTransform((mask > 0).astype(np.uint8), cv2.DIST_L2, 5)
        _dt_max_init = float(np.max(_dt_init)) if np.any(mask > 0) else 1.0
        _TARGET_MAX_DT = 15.0  # radio objetivo en píxeles

        if _dt_max_init > _TARGET_MAX_DT * 1.5:  # cable >22px de radio → escalar
            self._internal_scale = _TARGET_MAX_DT / _dt_max_init
            nh = max(100, int(mask.shape[0] * self._internal_scale))
            nw = max(100, int(mask.shape[1] * self._internal_scale))
            ms = cv2.resize(mask, (nw, nh), interpolation=cv2.INTER_AREA)
            mask = (ms > 127).astype(np.uint8) * 255
            s = self._internal_scale
            start = (max(0, min(nw - 1, int(start[0] * s))),
                     max(0, min(nh - 1, int(start[1] * s))))
            end   = (max(0, min(nw - 1, int(end[0]   * s))),
                     max(0, min(nh - 1, int(end[1]   * s))))
            print(f"  [AUTO-SCALE] Cable grueso (DT_max={_dt_max_init:.0f}px). "
                  f"Escalando {self._internal_scale:.3f}x → {nw}×{nh}px")

        self.mask = mask
        self.start = start
        self.end = end

        # Estado del tracking
        self.path: List[Tuple[int, int]] = []
        self.visited_map = np.zeros_like(mask, dtype=np.uint8)
        self.decision_points: List[DecisionPoint] = []

        # --- CALCULAR DISTANCE TRANSFORM para ancho adaptativo ---
        print("Calculando Distance Transform para ancho adaptativo...")
        self.distance_transform = cv2.distanceTransform(mask, cv2.DIST_L2, 5)

        # --- PARÁMETROS AJUSTADOS ---
        self.step_size = 5
        self.search_radius = 20
        # wire_radius adapta al grosor real del cable (afecta agrupación de candidatos)
        # Con DT_max=15 (nuestro target), wire_radius=15 → umbral de grupo = 30px = diámetro completo
        _dt_max_actual = float(np.max(self.distance_transform)) if np.any(mask > 0) else 9.0
        self.wire_radius = max(9, int(_dt_max_actual))
        self.min_coverage_radius = 4
        # INVARIANTE: max_coverage_radius < search_radius para que siempre quede
        # territorio no-visitado dentro del radio de búsqueda después de marcar.
        # Si max_coverage_radius >= search_radius el tracker queda ciego en el siguiente paso.
        self.max_coverage_radius = self.search_radius - self.step_size  # = 15px

        # Snap START/END al pixel de cable más cercano (corrige DT=0 en bordes de imagen)
        self.start = self._snap_to_mask(self.start)
        self.end   = self._snap_to_mask(self.end)

        # Estadísticas
        self.total_mask_pixels = np.sum(mask > 0)

    def track_wire(self, max_iterations: int = 5000, step_callback=None) -> Dict:
        h, w = self.mask.shape
        dt_max = float(np.max(self.distance_transform))
        print(f"\n=== WIRE TRACKER ===")
        print(f"Máscara {w}×{h} | Cable ~{dt_max*2:.0f}px diámetro | "
              f"step={self.step_size} search={self.search_radius} mark_max={self.max_coverage_radius} wire_r={self.wire_radius}")
        print(f"START={self.start}  END={self.end}")
        if self._internal_scale != 1.0:
            print(f"[Auto-scale activo: {self._internal_scale:.3f}x desde imagen original]")

        self.path = [self.start]
        current = self.start
        self._mark_visited(current)

        best_path = [self.start]   # guarda el path más largo visto
        backtrack_count = 0
        dp_total_created = 0
        COVERAGE_STOP = 0.95       # parar cuando se cubre el 95%
        iteration = 0

        while iteration < max_iterations:
            iteration += 1

            # 1. Verificar si llegamos al END
            dist_to_end = np.linalg.norm(np.array(current) - np.array(self.end))
            if dist_to_end < self.step_size * 3:
                self.path.append(self.end)
                print(f"[OK] Llegada al END en iter {iteration}")
                break

            # 2. Calcular opciones
            candidates = self._find_candidates(current)

            # 3. Filtrar candidatos: no-visitados primero, luego crossing exception
            momentum = self._get_momentum_direction()
            valid_candidates = []
            visited_crossing_candidates = []

            for c in candidates:
                if self.visited_map[c[1], c[0]] == 0:
                    valid_candidates.append(c)
                else:
                    if np.linalg.norm(momentum) > 0.1:
                        direction = np.array(c, dtype=np.float64) - np.array(current, dtype=np.float64)
                        norm = np.linalg.norm(direction)
                        if norm > 0:
                            direction /= norm
                            dot = np.dot(direction, momentum)
                            if dot > 0.85:
                                visited_crossing_candidates.append(c)

            # Info detallada solo en iter 1
            if iteration == 1:
                ar = self._compute_adaptive_radius_at(current)
                status = "⚠️ BLOQUEADO" if ar >= self.search_radius else "✓"
                print(f"[Iter-1] candidatos={len(valid_candidates)} válidos / {len(candidates)} brutos | "
                      f"mark_r={ar}px {status}")
                if len(valid_candidates) == 0:
                    sx, sy = int(current[0]), int(current[1])
                    mask_near = int(np.sum(self.mask[
                        max(0,sy-self.search_radius):min(h,sy+self.search_radius+1),
                        max(0,sx-self.search_radius):min(w,sx+self.search_radius+1)] > 0))
                    print(f"       PROBLEMA: 0 válidos, {mask_near} px de máscara en radio {self.search_radius}")

            # Usar crossing exception si hay pocos candidatos válidos
            if len(valid_candidates) < 3 and len(visited_crossing_candidates) > 0:
                valid_candidates.extend(visited_crossing_candidates)

            # 4. Análisis de flujo
            end_direction = self._get_direction_to_end(current)
            flow_options = self._analyze_flow_options(
                current, np.array(valid_candidates), momentum, end_direction
            )

            next_step = None

            if len(flow_options) == 1:
                next_step = flow_options[0]

            elif len(flow_options) > 1:
                sorted_options = self._sort_options(current, flow_options, momentum)
                next_step = sorted_options[0]
                alternatives = sorted_options[1:]
                dp = DecisionPoint(
                    location=current,
                    alternatives=alternatives,
                    chosen_index=len(self.path)
                )
                self.decision_points.append(dp)
                dp_total_created += 1

                # DEBUG: imprimir detalle de cada DP para diagnóstico de cruces
                self._debug_decision_point(dp_total_created, current, momentum,
                                           flow_options, sorted_options)

            # CASO C: Sin camino → BACKTRACKING
            if next_step is None:
                if self._perform_backtracking():
                    backtrack_count += 1
                    current = self.path[-1]
                    continue
                else:
                    print(f"[!] Sin camino. Backtracks={backtrack_count} DPs creados={dp_total_created}")
                    break

            # Avanzar
            self.path.append(next_step)
            current = next_step
            self._mark_visited(next_step)

            # Guardar el mejor path visto (el backtracking puede truncarlo después)
            if len(self.path) > len(best_path):
                best_path = list(self.path)

            # Callback para visualización en tiempo real
            if step_callback and iteration % 5 == 0:
                cb_path = list(best_path)
                if self._internal_scale != 1.0:
                    inv = 1.0 / self._internal_scale
                    cb_path = [(int(p[0] * inv), int(p[1] * inv)) for p in cb_path]
                step_callback(cb_path, iteration)

            # Progreso periódico + early stop por cobertura
            if iteration % 50 == 0:
                cov = self._compute_coverage()
                if iteration % 200 == 0:
                    cx, cy = int(current[0]), int(current[1])
                    dt_here = float(self.distance_transform[cy, cx])
                    print(f"[{iteration:5d}] pos=({cx},{cy})  path={len(self.path)}pts  "
                          f"cov={cov*100:.1f}%  DT@pos={dt_here:.1f}px  BT={backtrack_count}")

                # Detección de estancamiento: si tras 600 iters la cobertura
                # sigue por debajo del 3% y no hubo DPs, los endpoints son incorrectos
                if iteration == 600 and cov < 0.03 and dp_total_created == 0:
                    print(f"[!] ABORT: {cov*100:.1f}% cobertura tras 600 iters sin DPs "
                          f"→ endpoints incorrectos (START={self.start} END={self.end})")
                    break

                if cov >= COVERAGE_STOP:
                    # Solo parar si el END ya fue alcanzado o está muy cerca
                    dist_end = float(np.linalg.norm(np.array(current) - np.array(self.end)))
                    if dist_end < self.step_size * 8:
                        print(f"[OK] Cov={cov*100:.1f}% + cerca END ({dist_end:.0f}px) → completado")
                        break
                    # Si el END está lejos, seguir aunque la cobertura sea alta

        # Si el tracker terminó cerca del END pero no llegó, conectar directamente
        if self.path:
            dist_end = float(np.linalg.norm(np.array(self.path[-1]) - np.array(self.end)))
            if dist_end < self.step_size * 15 and tuple(self.path[-1]) != tuple(self.end):
                self.path.append(self.end)
                print(f"[END] Conectado al END (d={dist_end:.0f}px)")

        final_coverage = self._compute_coverage()
        print(f"[FIN] {len(self.path)}pts | cov={final_coverage*100:.1f}% | "
              f"iters={iteration} | BT={backtrack_count} | DPs_creados={dp_total_created}")

        self._save_tracker_debug_end(iteration)

        result_path = self.path
        if self._internal_scale != 1.0:
            inv = 1.0 / self._internal_scale
            result_path = [(int(p[0] * inv), int(p[1] * inv)) for p in self.path]

        return {
            'success': True,
            'path': result_path,
            'coverage': final_coverage
        }

    def _perform_backtracking(self) -> bool:
        """
        Retrocede al último punto de decisión con opciones disponibles.
        Desmarca el segmento fallido para que las alternativas puedan
        cruzar por esa zona (necesario para cuerdas enredadas con cruces).
        """
        while self.decision_points:
            last_dp = self.decision_points[-1]

            if not last_dp.alternatives:
                self.decision_points.pop()
                continue

            cut_index = last_dp.chosen_index + 1
            bad_segment = self.path[cut_index:]

            # Desmarcar el segmento fallido para liberar cruces
            for p in bad_segment:
                self._unmark_visited(p)

            self.path = self.path[:cut_index]

            next_option = last_dp.alternatives.pop(0)
            self.path.append(next_option)
            self._mark_visited(next_option)

            return True

        return False

    def _mark_visited(self, point: Tuple[int, int]):
        """
        Marca el área alrededor del punto como visitada.
        INVARIANTE: mark_radius < local_search_radius para que siempre quede
        territorio no visitado dentro del radio de búsqueda del siguiente paso.
        Los umbrales son exactamente los mismos que en _find_candidates.
        """
        x, y = int(point[0]), int(point[1])
        h, w = self.mask.shape
        x = max(0, min(w - 1, x))
        y = max(0, min(h - 1, y))

        dt_point = float(self.distance_transform[y, x])

        s = 8
        roi_dt = self.distance_transform[max(0,y-s):min(h,y+s),
                                          max(0,x-s):min(w,x+s)]
        dt_max_local = float(np.max(roi_dt))

        # Mismos umbrales que _find_candidates para garantizar coherencia
        if dt_point < 3:       # cable muy fino: no mezclar con local_max
            local_search_r = 6
            effective_distance = dt_point
        elif dt_point < 6:     # cable medio
            local_search_r = 12
            effective_distance = dt_point * 0.7 + dt_max_local * 0.3
        else:                  # cable normal/grueso
            local_search_r = self.search_radius
            effective_distance = dt_point * 0.7 + dt_max_local * 0.3

        adaptive_radius = int(effective_distance * 1.5) + 2

        # INVARIANTE: mark_r < local_search_r (siempre queda anillo libre)
        adaptive_radius = max(1, min(adaptive_radius, local_search_r - 2))
        adaptive_radius = min(adaptive_radius, self.max_coverage_radius)

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
        """
        Busca píxeles de cuerda en el radio, verificando conectividad.
        Usa parámetros adaptativos: radio y paso menores cuando el cable es fino,
        para que la línea de conectividad no se salga en zonas curvas delgadas.
        """
        x, y = current
        h, w = self.mask.shape
        cx_c, cy_c = max(0, min(w-1, int(x))), max(0, min(h-1, int(y)))
        dt_here = float(self.distance_transform[cy_c, cx_c])

        # Parámetros adaptativos según grosor local
        if dt_here < 3:      # cable muy fino (1-2px): paso y búsqueda mínimos
            search_r = 6
            min_dist  = 1.0
            allow_gap = True   # tolerar 1px de hueco en la conectividad
        elif dt_here < 6:    # cable medio
            search_r = 12
            min_dist  = 2.0
            allow_gap = True
        else:                # cable normal/grueso
            search_r  = self.search_radius
            min_dist  = self.step_size * 0.5
            allow_gap = False

        y_min = max(0, y - search_r)
        y_max = min(h, y + search_r + 1)
        x_min = max(0, x - search_r)
        x_max = min(w, x + search_r + 1)

        mask_slice = self.mask[y_min:y_max, x_min:x_max]
        if not (mask_slice > 0).any():
            return []

        ys, xs = np.where(mask_slice > 0)
        global_xs = xs + x_min
        global_ys = ys + y_min

        candidates = []
        for cx, cy in zip(global_xs, global_ys):
            dist = np.hypot(cx - x, cy - y)
            if min_dist < dist < search_r:
                if self._check_connectivity(current, (cx, cy), allow_gap=allow_gap):
                    candidates.append((cx, cy))
        return candidates

    def _check_connectivity(self, p1: Tuple[int, int], p2: Tuple[int, int],
                             allow_gap: bool = False) -> bool:
        """
        Verifica que haya cable continuo entre p1 y p2.
        allow_gap=True: tolera 1px de hueco (para cable fino y curvo).
        """
        x1, y1 = p1
        x2, y2 = p2
        dist = np.hypot(x2 - x1, y2 - y1)
        if dist < 1.0:
            return True

        h, w = self.mask.shape
        steps = int(dist * 2.0)
        for i in range(steps + 1):
            t = i / steps
            x = int(x1 + (x2 - x1) * t)
            y = int(y1 + (y2 - y1) * t)

            if not (0 <= y < h and 0 <= x < w):
                return False

            if self.mask[y, x] == 0:
                if not allow_gap:
                    return False
                # Tolerancia: buscar cable en vecindad 3×3
                found = any(
                    0 <= y + dy < h and 0 <= x + dx < w and self.mask[y+dy, x+dx] > 0
                    for dy in (-1, 0, 1) for dx in (-1, 0, 1)
                )
                if not found:
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

            # 5. COMBINACIÓN DE SCORES
            # Nota: dist_to_end eliminado del scoring de cruces — en cruce la dirección
            # al END puede apuntar al strand INCORRECTO (el otro extremo del cable),
            # causando que el tracker cambie de hebra. El momentum (1200) y el grosor (600)
            # son suficientes para mantener la hebra correcta en todos los casos.
            total_score = (
                geometric_score * 1200 +      # Continuidad geométrica (dominante)
                thickness_score * 600 +       # Continuidad de grosor
                centeredness_score * 300 +    # Preferencia por el centro del cable
                lateral_penalty               # Penalización por salto lateral (paralelas)
            )

            scores.append((total_score, opt))

        # Ordenar descendente (mayor score primero)
        scores.sort(key=lambda x: x[0], reverse=True)
        return [x[1] for x in scores]

    def _debug_decision_point(self, dp_num: int, current, momentum,
                               flow_options, sorted_options):
        """Imprime diagnóstico completo de un Decision Point."""
        cx, cy = int(current[0]), int(current[1])
        dt_here = float(self.distance_transform[cy, cx])
        iter_num = len(self.path)

        mom_angle = float(np.degrees(np.arctan2(momentum[1], momentum[0]))) if np.linalg.norm(momentum) > 0.01 else 0.0
        print(f"\n┌─ DP#{dp_num} @ iter {iter_num} | pos=({cx},{cy}) DT={dt_here:.1f}px")
        print(f"│  Momentum: ({momentum[0]:+.3f}, {momentum[1]:+.3f}) → {mom_angle:.0f}° "
              f"({'↑' if momentum[1]<-0.5 else '↓' if momentum[1]>0.5 else '→' if momentum[0]>0.5 else '←'})")

        current_arr = np.array(current)
        for rank, opt in enumerate(sorted_options):
            opt_arr   = np.array(opt)
            direction = (opt_arr - current_arr).astype(np.float32)
            norm      = np.linalg.norm(direction)
            if norm > 0:
                direction /= norm

            opt_angle = float(np.degrees(np.arctan2(direction[1], direction[0])))
            geo = float(np.dot(direction, momentum)) if np.linalg.norm(momentum) > 0.01 else 0.0

            opt_dt = float(self.distance_transform[int(opt[1]), int(opt[0])])
            current_dt = float(self.distance_transform[cy, cx])
            thick_diff = abs(current_dt - opt_dt)
            thick = float(np.exp(-thick_diff / 5.0))
            center = opt_dt / max(self.wire_radius, 1.0)

            parallel_groups = self._detect_parallel_lines(current, flow_options, momentum)
            lat_pen = 0
            if len(parallel_groups) > 1:
                lat = self._get_lateral_distance(current, opt, momentum)
                if lat > self.wire_radius * 1.1:
                    lat_pen = -800

            total = geo * 1200 + thick * 600 + center * 300 + lat_pen

            chosen = "← ELEGIDO" if rank == 0 else ""
            dir_arrow = ('↑' if direction[1]<-0.5 else '↓' if direction[1]>0.5
                         else '→' if direction[0]>0.5 else '←')
            print(f"│  Opción {rank+1}: ({int(opt[0])},{int(opt[1])}) {dir_arrow} {opt_angle:.0f}° | "
                  f"geo={geo:+.3f}({geo*1200:+.0f}) "
                  f"thick={thick:.2f}({thick*600:.0f}) "
                  f"center={center:.2f}({center*300:.0f}) "
                  f"lat={lat_pen:+.0f} "
                  f"TOTAL={total:+.0f}  {chosen}")
        print(f"└─ Elegido: ({int(sorted_options[0][0])},{int(sorted_options[0][1])})")

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

            # Umbral = diámetro completo del cable: candidatos dentro del grosor
            # del cable son la MISMA línea (no paralelas)
            if lateral_diff < self.wire_radius * 2.0:
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

        current_arr = np.array(current, dtype=np.float64)
        centers = []
        visited_cand = [False] * len(candidates)

        # Pre-computar direcciones normalizadas desde current para cada candidato
        dirs = []
        for c in candidates:
            v = c.astype(np.float64) - current_arr
            n = np.linalg.norm(v)
            dirs.append(v / n if n > 3.0 else None)

        for i in range(len(candidates)):
            if visited_cand[i]: continue

            group = [candidates[i]]
            visited_cand[i] = True

            for j in range(i+1, len(candidates)):
                if visited_cand[j]: continue
                dist = np.linalg.norm(candidates[i] - candidates[j])

                # Umbral de distancia: diámetro del cable
                if dist < self.wire_radius * 2.0:
                    # Verificación angular: solo fusionar si apuntan en dirección similar
                    # desde la posición actual. Esto evita mezclar hebras cruzadas que
                    # están cerca en distancia pero divergen en dirección.
                    should_merge = True
                    if dirs[i] is not None and dirs[j] is not None:
                        cos_a = np.clip(np.dot(dirs[i], dirs[j]), -1.0, 1.0)
                        angle_diff = np.degrees(np.arccos(cos_a))
                        # Umbral 50°: separa hebras cruzadas (~60° de separación mínima)
                        # sin fragmentar cables normales (candidatos del mismo cable
                        # con tracker en el centro quedan dentro de ~40° de spread).
                        if angle_diff > 50.0:
                            should_merge = False

                    if should_merge:
                        group.append(candidates[j])
                        visited_cand[j] = True

            # Calcular centro del grupo
            group_arr = np.array(group)
            center = tuple(np.mean(group_arr, axis=0).astype(int))
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
        
        # 3. Dibujar PATH en CIAN brillante (self.path puede estar en coords originales)
        if len(self.path) > 1:
            draw_path = self.path
            if self._internal_scale != 1.0:
                s = self._internal_scale
                draw_path = [(int(p[0] * s), int(p[1] * s)) for p in self.path]
            pts = np.array(draw_path, np.int32).reshape((-1, 1, 2))
            cv2.polylines(base, [pts], False, (255, 255, 0), 2)

        # 4. Dibujar puntos de decisión y Start/End
        for dp in self.decision_points:
            cv2.circle(base, dp.location, 6, (0, 255, 255), -1)

        cv2.circle(base, self.start, 8, (0, 255, 0), -1)
        cv2.circle(base, self.end, 8, (0, 0, 255), -1)
        
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

    # ------------------------------------------------------------------ #
    #  HELPERS                                                             #
    # ------------------------------------------------------------------ #

    def _snap_to_mask(self, point: Tuple[int, int]) -> Tuple[int, int]:
        """Mueve el punto al pixel de cable más cercano si está en fondo (DT=0)."""
        h, w = self.mask.shape
        x = max(0, min(w - 1, int(point[0])))
        y = max(0, min(h - 1, int(point[1])))
        if self.mask[y, x] > 0:
            return (x, y)
        for r in range(1, 60):
            y0, y1 = max(0, y - r), min(h, y + r + 1)
            x0, x1 = max(0, x - r), min(w, x + r + 1)
            roi = self.mask[y0:y1, x0:x1]
            ys, xs = np.where(roi > 0)
            if len(ys) > 0:
                dists = np.hypot(xs - (x - x0), ys - (y - y0))
                idx = int(np.argmin(dists))
                nx, ny = int(xs[idx]) + x0, int(ys[idx]) + y0
                print(f"  [SNAP] ({point[0]},{point[1]}) fuera del cable → ({nx},{ny}) ({r}px)")
                return (nx, ny)
        return (x, y)

    def _compute_adaptive_radius_at(self, point: Tuple[int, int]) -> int:
        """Mismo cálculo que _mark_visited (para debug coherente)."""
        x, y = int(point[0]), int(point[1])
        h, w = self.mask.shape
        dt_point = float(self.distance_transform[max(0,min(h-1,y)), max(0,min(w-1,x))])
        s = 8
        roi = self.distance_transform[max(0,y-s):min(h,y+s), max(0,x-s):min(w,x+s)]
        dt_max_local = float(np.max(roi))
        if dt_point < 3:
            local_search_r = 6
            eff = dt_point
        elif dt_point < 6:
            local_search_r = 12
            eff = dt_point * 0.7 + dt_max_local * 0.3
        else:
            local_search_r = self.search_radius
            eff = dt_point * 0.7 + dt_max_local * 0.3
        r = int(eff * 1.5) + 2
        return max(1, min(r, local_search_r - 2, self.max_coverage_radius))

    def _save_tracker_debug_end(self, iterations: int):
        """Guarda imagen de resultado final + mapa de grosor del cable."""
        from pathlib import Path
        d = Path("data/results/debug/tracker")
        d.mkdir(parents=True, exist_ok=True)
        cov = self._compute_coverage() * 100

        # --- Imagen 1: result.png — máscara + visitado + path ---
        vis = cv2.cvtColor(self.mask, cv2.COLOR_GRAY2BGR)
        vis[self.mask > 0] = [60, 60, 60]
        overlay = vis.copy()
        overlay[self.visited_map > 0] = [0, 0, 180]
        cv2.addWeighted(overlay, 0.5, vis, 0.5, 0, vis)

        if len(self.path) > 1:
            pts = np.array(self.path, np.int32).reshape((-1, 1, 2))
            cv2.polylines(vis, [pts], False, (0, 220, 255), 2)

        last_pos = tuple(int(v) for v in self.path[-1]) if self.path else self.start
        cv2.circle(vis, last_pos, 10, (0, 255, 255), 2)  # última posición del tracker
        cv2.circle(vis, self.start, 8, (0, 255, 0), -1)
        cv2.circle(vis, self.end,   8, (0, 0, 255), -1)
        cv2.putText(vis, f"{len(self.path)}pts  cov={cov:.1f}%  iters={iterations}",
                    (10, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (220, 220, 220), 2)
        cv2.putText(vis, "Cyan=last pos  Amarillo=path  Azul=visitado",
                    (10, 55), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (180, 180, 180), 1)
        cv2.imwrite(str(d / "result.png"), vis)

        # --- Imagen 2: thickness.png — DT como heatmap + path encima ---
        dt_norm = cv2.normalize(self.distance_transform, None, 0, 255,
                                cv2.NORM_MINMAX).astype(np.uint8)
        dt_color = cv2.applyColorMap(dt_norm, cv2.COLORMAP_JET)
        # Solo colorear donde hay cable; fondo negro
        dt_color[self.mask == 0] = [0, 0, 0]

        # Marcar zonas peligrosamente delgadas (DT < 3px) en rojo brillante
        thin_zone = (self.mask > 0) & (self.distance_transform < 3)
        dt_color[thin_zone] = [0, 0, 255]

        if len(self.path) > 1:
            pts = np.array(self.path, np.int32).reshape((-1, 1, 2))
            cv2.polylines(dt_color, [pts], False, (255, 255, 255), 2)

        cv2.circle(dt_color, last_pos, 10, (0, 255, 255), 2)
        cv2.circle(dt_color, self.start, 8, (0, 255, 0), -1)
        cv2.circle(dt_color, self.end,   8, (255, 0, 255), -1)

        dt_max = float(np.max(self.distance_transform))
        thin_px = int(np.sum(thin_zone))
        cv2.putText(dt_color,
                    f"DT_max={dt_max:.1f}px  Rojo=zona fina(<3px): {thin_px}px",
                    (10, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (220, 220, 220), 2)
        cv2.putText(dt_color,
                    "Azul=grueso  Verde/Amarillo=medio  Rojo=fino(<3px)",
                    (10, 55), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (180, 180, 180), 1)
        cv2.imwrite(str(d / "thickness.png"), dt_color)

        # DT a lo largo del path (print)
        if len(self.path) > 5:
            step = max(1, len(self.path) // 10)
            dt_profile = []
            for p in self.path[::step]:
                px, py = int(p[0]), int(p[1])
                dt_profile.append(f"{self.distance_transform[py, px]:.0f}")
            print(f"[DT a lo largo del path]: {' → '.join(dt_profile)}")

        print(f"[Imagen] result.png + thickness.png en {d}")


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
