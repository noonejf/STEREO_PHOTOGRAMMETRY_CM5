"""Prepara las figuras del PDF de posts ISSP.

No inventa ninguna imagen: recorta, escala y superpone lo que ya esta en el
repo. Cada figura dice de donde sale en el PDF.
"""
import io
import os
import sys

import cv2
import numpy as np
from PIL import Image

sys.stdout.reconfigure(encoding="utf-8")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEST = os.path.join(ROOT, "Documentation", "Posts_ISSP", "figures")
os.makedirs(DEST, exist_ok=True)


def guardar(img, nombre, calidad=92):
    ruta = os.path.join(DEST, nombre)
    if nombre.lower().endswith(".jpg"):
        img.convert("RGB").save(ruta, quality=calidad, optimize=True)
    else:
        img.save(ruta, optimize=True)
    print(f"{nombre:28s} {img.size[0]}x{img.size[1]}  "
          f"{os.path.getsize(ruta)/1024:.0f} kB")


def ancho(img, w):
    h = round(img.size[1] * w / img.size[0])
    return img.resize((w, h), Image.LANCZOS)


# --- 1. El soporte de las dos camaras, CAD del entregable D5 --------------
cad = Image.open(os.path.join(
    ROOT, "Documentation", "LINKU_Project_SubDeliverable_D5_CameraSystem_Report__v2_",
    "Images", "Figure 5.2.png")).convert("RGB")
# Recorta el margen blanco: todo lo que no sea casi blanco.
a = np.asarray(cad.convert("L"))
filas = np.where((a < 245).any(axis=1))[0]
cols = np.where((a < 245).any(axis=0))[0]
cad = cad.crop((cols[0], filas[0], cols[-1] + 1, filas[-1] + 1))
guardar(ancho(cad, 1400), "fig_rig.png")

# --- 2. El par estereo real ----------------------------------------------
MD = os.path.join(ROOT, "data", "ai_dataset", "mask_dataset")
izq = Image.open(os.path.join(MD, "images", "0012.jpg")).convert("RGB")
der = Image.open(os.path.join(MD, "images", "0012_right.jpg")).convert("RGB")
guardar(ancho(izq, 1500), "fig_pair_left.jpg")
guardar(ancho(der, 1500), "fig_pair_right.jpg")

# --- 3. Dos trozos del mismo cable, tomados lejos uno del otro ------------
# El argumento del post 2 en una imagen: dos parches de la MISMA foto, a
# cientos de pixeles de distancia a lo largo del cable, y no hay como
# distinguirlos. Los centros salen de la mascara dibujada a mano.
mask = np.asarray(Image.open(os.path.join(MD, "masks", "0012.png")).convert("L"))
ys, xs = np.nonzero(mask > 127)
print(f"mascara: {len(xs)} px de cable en {mask.shape[1]}x{mask.shape[0]}")

LADO = 500          # lado del parche en pixeles de la foto original
SALIDA = 560        # a cuanto se escala para imprimir


def parche(cx, cy):
    x0 = int(cx - LADO // 2)
    y0 = int(cy - LADO // 2)
    rec = izq.crop((x0, y0, x0 + LADO, y0 + LADO))
    return rec.resize((SALIDA, SALIDA), Image.LANCZOS)


def limpio(cx, cy):
    """Un parche sirve si dentro de el hay UNA sola hebra y no se sale.

    Una sola hebra es una sola componente conexa en la mascara: con dos, el
    parche cayo en un cruce y deja de ser un trozo cualquiera de cable, que
    es justo lo que la figura quiere ensenar.
    """
    x0, y0 = int(cx - LADO // 2), int(cy - LADO // 2)
    if x0 < 0 or y0 < 0 or x0 + LADO > mask.shape[1] or y0 + LADO > mask.shape[0]:
        return False
    sub = (mask[y0:y0 + LADO, x0:x0 + LADO] > 127).astype(np.uint8)
    if not 0.02 < sub.mean() < 0.30:
        return False
    n, _ = cv2.connectedComponents(sub, connectivity=8)
    return n == 2


orden = np.argsort(ys)
candidatos = [(int(xs[i]), int(ys[i])) for i in orden if limpio(xs[i], ys[i])]
print(f"parches limpios: {len(candidatos)}")
a_x, a_y = candidatos[len(candidatos) // 6]
b_x, b_y = candidatos[-len(candidatos) // 6]
sep = ((a_x - b_x) ** 2 + (a_y - b_y) ** 2) ** 0.5
print(f"parche A en ({a_x},{a_y}), parche B en ({b_x},{b_y}), "
      f"separados {sep:.0f} px")
guardar(parche(a_x, a_y), "fig_patch_a.jpg")
guardar(parche(b_x, b_y), "fig_patch_b.jpg")
io.open(os.path.join(DEST, "parches.txt"), "w", encoding="utf-8").write(
    f"A=({a_x},{a_y}) B=({b_x},{b_y}) separacion={sep:.0f} px "
    f"lado={LADO} px sobre 0012.jpg\n")

# --- 4. La mascara sobre la foto -----------------------------------------
# El cable marcado en naranja sobre la foto, a la mitad de tamano para que
# la linea siga viendose despues de escalar.
base = np.asarray(ancho(izq, 1500)).astype(np.float32)
mk = np.asarray(ancho(Image.open(os.path.join(MD, "masks", "0012.png")).convert("L"),
                      1500)).astype(np.float32) / 255.0
mk = np.clip(mk * 2.2, 0, 1)[..., None]       # la linea es finisima al escalar
color = np.array([255.0, 140.0, 40.0])
sobre = base * (1 - mk) + color * mk
guardar(Image.fromarray(sobre.astype(np.uint8)), "fig_mask_overlay.jpg")

# --- 5. El estudio simulado, haz vertical contra haz inclinado 60 --------
VIS = os.path.join(ROOT, "SIMULATION", "experimentos",
                   "estudio_luminarias_reales", "vistas")
for origen, nombre in (("tilt000.0_left.jpg", "fig_studio_vertical.jpg"),
                       ("tilt060.0_left.jpg", "fig_studio_tilt60.jpg")):
    guardar(Image.open(os.path.join(VIS, origen)).convert("RGB"), nombre)

print("listo")
