#!/usr/bin/env python3
"""Mide el contraste del cable en un barrido angular, bien.

    python tools/medir_barrido.py --variant SOL --tag sun
    python tools/medir_barrido.py --variant X --tag roll --desde 5.0

Para cada angulo del barrido imprime el contraste del cordon contra su fondo
local, y cuanto del cable queda con una lampara detras.

**Las dos trampas que este archivo existe para no volver a pisar**, las dos
pisadas el 20 de noviembre de 2026 sobre el barrido de roll, donde dieron una
curva de 52 a 87 niveles enteramente falsa:

1. **Los primeros metros de cuerda mandan sobre cualquier promedio.** El cable
   nace en el plano del lente, asi que su arranque ocupa cientos de pixeles y
   lleva flujo 1400 contra los 60 del tramo a 20 m. Por eso ``--desde``, que
   por defecto empieza a los 5 m.
2. **El pico de pixel no mide luz en un cable sub-pixel.** El filtro de
   reconstruccion de Cycles reparte el flujo entre mas vecinos o menos segun
   el angulo con que la linea cruza la reja, asi que el pico cambia sin que
   la luz se haya movido. Aqui se integra el flujo en un corte perpendicular
   al cable y se le resta la mediana de los flancos.

Y una tercera, que no es de medicion sino de lectura: las muestras que caen
sobre una lampara del cuadro traen el brillo de la lampara, no el del cable.
Se cuentan aparte en vez de promediarlas con el resto.

Sigue valiendo que el JPEG pasa por AgX y no es proporcional a la luz. Estos
numeros comparan angulos entre si, que es para lo que sirven. Una medida
fotometrica absoluta sale del EXR lineal, con ``--linear`` en el render.
"""
from __future__ import annotations

import argparse
import csv
import glob
import json
import math
import os
import re
import sys

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "SIMULATION"))

import cv2  # noqa: E402
import build_tv2_studio as S  # noqa: E402

FONDO_LAMPARA = 20.0   # niveles: por encima de esto, detras hay una lampara

#: Niveles de contraste por debajo de los cuales la mascara ya no tiene nada
#: que segmentar. No es un umbral elegido para que salga bonito: 5 niveles de
#: 8 bits sobre el fondo local es el orden del ruido de lectura del propio
#: render a 8 muestras, asi que por debajo de eso el cordon no esta medido,
#: esta supuesto. Se media en un script suelto en el barrido de azimut; vive
#: aqui para que la esfera y el anillo usen el mismo criterio.
UMBRAL_CIEGO = 5.0


def _bilineal(img, u, r):
    x0, y0 = int(np.floor(u)), int(np.floor(r))
    fx, fy = u - x0, r - y0
    return float(img[y0, x0] * (1 - fx) * (1 - fy)
                 + img[y0, x0 + 1] * fx * (1 - fy)
                 + img[y0 + 1, x0] * (1 - fx) * fy
                 + img[y0 + 1, x0 + 1] * fx * fy)


