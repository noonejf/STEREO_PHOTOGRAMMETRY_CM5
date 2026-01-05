"""
Detecta extremos de cuerda - VERSIÓN SIMPLE Y RÁPIDA
Busca puntos donde hay píxeles blancos solo en un lado (semicírculo).
"""

import cv2
import numpy as np
import matplotlib.pyplot as plt
from scipy.ndimage import distance_transform_edt


def compute_endpoint_score(mask, point, radii=[15, 25, 35, 45, 55]):
    """
    Calcula score de extremidad usando análisis de circunferencias.

    Un verdadero extremo tiene:
    1. Píxeles distribuidos asimétricamente (muchos en un lado, pocos en otro)
    2. Sectores completamente vacíos (espacios sin píxeles)
    3. Pocos píxeles totales alrededor (aislamiento)

    Args:
        mask: Máscara binaria (numpy array)
        point: Coordenadas (x, y) del punto a evaluar
        radii: Lista de radios a probar

    Returns:
        Score: mayor = más probablemente un extremo
    """
    x, y = point
    h, w = mask.shape

    total_score = 0.0

    for radius in radii:
        # Definir región circular
        y_min = max(0, y - radius)
        y_max = min(h, y + radius + 1)
        x_min = max(0, x - radius)
        x_max = min(w, x + radius + 1)

        # Crear máscaras para análisis por sectores (8 sectores)
        sector_counts = np.zeros(8)

        for dy in range(y_min - y, y_max - y):
            for dx in range(x_min - x, x_max - x):
                # Distancia al centro
                dist = np.sqrt(dx**2 + dy**2)

                # Solo píxeles dentro del anillo
                inner_radius = max(0, radius - 10)
                if dist < inner_radius or dist > radius:
                    continue

                # Verificar si hay píxel blanco
                py, px = y + dy, x + dx
                if py < 0 or py >= h or px < 0 or px >= w:
                    continue

                if mask[py, px] > 0:
                    # Calcular sector (0-7)
                    angle = np.arctan2(dy, dx)  # -π a π
                    sector = int((angle + np.pi) / (2 * np.pi) * 8) % 8
                    sector_counts[sector] += 1

        if sector_counts.sum() == 0:
            continue

        # Criterio 1: Número de sectores vacíos (más vacíos = mejor)
        empty_sectors = np.sum(sector_counts == 0)
        empty_score = empty_sectors / 8.0

        # Criterio 2: Asimetría entre sectores
        max_count = sector_counts.max()
        min_count = sector_counts.min()
        asymmetry = (max_count - min_count) / (sector_counts.sum() + 1e-6)

        # Criterio 3: Pocos píxeles totales = más aislado (penalizar muchos píxeles)
        # Normalizar por el área del anillo
        area = np.pi * (radius**2 - inner_radius**2)
        density = sector_counts.sum() / (area + 1e-6)
        isolation_score = 1.0 / (1.0 + density)  # Menos densidad = más aislado

        # Combinar criterios
        score = (empty_score * 2.0) + asymmetry + (isolation_score * 0.5)
        total_score += score

    return total_score


