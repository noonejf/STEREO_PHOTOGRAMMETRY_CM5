#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Detector de cable basado ÚNICAMENTE en GEOMETRÍA/BORDES
Ignora completamente el color - solo busca estructuras físicas
"""

import sys
import cv2
import numpy as np
from pathlib import Path

# Fix encoding en Windows
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')

def detect_wire_edges_v1_sobel(img, debug_name=""):
    """
    VERSIÓN 1: Detección usando operador Sobel (gradientes direccionales)
    Detecta cambios de intensidad en cualquier dirección
    """
    print(f"\n{'='*80}")
    print(f"MÉTODO 1: Sobel (Gradientes)")
    print(f"{'='*80}")

    # Convertir a escala de grises
    if len(img.shape) == 3:
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    else:
        gray = img.copy()

    # Aplicar Sobel en X e Y
    sobel_x = cv2.Sobel(gray, cv2.CV_64F, 1, 0, ksize=3)
    sobel_y = cv2.Sobel(gray, cv2.CV_64F, 0, 1, ksize=3)

    # Magnitud del gradiente
    gradient_mag = np.sqrt(sobel_x**2 + sobel_y**2)
    gradient_mag = np.uint8(np.clip(gradient_mag, 0, 255))

    # Umbralizar - solo bordes fuertes
    mean_grad = np.mean(gradient_mag)
    std_grad = np.std(gradient_mag)
    threshold = mean_grad + 1.5 * std_grad

    mask = (gradient_mag > threshold).astype(np.uint8)

    # Morfología: Cerrar gaps
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel, iterations=2)
    mask = cv2.dilate(mask, kernel, iterations=1)

    pixels_detected = np.sum(mask > 0)
    print(f"   Umbral gradiente: {threshold:.2f}")
    print(f"   Píxeles detectados: {pixels_detected} ({100*pixels_detected/mask.size:.2f}%)")

    if debug_name:
        save_debug(img, mask, gradient_mag, f"{debug_name}_v1_sobel")

    return mask, gradient_mag


def detect_wire_edges_v2_laplacian(img, debug_name=""):
    """
    VERSIÓN 2: Detección usando Laplaciano (segunda derivada)
    Muy sensible a cambios abruptos - perfecto para cables finos
    """
    print(f"\n{'='*80}")
    print(f"MÉTODO 2: Laplaciano (Segunda derivada)")
    print(f"{'='*80}")

    # Convertir a escala de grises
    if len(img.shape) == 3:
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    else:
        gray = img.copy()

    # Suavizado mínimo para reducir ruido
    blurred = cv2.GaussianBlur(gray, (3, 3), 0)

    # Laplaciano
    laplacian = cv2.Laplacian(blurred, cv2.CV_64F, ksize=3)
    laplacian_abs = np.abs(laplacian)
    laplacian_norm = np.uint8(np.clip(laplacian_abs, 0, 255))

    # Umbralizar
    mean_lap = np.mean(laplacian_abs)
    std_lap = np.std(laplacian_abs)
    threshold = mean_lap + 2.0 * std_lap

    mask = (laplacian_abs > threshold).astype(np.uint8)

    # Morfología
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel, iterations=2)
    mask = cv2.dilate(mask, kernel, iterations=1)

    pixels_detected = np.sum(mask > 0)
    print(f"   Umbral Laplaciano: {threshold:.2f}")
    print(f"   Píxeles detectados: {pixels_detected} ({100*pixels_detected/mask.size:.2f}%)")

    if debug_name:
        save_debug(img, mask, laplacian_norm, f"{debug_name}_v2_laplacian")

    return mask, laplacian_norm


def detect_wire_edges_v3_canny_adaptive(img, debug_name=""):
    """
    VERSIÓN 3: Canny con umbrales adaptativos basados en estadísticas
    """
    print(f"\n{'='*80}")
    print(f"MÉTODO 3: Canny Adaptativo")
    print(f"{'='*80}")

    # Convertir a escala de grises
    if len(img.shape) == 3:
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    else:
        gray = img.copy()

    # Suavizado mínimo
    blurred = cv2.GaussianBlur(gray, (3, 3), 0)

    # Calcular umbrales adaptativos basados en mediana
    median_val = np.median(blurred)
    sigma = 0.33  # Factor estándar
    lower = int(max(0, (1.0 - sigma) * median_val))
    upper = int(min(255, (1.0 + sigma) * median_val))

    # Probar múltiples configuraciones
    configs = [
        (lower, upper, "Auto (mediana)"),
        (10, 30, "Muy sensible"),
        (20, 60, "Sensible"),
        (30, 90, "Moderado"),
    ]

    best_mask = None
    best_score = 0
    best_config = None

    for low, high, name in configs:
        edges = cv2.Canny(blurred, low, high, apertureSize=3, L2gradient=True)

        # Morfología
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
        mask = cv2.dilate(edges, kernel, iterations=2)
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel, iterations=2)

        pixels = np.sum(mask > 0)
        # Score: queremos detectar algo pero no demasiado (1-5% es ideal)
        ideal_percentage = 0.03  # 3%
        current_percentage = pixels / mask.size
        score = 1.0 - abs(current_percentage - ideal_percentage)

        print(f"   Config {name}: low={low}, high={high} -> {pixels} px ({100*current_percentage:.2f}%) [score: {score:.3f}]")

        if score > best_score:
            best_score = score
            best_mask = mask
            best_config = (low, high, name)

    print(f"\n   ✓ MEJOR: {best_config[2]} (low={best_config[0]}, high={best_config[1]})")

    if debug_name:
        save_debug(img, best_mask, best_mask, f"{debug_name}_v3_canny")

    return best_mask, best_mask


def detect_wire_edges_v4_morphological_gradient(img, debug_name=""):
    """
    VERSIÓN 4: Gradiente morfológico (dilatación - erosión)
    Excelente para detectar contornos de objetos
    """
    print(f"\n{'='*80}")
    print(f"MÉTODO 4: Gradiente Morfológico")
    print(f"{'='*80}")

    # Convertir a escala de grises
    if len(img.shape) == 3:
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    else:
        gray = img.copy()

    # Probar diferentes tamaños de kernel
    best_mask = None
    best_pixels = 0

    for ksize in [3, 5, 7]:
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (ksize, ksize))

        # Gradiente morfológico = dilatación - erosión
        gradient = cv2.morphologyEx(gray, cv2.MORPH_GRADIENT, kernel)

        # Umbralizar
        mean_val = np.mean(gradient)
        std_val = np.std(gradient)
        threshold = mean_val + 1.5 * std_val

        mask = (gradient > threshold).astype(np.uint8)

        # Cerrar gaps
        kernel_close = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel_close, iterations=2)

        pixels = np.sum(mask > 0)
        print(f"   Kernel {ksize}x{ksize}: {pixels} px ({100*pixels/mask.size:.2f}%)")

        # Preferir el que detecte algo razonable (1-10%)
        if 0.01 <= pixels/mask.size <= 0.10:
            if pixels > best_pixels:
                best_pixels = pixels
                best_mask = mask

    if best_mask is None:
        # Fallback: usar el último
        best_mask = mask

    if debug_name:
        save_debug(img, best_mask, gradient, f"{debug_name}_v4_morphgrad")

    return best_mask, gradient


def detect_wire_edges_v5_tophat(img, debug_name=""):
    """
    VERSIÓN 5: Top-Hat Transform
    Detecta estructuras más CLARAS que el fondo (perfecto para cable blanco)
    """
    print(f"\n{'='*80}")
    print(f"MÉTODO 5: Top-Hat (Estructuras claras)")
    print(f"{'='*80}")

    # Convertir a escala de grises
    if len(img.shape) == 3:
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    else:
        gray = img.copy()

    # Top-hat: imagen - apertura
    # Resalta objetos pequeños y brillantes
    kernel_sizes = [7, 11, 15, 21]
    best_mask = None
    best_pixels = 0

    for ksize in kernel_sizes:
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (ksize, ksize))
        tophat = cv2.morphologyEx(gray, cv2.MORPH_TOPHAT, kernel)

        # Umbralizar
        mean_val = np.mean(tophat)
        std_val = np.std(tophat)
        threshold = mean_val + 2.0 * std_val

        mask = (tophat > threshold).astype(np.uint8)

        # Conectar componentes
        kernel_connect = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel_connect, iterations=2)
        mask = cv2.dilate(mask, kernel_connect, iterations=1)

        pixels = np.sum(mask > 0)
        print(f"   Kernel {ksize}x{ksize}: {pixels} px ({100*pixels/mask.size:.2f}%)")

        if 0.001 <= pixels/mask.size <= 0.10:
            if pixels > best_pixels:
                best_pixels = pixels
                best_mask = mask

    if best_mask is None:
        best_mask = mask

    if debug_name:
        save_debug(img, best_mask, tophat, f"{debug_name}_v5_tophat")

    return best_mask, tophat


def detect_wire_edges_v6_combined(img, debug_name=""):
    """
    VERSIÓN 6: COMBINACIÓN de múltiples métodos
    Fusiona los mejores resultados
    """
    print(f"\n{'='*80}")
    print(f"MÉTODO 6: COMBINADO (Fusión de técnicas)")
    print(f"{'='*80}")

    # Ejecutar todos los métodos
    mask1, _ = detect_wire_edges_v1_sobel(img, debug_name="")
    mask2, _ = detect_wire_edges_v2_laplacian(img, debug_name="")
    mask3, _ = detect_wire_edges_v3_canny_adaptive(img, debug_name="")
    mask4, _ = detect_wire_edges_v4_morphological_gradient(img, debug_name="")
    mask5, _ = detect_wire_edges_v5_tophat(img, debug_name="")

    # Votar: píxel es válido si al menos 2 métodos lo detectan
    votes = (mask1.astype(int) + mask2.astype(int) + mask3.astype(int) +
             mask4.astype(int) + mask5.astype(int))

    # Diferentes estrategias de votación
    strategies = {
        "Al menos 1 voto": votes >= 1,
        "Al menos 2 votos": votes >= 2,
        "Al menos 3 votos (mayoría)": votes >= 3,
        "Unanimidad (5 votos)": votes >= 5,
    }

    best_mask = None
    best_score = 0

    for name, mask in strategies.items():
        pixels = np.sum(mask)
        percentage = pixels / mask.size

        # Score: preferir 1-5%
        ideal = 0.03
        score = 1.0 - abs(percentage - ideal)

        print(f"   {name}: {pixels} px ({100*percentage:.2f}%) [score: {score:.3f}]")

        if score > best_score:
            best_score = score
            best_mask = mask.astype(np.uint8)

    # Limpieza final
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
    best_mask = cv2.morphologyEx(best_mask, cv2.MORPH_CLOSE, kernel, iterations=2)

    if debug_name:
        save_debug(img, best_mask, votes.astype(np.uint8) * 51, f"{debug_name}_v6_combined")

    return best_mask, votes


def save_debug(img, mask, edge_map, filename):
    """Guardar visualizaciones de debug"""
    debug_path = Path("data/results/debug/wire_detection")
    debug_path.mkdir(parents=True, exist_ok=True)

    # 1. Máscara binaria
    cv2.imwrite(str(debug_path / f"{filename}_mask.png"), mask * 255)

    # 2. Mapa de bordes/gradientes
    cv2.imwrite(str(debug_path / f"{filename}_edges.png"), edge_map)

    # 3. Overlay sobre imagen original
    overlay = img.copy()
    if len(overlay.shape) == 2:
        overlay = cv2.cvtColor(overlay, cv2.COLOR_GRAY2BGR)

    # Pintar máscara en verde brillante
    overlay[mask > 0] = [0, 255, 0]

    # Mezclar con original
    result = cv2.addWeighted(
        img if len(img.shape) == 3 else cv2.cvtColor(img, cv2.COLOR_GRAY2BGR),
        0.6, overlay, 0.4, 0
    )
    cv2.imwrite(str(debug_path / f"{filename}_overlay.jpg"), result)


def main():
    """Ejecutar todos los métodos de detección"""

    print("="*80)
    print("DETECTOR DE CABLE - BASADO EN GEOMETRÍA")
    print("="*80)

    # Cargar imagen
    img_path = Path("data/results/debug/01_left_original.jpg")

    if not img_path.exists():
        print(f"❌ ERROR: No se encuentra {img_path}")
        return

    print(f"\n📂 Cargando imagen: {img_path}")
    img = cv2.imread(str(img_path))
    print(f"   Tamaño: {img.shape}")

    # Ejecutar todos los métodos
    methods = [
        ("SOBEL", detect_wire_edges_v1_sobel),
        ("LAPLACIAN", detect_wire_edges_v2_laplacian),
        ("CANNY", detect_wire_edges_v3_canny_adaptive),
        ("MORPH_GRADIENT", detect_wire_edges_v4_morphological_gradient),
        ("TOPHAT", detect_wire_edges_v5_tophat),
        ("COMBINED", detect_wire_edges_v6_combined),
    ]

    results = {}

    for name, method in methods:
        mask, edge_map = method(img, debug_name=name.lower())
        results[name] = {
            'mask': mask,
            'edge_map': edge_map,
            'pixels': np.sum(mask > 0),
            'percentage': 100 * np.sum(mask > 0) / mask.size
        }

    # Resumen
    print("\n" + "="*80)
    print("RESUMEN DE RESULTADOS")
    print("="*80)
    print(f"\n{'Método':<20} {'Píxeles detectados':<25} {'Porcentaje':<15}")
    print("-"*80)

    for name, data in results.items():
        print(f"{name:<20} {data['pixels']:>12} píxeles       {data['percentage']:>8.2f}%")

    print("\n" + "="*80)
    print("ARCHIVOS GENERADOS:")
    print("="*80)
    print("\nRevisa la carpeta: data/results/debug/wire_detection/")
    print("\nPara cada método encontrarás:")
    print("  - *_mask.png     : Máscara binaria (blanco=cable detectado)")
    print("  - *_edges.png    : Mapa de bordes/gradientes")
    print("  - *_overlay.jpg  : Detección superpuesta en verde")

    print("\n✅ DETECCIÓN COMPLETADA")
    print("\n💡 SIGUIENTE PASO:")
    print("   1. Revisa los overlays (*_overlay.jpg)")
    print("   2. Identifica qué método detecta mejor el cable")
    print("   3. Ajustaremos los parámetros del mejor método")


if __name__ == "__main__":
    main()
