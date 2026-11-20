#!/usr/bin/env python3
"""Junta un barrido angular en una carpeta de experimento y realza las copias.

    python tools/collect_sweep.py                        # el roll del estudio
    python tools/collect_sweep.py --variant SOL --tag sun
    python tools/collect_sweep.py --variant SOL296 --tag sun

Lee las carpetas ``data/captures/stereo_sim_studio<VAR>_<TAG>NNN.N_*`` que deja
``render_studio_iterations.py`` con ``--rolls`` o con ``--sun-orbit``, y escribe:

    data/results/<destino>/
        ang_000.0_left.jpg      el render crudo, a resolucion de captura
        ang_000.0_right.jpg
        ...
        realzado/
            ang_000.0_left.jpg  el mismo, con gamma 0.42
            ...
        indice.json             angulos, rutas, y el nivel del cordon

**Los dos barridos son el mismo experimento por lados opuestos.** Con ``roll``
el cable y las lamparas se quedan quietos y rueda el par de camaras, porque
mover doce lamparas de estudio es caro. Con ``sun`` el instrumento se queda
como va a estar montado y lo que gira es el haz, que con un objeto Sun no
cuesta nada. El primero no puede cambiar la iluminacion del cable, y es por
eso el control; el segundo si, y es por eso la medida.

**Las dos versiones estan a resolucion original.** La realzada es solo para
mirar: estira el brillo con ``(v/255)**0.42 * 255``, que es una curva monotona
y no inventa nada, pero deja de ser proporcional a la luz que llego. Cualquier
medida fotometrica sale de la cruda, o mejor del EXR lineal con ``--linear``.

Por que hace falta realzar: el render esta bien expuesto y aun asi el cordon
marca unas decenas de niveles sobre 255, con el fondo en 0. Es contraste de
sobra para el sensor y poco para la pantalla, sobre todo si el visor encoge
4056 px a 600 y reparte un cordon sub-pixel entre siete vecinos.
"""
from __future__ import annotations

import argparse
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

GAMMA = 0.42


def nivel_del_cordon(img, meta):
    """Nivel medio del cordon, muestreado sobre donde la geometria dice.

    La distancia focal en pixeles sale del metadata y no de una constante:
    el IMX296 tiene pixeles de 3.45 um contra los 1.55 del IMX477, asi que
    fijarla aqui proyectaria el cable fuera de si mismo en cuanto cambia el
    sensor.

    El roll gira el mundo respecto al cuadro, asi que el derecho y el arriba
    de la imagen giran con el. En los barridos de sol el roll es cero y esto
    se reduce a la proyeccion de siempre.
    """
    c = meta["cord"]
    pts = S.cord_points(c["x_m"], c["z_m"], c["y0_m"], c["y1_m"], 20001,
                        wave=c.get("wave_modes_m"))
    cam = np.array(meta["left_camera"]["location_m"])
    px_um = (meta.get("sensor") or {}).get("pixel_um", 1.55)
    fx = meta["optics"]["focal_mm"] / (px_um * 1e-3)
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
        u = W / 2.0 + fx * float(v @ der) / d
        r = H / 2.0 - fx * float(v @ arr) / d
        if 3 <= u < W - 3 and 3 <= r < H - 3:
            vals.append(int(img[int(r) - 2:int(r) + 3,
                                int(u) - 2:int(u) + 3].max()))
    if not vals:
        return None
    return dict(medio=round(float(np.mean(vals)), 1),
                maximo=int(np.max(vals)), muestras=len(vals))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--variant", default="X")
    ap.add_argument("--tag", default="roll", choices=("roll", "sun"))
    ap.add_argument("--dest", default=None,
                    help="nombre de la carpeta en data/results/")
    args = ap.parse_args()

    dest = args.dest or f"experimento_{args.tag}_{args.variant}"
    destino = os.path.join(ROOT, "data", "results", dest)

    patron = os.path.join(ROOT, "data", "captures",
                          f"stereo_sim_studio{args.variant}_{args.tag}*")
    carpetas = {}
    for d in sorted(glob.glob(patron)):
        m = re.search(rf"_{args.tag}(\d+\.\d)_", os.path.basename(d) + "_")
        if not m or not os.path.exists(os.path.join(d, "left.jpg")):
            continue
        # Si un angulo se renderizo dos veces, gana el mas reciente.
        carpetas[float(m.group(1))] = d
    if not carpetas:
        print(f"no hay renders que casen con {os.path.basename(patron)}")
        return

    os.makedirs(destino, exist_ok=True)
    realzado = os.path.join(destino, "realzado")
    os.makedirs(realzado, exist_ok=True)

    lut = np.clip(((np.arange(256) / 255.0) ** GAMMA) * 255.0,
                  0, 255).astype(np.uint8)

    indice = []
    for ang in sorted(carpetas):
        d = carpetas[ang]
        meta = json.load(open(os.path.join(d, "metadata.json"),
                              encoding="utf-8"))
        fila = dict(angulo_deg=ang, tipo=args.tag, variante=args.variant,
                    origen=os.path.basename(d), lados={})
        for lado in ("left", "right"):
            src = os.path.join(d, f"{lado}.jpg")
            if not os.path.exists(src):
                continue
            nombre = f"ang_{ang:05.1f}_{lado}.jpg"
            shutil.copyfile(src, os.path.join(destino, nombre))

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
        sol = meta.get("sun") or {}
        fila["sensor"] = (meta.get("sensor") or {}).get("name")
        fila["focal_mm"] = meta["optics"]["focal_mm"]
        fila["iluminancia_lx"] = (sol.get("illuminance_at_cord_lx")
                                  or meta.get("illuminance_target_lx"))
        fila["lamparas_visibles"] = bool(
            (meta.get("lamps") or {}).get("visible_to_camera"))
        indice.append(fila)
        c = fila.get("cordon") or {}
        print(f"  {args.tag} {ang:5.1f}  cordon medio {c.get('medio', '-'):>6}"
              f"  max {c.get('maximo', '-'):>4}")

    with open(os.path.join(destino, "indice.json"), "w",
              encoding="utf-8") as fh:
        json.dump(dict(gamma_realzado=GAMMA, tipo=args.tag,
                       variante=args.variant, angulos=indice), fh,
                  indent=2, ensure_ascii=False)

    n = len(indice)
    peso = sum(os.path.getsize(os.path.join(dp, f))
               for dp, _, fs in os.walk(destino) for f in fs) / 1e6
    print(f"\n{n} angulos en {destino}  ({peso:.0f} MB)")


if __name__ == "__main__":
    main()