def find_wire_endpoints(mask_path, debug=True):
    """
    Encuentra los dos extremos de la cuerda.

    Estrategia simple:
    1. Adelgazar la máscara a 1 píxel de ancho
    2. Encontrar píxeles con exactamente 1 vecino
    3. Seleccionar los 2 más alejados
    """
    # Cargar máscara
    mask = cv2.imread(mask_path, cv2.IMREAD_GRAYSCALE)
    if mask is None:
        raise ValueError(f"No se pudo cargar: {mask_path}")
    _, mask = cv2.threshold(mask, 127, 255, cv2.THRESH_BINARY)

    print("Adelgazando máscara...")
    # Adelgazar a 1 píxel
    skeleton = cv2.ximgproc.thinning(mask, thinningType=cv2.ximgproc.THINNING_ZHANGSUEN)

    print("Buscando extremos...")
    # Contar vecinos para cada píxel
    kernel = np.array([[1, 1, 1],
                       [1, 0, 1],
                       [1, 1, 1]], dtype=np.uint8)

    neighbor_count = cv2.filter2D((skeleton > 0).astype(np.uint8), -1, kernel)

    # Extremos = píxeles con exactamente 1 vecino
    endpoints_mask = (skeleton > 0) & (neighbor_count == 1)
    y_coords, x_coords = np.where(endpoints_mask)

    candidates = list(zip(x_coords, y_coords))
    print(f"Candidatos encontrados: {len(candidates)}")

    if len(candidates) == 0:
        raise ValueError("No se encontraron extremos")

    if len(candidates) == 1:
        raise ValueError("Solo se encontró un extremo")

    # Seleccionar los 2 verdaderos extremos usando análisis de circunferencias
    if len(candidates) == 2:
        endpoint1, endpoint2 = candidates
    else:
        # Para cada candidato, calcular score de "extremidad"
        endpoint_scores = []
        for candidate in candidates:
            score = compute_endpoint_score(mask, candidate)
            endpoint_scores.append(score)

        # Tomar los 2 con mayor score
        sorted_indices = np.argsort(endpoint_scores)[::-1]  # De mayor a menor
        endpoint1 = candidates[sorted_indices[0]]
        endpoint2 = candidates[sorted_indices[1]]

        if debug:
            print(f"\nScores de extremidad:")
            for i in sorted_indices[:5]:  # Top 5
                print(f"  Candidato {candidates[i]}: score = {endpoint_scores[i]:.3f}")

    if debug:
        visualize_endpoints(mask, skeleton, candidates, endpoint1, endpoint2)

    return endpoint1, endpoint2


def visualize_endpoints(mask, skeleton, all_candidates, endpoint1, endpoint2):
    """Visualiza los resultados."""
    vis = cv2.cvtColor(mask, cv2.COLOR_GRAY2BGR)

    # Dibujar esqueleto en azul
    vis[skeleton > 0] = [255, 150, 50]

    # Todos los candidatos en amarillo
    for x, y in all_candidates:
        cv2.circle(vis, (x, y), 8, (0, 255, 255), 2)

    # Extremos finales MUY VISIBLES
    cv2.circle(vis, endpoint1, 20, (0, 255, 0), -1)  # Verde
    cv2.circle(vis, endpoint2, 20, (0, 0, 255), -1)  # Rojo

    # Etiquetas
    for pt, text, color in [
        (endpoint1, "START", (0, 255, 0)),
        (endpoint2, "END", (0, 0, 255))
    ]:
        (w, h), _ = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, 1.0, 2)
        cv2.rectangle(vis,
                     (pt[0] - 50, pt[1] - 40),
                     (pt[0] - 50 + w + 15, pt[1] - 40 + h + 15),
                     (0, 0, 0), -1)
        cv2.putText(vis, text, (pt[0] - 45, pt[1] - 20),
                   cv2.FONT_HERSHEY_SIMPLEX, 1.0, color, 2)

    plt.figure(figsize=(16, 14))
    plt.imshow(cv2.cvtColor(vis, cv2.COLOR_BGR2RGB))
    plt.title("Extremos de Cuerda Detectados", fontsize=16, weight='bold')
    plt.axis('off')
    plt.tight_layout()

    output_path = 'data/results/debug/wire_endpoints_detection.png'
    plt.savefig(output_path, dpi=150, bbox_inches='tight')
    print(f"\nResultado guardado: {output_path}")
    plt.show()

    dist = np.linalg.norm(np.array(endpoint1) - np.array(endpoint2))
    print(f"\n{'='*50}")
    print(f"EXTREMOS DETECTADOS:")
    print(f"  START (verde): {endpoint1}")
    print(f"  END (rojo):    {endpoint2}")
    print(f"  Distancia:     {dist:.1f} píxeles")
    print(f"{'='*50}\n")


def main():
    mask_path = r"c:\Users\jf19s\Desktop\PROYECTOS\ACTUALES\STEREO_PHOTOGRAMMETRY_CM5\data\results\debug\cable_mask_left.png"

    print("\n" + "="*50)
    print("DETECTOR DE EXTREMOS DE CUERDA")
    print("="*50 + "\n")

    try:
        endpoint1, endpoint2 = find_wire_endpoints(mask_path, debug=True)
        print("✓ Detección exitosa!")

    except Exception as e:
        print(f"\n✗ Error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
