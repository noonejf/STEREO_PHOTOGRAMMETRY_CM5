#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Script de prueba para integración del GUI en procesamiento
"""

import cv2
from pathlib import Path
from edge_detection_tuner import open_cable_detection_tuner

# Cargar imágenes de prueba
left_path = Path("data/results/debug/01_left_original.jpg")
right_path = Path("data/results/debug/02_right_original.jpg")

if not left_path.exists():
    print("❌ No se encuentran las imágenes de prueba")
    exit(1)

left_img = cv2.imread(str(left_path))
right_img = cv2.imread(str(right_path))

print("Abriendo GUI de detección de cable...")
print("Ajusta los parámetros y presiona 'Aplicar y Continuar Procesamiento'")

# Abrir GUI - se bloquea hasta que el usuario cierre
result = open_cable_detection_tuner(left_img, right_img)

if result is not None:
    mask_left, mask_right = result
    print("\n✅ Máscaras obtenidas del GUI")
    print(f"   Left mask: {mask_left.shape}, píxeles detectados: {mask_left.sum()}")
    print(f"   Right mask: {mask_right.shape}, píxeles detectados: {mask_right.sum()}")

    # Guardar máscaras para inspección
    debug_path = Path("data/results/debug")
    cv2.imwrite(str(debug_path / "mask_left_from_tuner.png"), mask_left)
    cv2.imwrite(str(debug_path / "mask_right_from_tuner.png"), mask_right)

    print(f"\n   Máscaras guardadas en {debug_path}/")
    print("\n🎉 Integración exitosa! Ahora puedes usar estas máscaras en SGBM")
else:
    print("\n❌ Usuario canceló el ajuste")
