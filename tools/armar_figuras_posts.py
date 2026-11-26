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


D5 = os.path.join(ROOT, "Documentation",
                  "LINKU_Project_SubDeliverable_D5_CameraSystem_Report__v2_",
                  "Images")


def sin_margen(img, umbral=245):
    """Recorta el marco blanco de una figura de entregable."""
    a = np.asarray(img.convert("L"))
    filas = np.where((a < umbral).any(axis=1))[0]
    cols = np.where((a < umbral).any(axis=0))[0]
    return img.crop((cols[0], filas[0], cols[-1] + 1, filas[-1] + 1))


# --- 1. El soporte de las dos camaras, CAD del entregable D5 --------------
cad = Image.open(os.path.join(D5, "Figure 5.2.png")).convert("RGB")
guardar(ancho(sin_margen(cad), 1400), "fig_rig.png")

# --- 1b. El diagrama del instrumento, que es lo que va en el post 1 -------
# La Figure 5.3 del D5: las dos camaras, el CM5, el almacenamiento y lo que
# pasa despues en tierra. Trae la base de 100 mm y el campo de vision, que
# son los dos numeros que el post deja fuera: si Jose no los quiere, se
# recorta la caja central.
hw = Image.open(os.path.join(D5, "Figure 5.3.png")).convert("RGB")
guardar(ancho(sin_margen(hw), 1700), "fig_hw.png")

# --- 1c. Por que un cable rompe la fotogrametria, Figure 2.2 del D5 -------
# Solo las tres primeras columnas: objeto con textura, estructura de alambre
# y el caso del tether. La cuarta es un resumen en texto y la leyenda de
# abajo se queda fuera del recorte, asi que el pie tiene que decir que
# significan el verde y el rojo.
por = Image.open(os.path.join(D5, "Figure 2.2.png")).convert("RGB")
w0, h0 = por.size
guardar(ancho(por.crop((0, 0, int(w0 * 0.737), int(h0 * 0.935))), 1600),
        "fig_why.png")

# --- 1d. La cadena de medida de punta a punta, Figure 6.11 del D5 --------
pip = Image.open(os.path.join(D5, "Figure 6.11.png")).convert("RGB")
guardar(ancho(sin_margen(pip), 1700), "fig_pipeline.png")

# --- 1e. Seis escenas sinteticas de entrenamiento ------------------------
# De data/synthetic, que NO esta versionado: si falta, se regenera con
# synthetic/. Se eligen a mano seis que cubran lo que el generador hace,
# del cable liso al enredo con cruces.
SYN = os.path.join(ROOT, "data", "synthetic", "mask", "images")
elegidas = ("000001", "000025", "000007", "000013", "000101", "000222")
if all(os.path.exists(os.path.join(SYN, f"{n}.jpg")) for n in elegidas):
    cel_w, hueco = 520, 8
    trozos = [ancho(Image.open(os.path.join(SYN, f"{n}.jpg")).convert("RGB"),
                    cel_w) for n in elegidas]
    cel_h = trozos[0].size[1]
    hoja = Image.new("RGB", (3 * cel_w + 2 * hueco, 2 * cel_h + hueco),
                     (255, 255, 255))
    for k, t in enumerate(trozos):
        hoja.paste(t, ((k % 3) * (cel_w + hueco), (k // 3) * (cel_h + hueco)))
    guardar(hoja, "fig_synthetic.jpg")
    fila = Image.new("RGB", (3 * cel_w + 2 * hueco, cel_h), (255, 255, 255))
    for k in (0, 2, 4):
        fila.paste(trozos[k], ((k // 2) * (cel_w + hueco), 0))
    guardar(fila, "fig_synthetic_row.jpg")
else:
    print("AVISO: falta data/synthetic, no se arma fig_synthetic.jpg")

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
pa, pb = parche(a_x, a_y), parche(b_x, b_y)
guardar(pa, "fig_patch_a.jpg")
guardar(pb, "fig_patch_b.jpg")
# Y los dos pegados: el PDF los maqueta mejor como una figura sola, aunque en
# el post puedan ir como dos imagenes.
par = Image.new("RGB", (2 * SALIDA + 10, SALIDA), (255, 255, 255))
par.paste(pa, (0, 0))
par.paste(pb, (SALIDA + 10, 0))
guardar(par, "fig_patches.jpg")
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
estudio = []
for origen, nombre in (("tilt000.0_left.jpg", "fig_studio_vertical.jpg"),
                       ("tilt060.0_left.jpg", "fig_studio_tilt60.jpg")):
    im = Image.open(os.path.join(VIS, origen)).convert("RGB")
    estudio.append(im)
    guardar(im, nombre)
w_e, h_e = estudio[0].size
par_e = Image.new("RGB", (2 * w_e + 10, h_e), (255, 255, 255))
par_e.paste(estudio[0], (0, 0))
par_e.paste(estudio[1], (w_e + 10, 0))
guardar(par_e, "fig_studio_pair.jpg")

print("listo")
