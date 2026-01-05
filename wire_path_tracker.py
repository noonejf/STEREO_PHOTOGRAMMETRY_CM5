"""
Wire Path Tracker - Reconstrucción 2D de cuerda siguiendo el flujo de la máscara.

NO usa skeleton. Sigue el flujo natural de la cuerda, manejando cruces
y auto-intersecciones inteligentemente.
"""

import cv2
import numpy as np
import matplotlib.pyplot as plt
from detect_wire_endpoints import find_wire_endpoints


class WirePathTracker:
    """Rastrea el camino de una cuerda desde START hasta END."""

    def __init__(self, mask_path, start_point=None, end_point=None):
        """
        Args:
            mask_path: Ruta a la máscara binaria
            start_point: Punto inicial (x, y). Si None, se detecta automáticamente
            end_point: Punto final (x, y). Si None, se detecta automáticamente
        """
        self.mask = cv2.imread(mask_path, cv2.IMREAD_GRAYSCALE)
        if self.mask is None:
            raise ValueError(f"No se pudo cargar: {mask_path}")
        _, self.mask = cv2.threshold(self.mask, 127, 255, cv2.THRESH_BINARY)

        # Encontrar extremos
        if start_point is None or end_point is None:
            print("Detectando extremos...")
            self.start, self.end = find_wire_endpoints(mask_path, debug=False)
            print(f"  START: {self.start}")
            print(f"  END: {self.end}")
        else:
            self.start = start_point
            self.end = end_point
            print(f"Usando extremos proporcionados:")
            print(f"  START: {self.start}")
            print(f"  END: {self.end}")

    def track_wire_path(self, step_size=3):
        """
        Rastrea el camino de la cuerda desde START hasta END.

        Args:
            step_size: Tamaño del paso (píxeles) - más grande = más rápido pero menos preciso

        Returns:
            Lista de puntos (x, y) que forman el camino
        """
        print(f"\nRastreando cuerda con step_size={step_size}...")

        path = [self.start]
        current_pos = np.array(self.start, dtype=float)
        visited_map = np.zeros_like(self.mask, dtype=np.uint8)

        # Marcar región inicial como visitada
        cv2.circle(visited_map, self.start, step_size, 255, -1)

        max_iterations = 10000
        iteration = 0

        while iteration < max_iterations:
            iteration += 1

            # Calcular dirección de flujo
            flow_direction = self._compute_flow_direction(
                current_pos,
                path[-2] if len(path) > 1 else None,
                visited_map,
                step_size
            )

            if flow_direction is None:
                print(f"  Llegó al final o sin salida en iteración {iteration}")
                break

            # Avanzar en esa dirección
            next_pos = current_pos + flow_direction * step_size
            next_pos_int = tuple(next_pos.astype(int))

            # Verificar si llegamos al END
            dist_to_end = np.linalg.norm(next_pos - np.array(self.end))
            if dist_to_end < step_size * 2:
                path.append(self.end)
                print(f"  ¡Llegó al END en iteración {iteration}!")
                break

            # Agregar al camino
            path.append(next_pos_int)
            current_pos = next_pos

            # Marcar como visitado
            cv2.circle(visited_map, next_pos_int, step_size // 2, 255, -1)

            if iteration % 100 == 0:
                print(f"  Progreso: {iteration} pasos, {len(path)} puntos")

        print(f"Camino completado: {len(path)} puntos")
        return path

    def _compute_flow_direction(self, current_pos, previous_pos, visited_map, step_size):
        """
        Calcula la dirección del flujo de la cuerda.

        Estrategia mejorada para cruces:
        1. Priorizar FUERTEMENTE el momentum (seguir recto)
        2. En cruces, elegir la dirección más alineada con la trayectoria
        3. Ignorar pequeñas protuberancias/pelos
        """
        x, y = int(current_pos[0]), int(current_pos[1])
        search_radius = step_size * 3

        # Obtener píxeles candidatos en la vecindad
        y_min = max(0, y - search_radius)
        y_max = min(self.mask.shape[0], y + search_radius + 1)
        x_min = max(0, x - search_radius)
        x_max = min(self.mask.shape[1], x + search_radius + 1)

        # Región de búsqueda
        mask_region = self.mask[y_min:y_max, x_min:x_max]
        visited_region = visited_map[y_min:y_max, x_min:x_max]

        # Píxeles de cuerda NO visitados (preferencia)
        unvisited_wire = (mask_region > 0) & (visited_region == 0)

        # Si no hay píxeles no visitados, permitir visitados (cruces)
        if not unvisited_wire.any():
            wire_pixels = (mask_region > 0)
        else:
            wire_pixels = unvisited_wire

        if not wire_pixels.any():
            return None  # Sin salida

        # Obtener coordenadas de píxeles de cuerda
        wire_y, wire_x = np.where(wire_pixels)

        # Convertir a coordenadas globales
        wire_y = wire_y + y_min
        wire_x = wire_x + x_min

        # Calcular vectores desde posición actual
        vectors = np.column_stack([wire_x - x, wire_y - y])
        distances = np.linalg.norm(vectors, axis=1)

        # Filtrar píxeles muy cercanos (ya estamos ahí)
        far_enough = distances > step_size * 0.7
        if not far_enough.any():
            return None

        vectors = vectors[far_enough]
        distances = distances[far_enough]
        wire_x = wire_x[far_enough]
        wire_y = wire_y[far_enough]

        # Normalizar vectores
        directions = vectors / (distances[:, np.newaxis] + 1e-6)

        # MEJORADO: Momentum MUY fuerte para evitar zigzags en cruces
        if previous_pos is not None:
            prev_direction = current_pos - np.array(previous_pos)
            prev_direction = prev_direction / (np.linalg.norm(prev_direction) + 1e-6)

            # Calcular alineación con dirección previa
            alignment = np.dot(directions, prev_direction)

            # CLAVE: Penalizar FUERTEMENTE direcciones que no estén adelante
            # alignment > 0.7 = casi recto adelante
            # alignment < 0 = hacia atrás (muy malo)

            # Priorizar fuertemente direcciones alineadas (más simple y rápido)
            # Si alignment > 0.5 (ángulo < 60°), dar mucho peso
            # Si alignment < 0, muy poco peso (ir hacia atrás)
            alignment_score = np.maximum(alignment, 0) ** 4  # Cuarta potencia para énfasis

            # Penalizar distancias largas
            distance_score = 1.0 / (distances + 1e-6)

            # Combinar: priorizar MUCHO la alineación
            weights = alignment_score * distance_score

            # Eliminar opciones hacia atrás
            weights[alignment < 0] = 0  # Absolutamente no ir hacia atrás

            if weights.sum() == 0:
                # Si no hay buenas opciones adelante, buscar cualquier dirección no visitada
                weights = distance_score
        else:
            # Sin dirección previa, solo usar cercanía
            weights = 1.0 / (distances + 1e-6)

        # Normalizar pesos
        weights = weights / (weights.sum() + 1e-6)

        # En lugar de centro de masa, elegir LA MEJOR opción directamente
        # (evita promediar entre dos caminos en un cruce)
        best_idx = np.argmax(weights)
        target_x = wire_x[best_idx]
        target_y = wire_y[best_idx]

        # Dirección hacia ese punto
        direction = np.array([target_x - x, target_y - y], dtype=float)
        direction_norm = np.linalg.norm(direction)

        if direction_norm < 1e-6:
            return None

        return direction / direction_norm

    def visualize_path(self, path, output_path='data/results/debug/wire_path.png'):
        """Visualiza el camino reconstruido."""
        # Crear imagen RGB
        vis = cv2.cvtColor(self.mask, cv2.COLOR_GRAY2BGR)

        # Dibujar camino como línea continua
        path_array = np.array(path, dtype=np.int32)
        cv2.polylines(vis, [path_array], False, (0, 255, 0), 3)

        # Marcar START y END
        cv2.circle(vis, self.start, 15, (0, 255, 0), -1)
        cv2.circle(vis, self.end, 15, (0, 0, 255), -1)

        # Etiquetas
        cv2.putText(vis, "START", (self.start[0] - 40, self.start[1] - 20),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)
        cv2.putText(vis, "END", (self.end[0] - 30, self.end[1] - 20),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 255), 2)

        plt.figure(figsize=(16, 14))
        plt.imshow(cv2.cvtColor(vis, cv2.COLOR_BGR2RGB))
        plt.title(f"Reconstrucción de Cuerda - {len(path)} puntos", fontsize=16, weight='bold')
        plt.axis('off')
        plt.tight_layout()
        plt.savefig(output_path, dpi=150, bbox_inches='tight')
        print(f"\nResultado guardado: {output_path}")
        plt.show()


def main():
    mask_path = r"c:\Users\jf19s\Desktop\PROYECTOS\ACTUALES\STEREO_PHOTOGRAMMETRY_CM5\data\results\debug\cable_mask_left.png"

    print("\n" + "="*60)
    print("WIRE PATH TRACKER - Reconstrucción 2D de Cuerda")
    print("="*60 + "\n")

    try:
        # Usar extremos ya conocidos para acelerar
        start = (1248, 668)
        end = (1297, 945)

        tracker = WirePathTracker(mask_path, start_point=start, end_point=end)
        path = tracker.track_wire_path(step_size=5)
        tracker.visualize_path(path)

        print("\nDetección exitosa!")

    except Exception as e:
        print(f"\nError: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
