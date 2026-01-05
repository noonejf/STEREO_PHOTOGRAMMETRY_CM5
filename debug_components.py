#!/usr/bin/env python3
"""Debug: Visualizar componentes y ver si START/END están conectados."""

import cv2
import numpy as np
import matplotlib.pyplot as plt

# Cargar máscara
mask_path = r"c:\Users\jf19s\Desktop\PROYECTOS\ACTUALES\STEREO_PHOTOGRAMMETRY_CM5\data\results\debug\cable_mask_left.png"
mask = cv2.imread(mask_path, cv2.IMREAD_GRAYSCALE)
_, mask = cv2.threshold(mask, 127, 255, cv2.THRESH_BINARY)

start = (1248, 668)
end = (1297, 945)

# Limpiar máscara (igual que el planner)
kernel_erode = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
eroded = cv2.erode(mask, kernel_erode, iterations=2)
kernel_dilate = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
cleaned = cv2.dilate(eroded, kernel_dilate, iterations=1)

# Detectar componentes
num_components, labels = cv2.connectedComponents(cleaned)

print(f"\n=== ANALISIS DE COMPONENTES ===")
print(f"Total componentes: {num_components - 1}")

# ¿En qué componente están START y END?
start_component = labels[start[1], start[0]] if 0 <= start[1] < labels.shape[0] and 0 <= start[0] < labels.shape[1] else 0
end_component = labels[end[1], end[0]] if 0 <= end[1] < labels.shape[0] and 0 <= end[0] < labels.shape[1] else 0

print(f"\nSTART {start} está en componente: {start_component}")
print(f"END {end} está en componente: {end_component}")

if start_component == end_component and start_component > 0:
    print("\n[OK] START y END estan en el MISMO componente - Path posible")
elif start_component == 0 or end_component == 0:
    print("\n[ERROR] START o END estan FUERA de la mascara!")
else:
    print(f"\n[ERROR] START y END estan en COMPONENTES DIFERENTES!")
    print(f"   Componente START: {start_component}")
    print(f"   Componente END: {end_component}")
    print(f"   No es posible llegar sin saltar entre componentes!")

# Visualizar componentes con colores
vis = np.zeros((mask.shape[0], mask.shape[1], 3), dtype=np.uint8)

# Colores para cada componente
colors = [
    (0, 0, 0),       # Background
    (255, 0, 0),     # Componente 1 - ROJO
    (0, 255, 0),     # Componente 2 - VERDE
    (0, 0, 255),     # Componente 3 - AZUL
    (255, 255, 0),   # Componente 4 - AMARILLO
    (255, 0, 255),   # Componente 5 - MAGENTA
]

for i in range(num_components):
    if i < len(colors):
        vis[labels == i] = colors[i]

# Marcar START y END
cv2.circle(vis, start, 20, (255, 255, 255), 3)
cv2.circle(vis, start, 10, (0, 255, 255), -1)
cv2.putText(vis, "START", (start[0] - 50, start[1] - 25),
           cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2)

cv2.circle(vis, end, 20, (255, 255, 255), 3)
cv2.circle(vis, end, 10, (255, 128, 0), -1)
cv2.putText(vis, "END", (end[0] - 40, end[1] - 25),
           cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2)

# Mostrar tamaños de componentes
print(f"\nTamaños de componentes:")
for i in range(1, num_components):
    size = np.sum(labels == i)
    print(f"  Componente {i}: {size} px")

# Guardar y mostrar
output_path = 'data/results/debug/components_debug.png'
plt.figure(figsize=(16, 14))
plt.imshow(vis)
plt.title(f"Componentes Detectados: {num_components - 1} | "
         f"START en comp {start_component}, END en comp {end_component}",
         fontsize=14, weight='bold')
plt.axis('off')
plt.tight_layout()
plt.savefig(output_path, dpi=150, bbox_inches='tight')
print(f"\n[OK] Debug guardado: {output_path}")
plt.show()