def medir(carpeta, desde_m, lado="left"):
    meta = json.load(open(os.path.join(carpeta, "metadata.json"),
                          encoding="utf-8"))
    img = cv2.imread(os.path.join(carpeta, f"{lado}.jpg"),
                     cv2.IMREAD_GRAYSCALE)
    if img is None:
        return None
    img = img.astype(np.float32)
    c = meta["cord"]
    pts = S.cord_points(c["x_m"], c["z_m"], c["y0_m"], c["y1_m"], 20001,
                        wave=c.get("wave_modes_m"))
    cam = np.array(meta[f"{lado}_camera"]["location_m"])
    px_um = (meta.get("sensor") or {}).get("pixel_um", 1.55)
    fx = meta["optics"]["focal_mm"] / (px_um * 1e-3)
    roll = math.radians(meta.get("roll_deg", 0.0))
    der = np.array([math.cos(roll), 0.0, -math.sin(roll)])
    arr = np.array([math.sin(roll), 0.0, math.cos(roll)])
    H, W = img.shape

    uv = []
    for p in pts:
        v = np.array(p) - cam
        d = v[1]
        uv.append(None if d < 0.4 else
                  (W / 2.0 + fx * float(v @ der) / d,
                   H / 2.0 - fx * float(v @ arr) / d))

    ts = np.arange(-12, 12.01, 0.25)
    picos, bases, dist = [], [], []
    for i in range(20, len(uv) - 20, 20):
        if uv[i] is None or uv[i - 10] is None or uv[i + 10] is None:
            continue
        d = float(pts[i][1] - cam[1])
        u, r = uv[i]
        if not (16 <= u < W - 17 and 16 <= r < H - 17):
            continue
        du = uv[i + 10][0] - uv[i - 10][0]
        dr = uv[i + 10][1] - uv[i - 10][1]
        n = math.hypot(du, dr)
        if n < 1e-6:
            continue
        pu, pr = -dr / n, du / n
        corte = np.array([_bilineal(img, u + pu * t, r + pr * t) for t in ts])
        base = float(np.median(np.concatenate([corte[:12], corte[-12:]])))
        picos.append(float(corte.max() - base))
        bases.append(base)
        dist.append(d)

    if not picos:
        return None
    picos = np.array(picos)
    bases = np.array(bases)
    dist = np.array(dist)
    sobre = bases > FONDO_LAMPARA

    # **Las dos medidas no se toman sobre el mismo tramo, y es a proposito.**
    #
    # El contraste se promedia desde ``desde_m`` porque el cable nace en el
    # plano del lente: sus primeros dos metros llevan 1400 niveles contra 60
    # a 20 m, asi que dominan cualquier promedio y lo que se mediria es la
    # distancia al cable, no la luz.
    #
    # El cable ciego se cuenta sobre el cable ENTERO, porque la pregunta es
    # que fraccion no se puede segmentar, y el tramo cercano es parte del
    # cable. Si se contara desde 5 m, el tramo ciego que a 270 grados
    # empieza en 0.4 m no existiria, y la fraccion saldria mas alta por
    # quitar del denominador justo las muestras brillantes: a 180 grados,
    # 44.3 % en vez de 35.8 %. Cambiar cualquiera de los dos dominios
    # invalida la comparacion con el barrido de azimut.
    lejos = dist >= desde_m
    limpio = picos[(~sobre) & lejos]
    ciego = (~sobre) & (picos < UMBRAL_CIEGO)
    n_limpio = int((~sobre).sum())
    return dict(
        contraste=float(limpio.mean()) if limpio.size else float("nan"),
        contraste_lejos=float(picos[(~sobre) & (dist > 18)].mean())
        if ((~sobre) & (dist > 18)).any() else float("nan"),
        ciego_pct=float(ciego.sum() / n_limpio * 100.0) if n_limpio else
        float("nan"),
        ciego_desde_m=float(dist[ciego].min()) if ciego.any() else float("nan"),
        ciego_hasta_m=float(dist[ciego].max()) if ciego.any() else float("nan"),
        sobre_lampara_pct=float(sobre.mean() * 100.0),
        tramo_lampara_m=float(dist[sobre].max() - dist[sobre].min())
        if sobre.any() else 0.0,
        muestras=int(picos.size),
        muestras_desde=int(lejos.sum()),
        desde_m=desde_m,
        sensor=(meta.get("sensor") or {}).get("name", "IMX477"),
        focal_mm=meta["optics"]["focal_mm"],
        resolucion=[img.shape[1], img.shape[0]])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--variant", default="SOL")
    ap.add_argument("--tag", default="sun", choices=("roll", "sun"))
    ap.add_argument("--desde", type=float, default=5.0,
                    help="metros desde la camara a partir de los cuales se "
                         "mide: el arranque del cable falsea el promedio")
    ap.add_argument("--csv", default=None)
    args = ap.parse_args()

    patron = os.path.join(ROOT, "data", "captures",
                          f"stereo_sim_studio{args.variant}_{args.tag}*")
    carpetas = {}
    for d in sorted(glob.glob(patron)):
        m = re.search(rf"_{args.tag}(\d+\.\d)_", os.path.basename(d) + "_")
        if m:
            carpetas[float(m.group(1))] = d
    if not carpetas:
        print(f"no hay renders que casen con {os.path.basename(patron)}")
        return

    print(f"{'angulo':>7} {'contraste':>10} {'lejos>18m':>10} "
          f"{'ciego':>7} {'lampara':>8} {'tramo':>7} {'muestras':>9}")
    filas = []
    for ang in sorted(carpetas):
        r = medir(carpetas[ang], args.desde)
        if r is None:
            continue
        print(f"{ang:7.1f} {r['contraste']:10.1f} {r['contraste_lejos']:10.1f}"
              f" {r['ciego_pct']:6.1f}% {r['sobre_lampara_pct']:7.1f}%"
              f" {r['tramo_lampara_m']:6.1f}m {r['muestras']:9d}")
        filas.append(dict(angulo_deg=ang, **r))

    if filas:
        cs = np.array([f["contraste"] for f in filas])
        i_max = int(np.nanargmax(cs))
        i_min = int(np.nanargmin(cs))
        print(f"\n{filas[0]['sensor']} {filas[0]['focal_mm']:.0f} mm, "
              f"{filas[0]['resolucion'][0]} x {filas[0]['resolucion'][1]}")
        print(f"contraste: min {np.nanmin(cs):.1f} a "
              f"{filas[i_min]['angulo_deg']:.1f} grados, "
              f"max {np.nanmax(cs):.1f} a "
              f"{filas[i_max]['angulo_deg']:.1f} grados, "
              f"variacion {(np.nanmax(cs) / np.nanmin(cs) - 1) * 100:.1f}%")

    if args.csv:
        with open(args.csv, "w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=list(filas[0].keys()))
            w.writeheader()
            for f in filas:
                w.writerow(f)
        print(f"escrito {args.csv}")


if __name__ == "__main__":
    main()
