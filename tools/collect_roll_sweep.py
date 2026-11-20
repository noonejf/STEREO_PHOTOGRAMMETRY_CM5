#!/usr/bin/env python3
"""Junta el barrido de roll en una carpeta de experimento y realza las copias.

    python tools/collect_roll_sweep.py

Lee las carpetas ``data/captures/stereo_sim_studioX_rollNNN.N_*`` que deja
``render_studio_iterations.py --rolls``, y escribe:

    data/results/experimento_roll_360/
        roll_000.0_left.jpg      el render crudo, 4056 x 3040
        roll_000.0_right.jpg
        ...
        realzado/
            roll_000.0_left.jpg  el mismo, con gamma 0.42
            ...
        indice.json              angulos, rutas, y el nivel del cordon

**Las dos versiones estan a resolucion original.** La realzada es solo para
mirar: estira el brillo con ``(v/255)**0.42 * 255``, que es una curva monotona
y no inventa nada, pero deja de ser proporcional a la luz que llego. Cualquier
medida fotometrica sale de la cruda, o mejor del EXR lineal con ``--linear``.

Por que hace falta realzar: el render esta bien expuesto y aun asi el cordon
marca 23 niveles sobre 255 a 8-11 m, con el fondo en 0. Es contraste de sobra
para el sensor y poco para la pantalla, sobre todo si el visor encoge 4056 px
a 600 y reparte un cordon sub-pixel entre siete vecinos.
"""
from __future__ import annotations

import glob
import json
import math
import os
import re
import shutil
import sys

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "SIMULATION"))

import cv2  # noqa: E402
import build_tv2_studio as S  # noqa: E402

DESTINO = os.path.join(ROOT, "data", "results", "experimento_roll_360")
GAMMA = 0.42
FX = 8.0 / 0.00155


def nivel_del_cordon(img, meta):
    """Nivel medio del cordon, muestreado sobre donde la geometria dice.

    El roll gira el mundo respecto al cuadro, asi que el derecho y el arriba
    de la imagen giran con el: proyectar sin rotarlos deja el muestreo fuera
    del cable.
    """
    c = meta["cord"]
    pts = S.cord_points(c["x_m"], c["z_m"], c["y0_m"], c["y1_m"], 20001,
                        wave=c.get("wave_modes_m"))
    cam = np.array(meta["left_camera"]["location_m"])
    roll = math.radians(meta.get("roll_deg", 0.0))
    der = np.array([math.cos(roll), 0.0, -math.sin(roll)])
    arr = np.array([math.sin(roll), 0.0, math.cos(roll)])
    H, W = img.shape[:2]
    vals = []
    for p in pts[::20]:
        v = np.array(p) - cam
        d = v[1]
        if d < 0.4:
            continue
        u = W / 2.0 + FX * float(v @ der) / d
        r = H / 2.0 - FX * float(v @ arr) / d
        if 3 <= u < W - 3 and 3 <= r < H - 3:
            vals.append(int(img[int(r) - 2:int(r) + 3,
                                int(u) - 2:int(u) + 3].max()))
    if not vals:
        return None
    return dict(medio=round(float(np.mean(vals)), 1),
                maximo=int(np.max(vals)), muestras=len(vals))


def main():
    patron = os.path.join(ROOT, "data", "captures",
                          "stereo_sim_studioX_roll*")
    carpetas = {}
    for d in sorted(glob.glob(patron)):
        m = re.search(r"_roll(\d+\.\d)_", os.path.basename(d) + "_")
        if not m or not os.path.exists(os.path.join(d, "left.jpg")):
            continue
        # Si un angulo se renderizo dos veces, gana el mas reciente.
        carpetas[float(m.group(1))] = d
    if not carpetas:
        print("no hay renders del barrido todavia")
        return

    os.makedirs(DESTINO, exist_ok=True)
    realzado = os.path.join(DESTINO, "realzado")
    os.makedirs(realzado, exist_ok=True)

    lut = np.clip(((np.arange(256) / 255.0) ** GAMMA) * 255.0,
                  0, 255).astype(np.uint8)

    indice = []
    for ang in sorted(carpetas):
        d = carpetas[ang]
        meta = json.load(open(os.path.join(d, "metadata.json"),
                              encoding="utf-8"))
        fila = dict(roll_deg=ang, origen=os.path.basename(d), lados={})
        for lado in ("left", "right"):
            src = os.path.join(d, f"{lado}.jpg")
            nombre = f"roll_{ang:05.1f}_{lado}.jpg"
            shutil.copyfile(src, os.path.join(DESTINO, nombre))

            img = cv2.imread(src, cv2.IMREAD_GRAYSCALE)
            cv2.imwrite(os.path.join(realzado, nombre),
                        cv2.LUT(img, lut),
                        [cv2.IMWRITE_JPEG_QUALITY, 88])

            fila["lados"][lado] = dict(
                crudo=nombre,
                realzado=f"realzado/{nombre}",
                resolucion=[img.shape[1], img.shape[0]])
            if lado == "left":
                fila["cordon"] = nivel_del_cordon(img, meta)
        fila["lamparas_visibles"] = bool(
            (meta.get("lamps") or {}).get("visible_to_camera"))
        fila["iluminancia_lx"] = meta.get("illuminance_target_lx")
        indice.append(fila)
        c = fila.get("cordon") or {}
        print(f"  roll {ang:5.1f}  cordon medio {c.get('medio', '-'):>6}  "
              f"max {c.get('maximo', '-'):>4}")

    with open(os.path.join(DESTINO, "indice.json"), "w",
              encoding="utf-8") as fh:
        json.dump(dict(gamma_realzado=GAMMA, angulos=indice), fh,
                  indent=2, ensure_ascii=False)

    n = len(indice)
    peso = sum(os.path.getsize(os.path.join(dp, f))
               for dp, _, fs in os.walk(DESTINO) for f in fs) / 1e6
    print(f"\n{n} angulos, {2*n} cuadros crudos y {2*n} realzados")
    print(f"{DESTINO}  ({peso:.0f} MB)")


if __name__ == "__main__":
    main()
