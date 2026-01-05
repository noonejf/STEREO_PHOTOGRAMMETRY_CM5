#!/usr/bin/env python3
"""
Curve Tracker - Extraer y ordenar esqueleto de cable como curva continua
"""

import cv2
import numpy as np
from typing import Dict, Any, List, Tuple, Optional
from pathlib import Path

from utils.logger import get_logger

logger = get_logger(__name__)


class CurveTracker:
    """
    Extrae el esqueleto de un cable desde máscara binaria y lo ordena
    como una curva continua siguiendo el flujo geométrico
    """

    def __init__(self):
        self.skeleton = None
        self.ordered_points = None
        self.curve_segments = []

    def extract_and_order_skeleton(self, mask: np.ndarray,
                                   sample_spacing: int = 2) -> Dict[str, Any]:
        """
        Extraer curva del cable identificando extremos REALES y trazando desde ellos

        Estrategia:
        1. Adelgazar máscara a esqueleto
        2. Limpiar bifurcaciones causadas por sombras/grosor
        3. Identificar extremos reales (puntos con solo 1 vecino)
        4. Trazar desde extremo siguiendo SOLO vecinos inmediatos (no saltos)

        Args:
            mask: Máscara binaria (255=cable, 0=fondo)
            sample_spacing: Espaciado entre puntos en la curva final

        Returns:
            result: Dict con curva ordenada y estadísticas
        """

        logger.info("🔍 Extrayendo esqueleto del cable...")

        # PASO 1: Adelgazar máscara a esqueleto
        mask_binary = (mask > 0).astype(np.uint8)
        skeleton = cv2.ximgproc.thinning(mask_binary * 255,
                                         thinningType=cv2.ximgproc.THINNING_ZHANGSUEN)
        skeleton = (skeleton > 0).astype(np.uint8)

        # PASO 2: NO limpiar - solo usar el skeleton tal cual
        # El problema es que la limpieza fragmenta el cable
        skeleton_clean = skeleton.copy()

        pixels_total = np.sum(skeleton > 0)
        logger.info(f"  Píxeles de esqueleto: {pixels_total}")

        # PASO 3: Identificar los 2 EXTREMOS REALES del cable
        # Estrategia: Buscar puntos con SOLO 1 vecino (endpoints verdaderos)
        logger.info("  Buscando inicio y final del cable...")

        # IMPORTANTE: Buscar endpoints ANTES de cualquier dilatación/limpieza
        # La dilatación puede destruir los endpoints
        endpoints = self._find_endpoints(skeleton_clean)
        logger.info(f"  Endpoints detectados con 1 vecino: {len(endpoints)}")

        # Si hay más de 2 endpoints, NO usar validación compleja
        # En su lugar, simplemente elegir los 2 más alejados
        # (los endpoints falsos suelen estar cerca entre sí)
        if len(endpoints) > 2:
            logger.info(f"  Multiples candidatos, eligiendo los 2 mas alejados...")
            max_dist = 0
            best_pair = None
            for i, p1 in enumerate(endpoints):
                for j, p2 in enumerate(endpoints[i+1:], i+1):
                    dist = np.linalg.norm(np.array(p1) - np.array(p2))
                    if dist > max_dist:
                        max_dist = dist
                        best_pair = (p1, p2)
            if best_pair:
                endpoints = list(best_pair)
                logger.info(f"  Par mas alejado seleccionado: {max_dist:.1f} px")

        # Usar skeleton limpio sin dilatación adicional
        skeleton_final = skeleton_clean

        coords = np.column_stack(np.where(skeleton_final > 0))
        coords = coords[:, [1, 0]]  # (x, y)

        if len(coords) < 2:
            logger.error("❌ Muy pocos puntos de esqueleto!")
            return {'success': False, 'error': 'Insufficient skeleton points'}

        # Si hay exactamente 2 endpoints, usarlos directamente
        if len(endpoints) == 2:
            start_point = endpoints[0]
            end_point = endpoints[1]
            logger.info(f"  ✓ PERFECTO: Exactamente 2 endpoints detectados")

        # Si hay más de 2, elegir los 2 más alejados entre sí
        elif len(endpoints) > 2:
            logger.info(f"  Múltiples endpoints detectados, eligiendo los 2 más alejados...")
            max_dist = 0
            start_point = None
            end_point = None

            for i, p1 in enumerate(endpoints):
                for j, p2 in enumerate(endpoints[i+1:], i+1):
                    dist = np.linalg.norm(np.array(p1) - np.array(p2))
                    if dist > max_dist:
                        max_dist = dist
                        start_point = p1
                        end_point = p2

        # Si hay menos de 2, usar estrategia de fallback (extremos geométricos)
        else:
            logger.warning(f"  Pocos endpoints detectados ({len(endpoints)}), usando fallback...")
            y_min_idx = np.argmin(coords[:, 1])
            y_max_idx = np.argmax(coords[:, 1])
            x_min_idx = np.argmin(coords[:, 0])
            x_max_idx = np.argmax(coords[:, 0])

            candidates = [
                tuple(coords[y_min_idx]),
                tuple(coords[y_max_idx]),
                tuple(coords[x_min_idx]),
                tuple(coords[x_max_idx])
            ]

            max_dist = 0
            start_point = None
            end_point = None
            for i, p1 in enumerate(candidates):
                for j, p2 in enumerate(candidates[i+1:], i+1):
                    dist = np.linalg.norm(np.array(p1) - np.array(p2))
                    if dist > max_dist:
                        max_dist = dist
                        start_point = p1
                        end_point = p2

        logger.info(f"  ✓ INICIO: {start_point}")
        logger.info(f"  ✓ FINAL: {end_point}")
        dist = np.linalg.norm(np.array(start_point) - np.array(end_point))
        logger.info(f"  Distancia entre extremos: {dist:.1f} píxeles")

        # PASO 4: Ordenar TODOS los puntos del skeleton usando vecino más cercano
        # Esto conecta automáticamente fragmentos
        logger.info("  Ordenando todos los puntos del skeleton...")
        ordered_points = self._order_points_nearest_neighbor(coords, start_point=start_point)

        logger.info(f"✓ Curva trazada: {len(ordered_points)} puntos")

        # PASO 5: Re-muestrear curva con espaciado uniforme
        if sample_spacing > 1:
            resampled = self._resample_curve(ordered_points, sample_spacing)
            logger.info(f"  Re-muestreado con spacing={sample_spacing}: {len(resampled)} puntos")
        else:
            resampled = ordered_points

        # PASO 6: Detectar auto-intersecciones SOLO si no hay demasiados puntos
        # (evita cálculos O(N^2) muy costosos)
        if len(resampled) < 2000:
            crossings = self._detect_crossings(resampled, threshold=10)
            logger.info(f"  Auto-intersecciones detectadas: {len(crossings)}")
        else:
            crossings = []
            logger.info(f"  Detección de crossings omitida (demasiados puntos: {len(resampled)})")

        return {
            'success': True,
            'ordered_points': np.array(resampled),
            'num_points': len(resampled),
            'endpoints': [start_point, end_point],  # Los 2 extremos reales
            'crossings': crossings,
            'skeleton': skeleton_final
        }

    def _order_points_nearest_neighbor(self, points: np.ndarray,
                                       start_point: Optional[Tuple[int, int]] = None) -> List[Tuple[int, int]]:
        """
        Ordenar puntos usando algoritmo de vecino más cercano (greedy)

        Esto conecta automáticamente fragmentos del esqueleto
        """

        if len(points) == 0:
            return []

        # Convertir a lista de tuplas
        points_list = [tuple(p) for p in points]

        # Empezar desde punto especificado o el punto con Y más pequeño
        if start_point is not None and start_point in points_list:
            start_idx = points_list.index(start_point)
        else:
            start_idx = np.argmin(points[:, 1])

        ordered = [points_list[start_idx]]
        remaining = set(points_list)
        remaining.remove(points_list[start_idx])

        current = np.array(points_list[start_idx])

        # Conectar puntos de forma greedy (vecino más cercano)
        while remaining:
            # Calcular distancias a todos los puntos restantes
            remaining_array = np.array(list(remaining))
            distances = np.sqrt(np.sum((remaining_array - current)**2, axis=1))

            # Encontrar el más cercano
            min_idx = np.argmin(distances)
            next_point = tuple(remaining_array[min_idx])

            ordered.append(next_point)
            remaining.remove(next_point)
            current = np.array(next_point)

            # Log progreso cada 10%
            if len(ordered) % max(1, len(points_list) // 10) == 0:
                progress = 100 * len(ordered) / len(points_list)
                logger.debug(f"    Ordenando: {progress:.0f}%")

        return ordered

    def _clean_skeleton_branches(self, skeleton: np.ndarray, max_branch_len: int = 3) -> np.ndarray:
        """
        Limpiar bifurcaciones PEQUEÑAS del esqueleto causadas por sombras/grosor

        Solo elimina ramas MUY cortas (< max_branch_len píxeles)
        NO toca la curva principal

        Args:
            skeleton: Esqueleto binario
            max_branch_len: Longitud máxima de rama a eliminar (píxeles)

        Returns:
            Esqueleto limpio
        """

        skeleton_clean = skeleton.copy()

        # Solo eliminar ramas MUY pequeñas (< max_branch_len píxeles)
        for iteration in range(max_branch_len):
            coords = np.column_stack(np.where(skeleton_clean > 0))

            if len(coords) == 0:
                break

            changed = False

            for y, x in coords:
                # Contar vecinos
                neighbors = skeleton_clean[max(0, y-1):y+2, max(0, x-1):x+2]
                num_neighbors = np.sum(neighbors) - 1

                # Si es un extremo (solo 1 vecino), eliminar
                # Esto solo afecta ramas pequeñas porque iteramos max_branch_len veces
                if num_neighbors == 1:
                    skeleton_clean[y, x] = 0
                    changed = True

            # Si no hubo cambios, terminar
            if not changed:
                break

        return skeleton_clean

    def _find_endpoints(self, skeleton: np.ndarray) -> List[Tuple[int, int]]:
        """
        Encontrar puntos extremos del esqueleto (puntos con solo 1 vecino)
        """

        endpoints = []
        coords = np.column_stack(np.where(skeleton > 0))

        for y, x in coords:
            # Contar vecinos en ventana 3x3
            neighbors = skeleton[max(0, y-1):y+2, max(0, x-1):x+2]
            num_neighbors = np.sum(neighbors) - 1  # Excluir el punto mismo

            if num_neighbors == 1:
                endpoints.append((x, y))

        return endpoints

    def _validate_endpoints_robust(self, skeleton: np.ndarray, endpoints: List[Tuple[int, int]],
                                   mask: np.ndarray) -> List[Tuple[int, int]]:
        """
        Validar endpoints con múltiples filtros para encontrar los VERDADEROS extremos

        Filtros aplicados:
        1. Verificar que sean endpoints en un radio más grande (5x5)
        2. Verificar distancia al borde de la máscara
        3. Calcular curvatura local (extremos reales tienen baja curvatura)
        """

        if len(endpoints) <= 2:
            return endpoints

        logger.info(f"  Validando {len(endpoints)} endpoints candidatos...")

        validated = []
        h, w = skeleton.shape

        for ep_x, ep_y in endpoints:
            # FILTRO 1: Verificar que sea endpoint en ventana 5x5
            window_size = 5
            y_min = max(0, ep_y - window_size//2)
            y_max = min(h, ep_y + window_size//2 + 1)
            x_min = max(0, ep_x - window_size//2)
            x_max = min(w, ep_x + window_size//2 + 1)

            window = skeleton[y_min:y_max, x_min:x_max]
            num_neighbors_large = np.sum(window) - 1

            # Si tiene muy pocos vecinos en ventana grande, es candidato fuerte
            if num_neighbors_large < 5:

                # FILTRO 2: Verificar distancia al borde de la máscara
                # Los extremos verdaderos suelen estar en el borde de la máscara
                mask_window = mask[y_min:y_max, x_min:x_max]
                mask_edge = cv2.Canny(mask_window, 50, 150)

                # Distancia al borde más cercano de la máscara
                edge_pixels = np.column_stack(np.where(mask_edge > 0))
                if len(edge_pixels) > 0:
                    center = np.array([window_size//2, window_size//2])
                    distances = np.sqrt(np.sum((edge_pixels - center)**2, axis=1))
                    min_dist_to_edge = np.min(distances)

                    # Endpoint verdadero está cerca del borde (< 3 píxeles)
                    if min_dist_to_edge < 3:
                        validated.append((ep_x, ep_y))
                else:
                    # Si no hay borde detectado, aceptar el punto
                    validated.append((ep_x, ep_y))

        logger.info(f"  Endpoints validados: {len(validated)}")
        return validated if len(validated) > 0 else endpoints

    def _trace_all_segments(self, skeleton: np.ndarray,
                           all_coords: np.ndarray) -> List[List[Tuple[int, int]]]:
        """
        Trazar TODOS los segmentos conectados del esqueleto

        Esto maneja cables fragmentados o con múltiples componentes
        """

        visited = np.zeros_like(skeleton, dtype=bool)
        segments = []

        # Convertir coords a conjunto para búsqueda rápida
        coords_set = set(map(tuple, all_coords))

        # Para cada punto no visitado, iniciar un nuevo segmento
        for coord in all_coords:
            x, y = coord
            if visited[y, x]:
                continue

            # Trazar segmento desde este punto
            segment = self._trace_curve(skeleton, (x, y), visited)

            if len(segment) > 2:  # Solo guardar segmentos significativos
                segments.append(segment)

        return segments

    def _trace_curve(self, skeleton: np.ndarray,
                    start_point: Tuple[int, int],
                    visited: Optional[np.ndarray] = None) -> List[Tuple[int, int]]:
        """
        Trazar curva desde punto inicial siguiendo vecinos conectados

        En caso de bifurcaciones, elige el vecino que mejor continúa
        la dirección actual del cable
        """

        height, width = skeleton.shape

        # Crear visited si no se proporcionó
        if visited is None:
            visited = np.zeros_like(skeleton, dtype=bool)

        ordered = []

        current = start_point
        ordered.append(current)
        visited[current[1], current[0]] = True

        max_iterations = np.sum(skeleton > 0) * 2  # Safety limit
        iterations = 0

        while iterations < max_iterations:
            iterations += 1

            # Buscar vecinos no visitados
            x, y = current
            candidates = []

            # Buscar en ventana 3x3
            for dy in [-1, 0, 1]:
                for dx in [-1, 0, 1]:
                    if dx == 0 and dy == 0:
                        continue

                    nx, ny = x + dx, y + dy

                    # Verificar límites
                    if nx < 0 or nx >= width or ny < 0 or ny >= height:
                        continue

                    # Verificar si es parte del esqueleto y no visitado
                    if skeleton[ny, nx] > 0 and not visited[ny, nx]:
                        candidates.append((nx, ny))

            if len(candidates) == 0:
                # No hay más vecinos - fin de la curva (o loop cerrado)
                break

            # Si hay múltiples candidatos (bifurcación), elegir el mejor
            if len(candidates) == 1:
                next_point = candidates[0]
            else:
                # Elegir candidato que mejor continúa la dirección actual
                if len(ordered) >= 2:
                    # Calcular dirección actual
                    prev = np.array(ordered[-2])
                    curr = np.array(current)
                    direction = curr - prev

                    # Elegir candidato más alineado con dirección
                    best_score = -999
                    next_point = candidates[0]

                    for cand in candidates:
                        cand_vec = np.array(cand) - curr
                        # Producto punto (mayor = más alineado)
                        score = np.dot(direction, cand_vec)
                        if score > best_score:
                            best_score = score
                            next_point = cand
                else:
                    # Sin dirección previa, tomar el primero
                    next_point = candidates[0]

            current = next_point
            ordered.append(current)
            visited[current[1], current[0]] = True

        return ordered

    def _resample_curve(self, points: List[Tuple[int, int]],
                       spacing: int) -> List[Tuple[int, int]]:
        """
        Re-muestrear curva con espaciado uniforme a lo largo de la longitud
        """

        if len(points) < 2:
            return points

        points_array = np.array(points, dtype=np.float32)

        # Calcular distancias acumuladas a lo largo de la curva
        diffs = np.diff(points_array, axis=0)
        distances = np.sqrt(np.sum(diffs**2, axis=1))
        cumulative_dist = np.concatenate([[0], np.cumsum(distances)])

        total_length = cumulative_dist[-1]

        # Puntos de muestreo uniformes
        sample_distances = np.arange(0, total_length, spacing)

        # Interpolar posiciones
        resampled = []
        for dist in sample_distances:
            # Encontrar segmento donde cae este punto
            idx = np.searchsorted(cumulative_dist, dist)

            if idx >= len(points):
                break

            if idx == 0:
                resampled.append(points[0])
            else:
                # Interpolar linealmente entre puntos
                t = (dist - cumulative_dist[idx-1]) / (cumulative_dist[idx] - cumulative_dist[idx-1])
                p0 = points_array[idx-1]
                p1 = points_array[idx]
                interp = p0 + t * (p1 - p0)
                resampled.append((int(interp[0]), int(interp[1])))

        return resampled

    def _detect_crossings(self, points: List[Tuple[int, int]],
                         threshold: int = 10) -> List[Tuple[int, int]]:
        """
        Detectar auto-intersecciones (donde el cable cruza sobre sí mismo)

        Busca pares de puntos en la curva que están muy cerca espacialmente
        pero muy lejos en índice (no son vecinos en la curva)
        """

        crossings = []

        if len(points) < 4:
            return crossings

        points_array = np.array(points)

        # Para cada punto, buscar otros puntos cercanos
        for i in range(len(points)):
            for j in range(i + threshold, len(points)):
                # Distancia euclidiana
                dist = np.linalg.norm(points_array[i] - points_array[j])

                # Si están muy cerca pero alejados en índice -> cruce
                if dist < threshold:
                    crossings.append((i, j))

        return crossings

    def visualize_curve(self, image: np.ndarray,
                       ordered_points: np.ndarray,
                       output_path: Path) -> None:
        """
        Visualizar curva ordenada con gradiente de color para mostrar flujo
        """

        vis = image.copy()
        if len(vis.shape) == 2:
            vis = cv2.cvtColor(vis, cv2.COLOR_GRAY2BGR)

        num_points = len(ordered_points)

        # Dibujar curva con gradiente de color (rojo -> azul siguiendo flujo)
        for i in range(num_points - 1):
            p1 = tuple(ordered_points[i].astype(int))
            p2 = tuple(ordered_points[i+1].astype(int))

            # Color que varía de rojo (inicio) a azul (fin)
            ratio = i / num_points
            color_val = int(ratio * 255)
            color = cv2.applyColorMap(np.array([[color_val]], dtype=np.uint8),
                                     cv2.COLORMAP_JET)[0, 0]
            color = tuple(map(int, color))

            cv2.line(vis, p1, p2, color, 2)

        # Marcar inicio (verde) y fin (magenta)
        if num_points > 0:
            start = tuple(ordered_points[0].astype(int))
            end = tuple(ordered_points[-1].astype(int))
            cv2.circle(vis, start, 8, (0, 255, 0), -1)  # Verde
            cv2.circle(vis, end, 8, (255, 0, 255), -1)  # Magenta

        cv2.imwrite(str(output_path), vis)
        logger.info(f"  Visualización guardada: {output_path}")


if __name__ == "__main__":
    # Test básico
    print("="*80)
    print("CURVE TRACKER - TEST")
    print("="*80)

    # Crear máscara de test (espiral simple)
    test_mask = np.zeros((500, 500), dtype=np.uint8)

    # Dibujar espiral
    center = (250, 250)
    for i in range(100):
        angle = i * 0.2
        radius = 50 + i * 1.5
        x = int(center[0] + radius * np.cos(angle))
        y = int(center[1] + radius * np.sin(angle))
        cv2.circle(test_mask, (x, y), 5, 255, -1)

    tracker = CurveTracker()
    result = tracker.extract_and_order_skeleton(test_mask, sample_spacing=5)

    if result['success']:
        print(f"\n✓ Curva extraída: {result['num_points']} puntos")
        print(f"  Extremos: {result['endpoints']}")
        print(f"  Cruces: {len(result['crossings'])}")
    else:
        print(f"\n❌ Error: {result['error']}")
