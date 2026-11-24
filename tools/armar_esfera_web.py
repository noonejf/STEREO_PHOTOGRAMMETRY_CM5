#!/usr/bin/env python3
"""Prepara la esfera del sol para el visor: miniaturas realzadas e indice.

    python tools/armar_esfera_web.py
    python tools/armar_esfera_web.py --dest SIMULATION/experimentos/sol_esfera/web

Toma las carpetas de captura que deja ``render_studio_iterations.py`` con
``--sun-orbit`` y ``--sun-tilt`` juntos, y escribe una imagen por direccion
mas un ``indice.json`` con las medidas de cada una. El visor, que es un
artefacto HTML, no lee ``data/captures`` ni calcula nada: lee este indice.

**Las imagenes van realzadas y eso hay que decirlo donde se vean.** El render
esta bien expuesto y aun asi el cordon marca unas decenas de niveles sobre
255 con el fondo en cero, que es contraste de sobra para el sensor y poco
para una pantalla. La curva es ``(v/255)**GAMMA``, monotona, asi que no
inventa nada ni cambia el orden de dos pixeles, pero deja de ser
proporcional a la luz: ninguna medida sale de estas copias. Las medidas del
indice salen de ``tools/medir_barrido.medir`` sobre el JPEG crudo.
"""
from __future__ import annotations

import argparse
import json
import os
import sys

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import cv2  # noqa: E402
from medir_barrido import medir, UMBRAL_CIEGO  # noqa: E402
from medir_esfera import recoger  # noqa: E402

GAMMA = 0.42


def realzar(img):
    return np.clip((img.astype(np.float32) / 255.0) ** GAMMA * 255.0,
                   0, 255).astype(np.uint8)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--variant", default="SOL")
    ap.add_argument("--dest", default=os.path.join(
        "SIMULATION", "experimentos", "sol_esfera", "web"))
    ap.add_argument("--calidad", type=int, default=85)
    ap.add_argument("--ancho", type=int, default=0,
                    help="0 deja la resolucion del render")
    ap.add_argument("--desde", type=float, default=5.0)
    args = ap.parse_args()

    direcciones = recoger(args.variant)
    if not direcciones:
        print("no hay renders de esfera todavia")
        return
    dest = os.path.join(ROOT, args.dest)
    os.makedirs(dest, exist_ok=True)

    entradas = []
    total = 0
    for (az, inc), carpeta in sorted(direcciones.items()):
        cruda = os.path.join(carpeta, "left.jpg")
        img = cv2.imread(cruda, cv2.IMREAD_GRAYSCALE)
        if img is None:
            continue
        r = medir(carpeta, args.desde)
        vista = realzar(img)
        if args.ancho and args.ancho < vista.shape[1]:
            h = int(round(vista.shape[0] * args.ancho / vista.shape[1]))
            vista = cv2.resize(vista, (args.ancho, h),
                               interpolation=cv2.INTER_AREA)
        nombre = f"az{az:05.1f}_inc{inc:+06.1f}.jpg"
        cv2.imwrite(os.path.join(dest, nombre), vista,
                    [int(cv2.IMWRITE_JPEG_QUALITY), args.calidad])
        total += os.path.getsize(os.path.join(dest, nombre))
        entradas.append(dict(
            azimut=az, inclinacion=inc, imagen=nombre,
            ancho=int(vista.shape[1]), alto=int(vista.shape[0]),
            contraste=None if r is None else round(r["contraste"], 2),
            contraste_lejos=None if r is None else
            (None if np.isnan(r["contraste_lejos"]) else
             round(r["contraste_lejos"], 2)),
            ciego_pct=None if r is None else round(r["ciego_pct"], 2),
            ciego_desde_m=None if r is None or np.isnan(r["ciego_desde_m"])
            else round(r["ciego_desde_m"], 1),
            ciego_hasta_m=None if r is None or np.isnan(r["ciego_hasta_m"])
            else round(r["ciego_hasta_m"], 1),
            captura=os.path.basename(carpeta)))

    indice = dict(
        experimento="La esfera de direcciones del sol sobre un cable tendido",
        variante=args.variant,
        gamma_de_las_imagenes=GAMMA,
        aviso=("Las imagenes estan realzadas con una curva de gamma para "
               "poder verse en pantalla. Las medidas salen del render "
               "crudo, no de ellas."),
        umbral_ciego_niveles=UMBRAL_CIEGO,
        contraste_desde_m=args.desde,
        convenio=("El haz viaja en (cos t sin o, -sin t, -cos t cos o), con "
                  "o el azimut y t la inclinacion. A 0 y 0 el sol viene de "
                  "arriba, perpendicular al cable; a 90 de azimut del lado "
                  "-x; a 180 de abajo. La inclinacion tumba el haz a lo "
                  "largo del cable: positiva, el sol esta del lado del "
                  "extremo lejano."),
        azimutes=sorted({e["azimut"] for e in entradas}),
        inclinaciones=sorted({e["inclinacion"] for e in entradas}),
        direcciones=entradas)
    with open(os.path.join(dest, "indice.json"), "w", encoding="utf-8") as fh:
        json.dump(indice, fh, indent=2, ensure_ascii=False)

    print(f"{len(entradas)} direcciones en {dest}")
    print(f"{total / 1e6:.1f} MB de imagenes, "
          f"{total / max(1, len(entradas)) / 1e3:.0f} kB cada una")
    print(f"{len(indice['azimutes'])} azimutes x "
          f"{len(indice['inclinaciones'])} inclinaciones")


if __name__ == "__main__":
    main()
