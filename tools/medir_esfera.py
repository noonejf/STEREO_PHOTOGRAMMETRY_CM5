"""Mide la esfera de direcciones del sol: contraste y cable ciego por direccion.

El barrido de azimut, que `tools/medir_barrido.py` tabula, recorre un circulo
maximo: el haz gira alrededor del eje del cable y la inclinacion se queda en
cero. Eso contesta una pregunta mas estrecha que la real, porque no se sabe
en que direccion va a estar el sol y un circulo no es una esfera.

Este archivo tabula la rejilla completa, azimut por inclinacion, con **el
mismo criterio** que el anillo: importa `medir` de `medir_barrido`, no una
copia. El umbral de cable ciego, los dos dominios de medida y el corte por
lampara detras viven alli y aqui no se redefinen; si se cambian, el anillo y
la esfera cambian juntos, que es la unica forma de poder compararlos.

    python tools/medir_esfera.py
    python tools/medir_esfera.py --csv SIMULATION/experimentos/sol_esfera/medidas.csv

**Convenio de angulos**, el mismo de `build_sun`: el haz viaja en
``(cos t sin o, -sin t, -cos t cos o)``, con ``o`` el azimut y ``t`` la
inclinacion. A azimut 0 e inclinacion 0 el sol viene de arriba, perpendicular
al cable; a 90 de azimut viene del lado -x; a 180 de abajo. La inclinacion
tumba el haz a lo largo del propio cable: positiva, el sol esta del lado del
extremo lejano y el haz viaja hacia las camaras; negativa, al contrario. A
+-89 grados el haz corre casi paralelo al cable y es el caso rasante.
"""
from __future__ import annotations

import argparse
import csv
import glob
import json
import os
import re
import sys

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

from medir_barrido import medir, UMBRAL_CIEGO  # noqa: E402

#: Como se llaman las carpetas que escribe ``render_studio_iterations`` con
#: ``--sun-orbit`` y ``--sun-tilt`` juntos. El azimut lleva cinco cifras con
#: un decimal y la inclinacion va con signo, que es lo que permite ordenarlas
#: sin leer el metadata.
PATRON = re.compile(r"_sun(\d+\.\d)_inc([+-]\d+\.\d)_")


#: El anillo, que es la fila de inclinacion cero de esta misma esfera.
PATRON_ANILLO = re.compile(r"_sun(\d+\.\d)_\d{8}_")


def recoger(variant="SOL", carpeta_base=None, incluir_anillo=True):
    """Todas las direcciones renderizadas, indexadas por (azimut, inclinacion).

    **El anillo ya publicado ES la fila de inclinacion cero**, asi que se
    recoge aqui en vez de renderizarse de nuevo. Sus carpetas no llevan
    ``_inc`` en el nombre porque se hicieron con ``--sun-orbit`` a secas,
    cuando la inclinacion no era todavia un eje del barrido, pero la escena
    es la misma variante con ``tilt`` en cero y los mismos 24 muestras a
    resolucion completa. Reutilizarlo tiene una ventaja sobre repetirlo: la
    fila de cero de la esfera coincide entonces **exactamente** con la tabla
    que ya esta publicada en sol_orbita/RESULTADOS.md, en vez de parecerse.

    Para cada azimut se queda la carpeta mas reciente, que es lo que hace
    falta porque el anillo se renderizo dos veces: una prueba a 25 % de
    escala y la definitiva a resolucion completa. Esa prueba es la que, leida
    por error, devolvio contraste 1.4 en vez de 50.
    """
    base = carpeta_base or os.path.join(ROOT, "data", "captures")
    fuera = {}
    for d in sorted(glob.glob(os.path.join(
            base, f"stereo_sim_studio{variant}_sun*"))):
        nombre = os.path.basename(d) + "_"
        if not os.path.exists(os.path.join(d, "left.jpg")):
            continue
        m = PATRON.search(nombre)
        if m:
            fuera[(float(m.group(1)), float(m.group(2)))] = d
            continue
        if incluir_anillo:
            a = PATRON_ANILLO.search(nombre)
            if a:
                fuera[(float(a.group(1)), 0.0)] = d
    return fuera


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--variant", default="SOL")
    ap.add_argument("--desde", type=float, default=5.0,
                    help="metros desde la camara a partir de los cuales se "
                         "promedia el contraste. El cable ciego se cuenta "
                         "sobre el cable entero, no desde aqui")
    ap.add_argument("--csv", default=None)
    args = ap.parse_args()

    direcciones = recoger(args.variant)
    if not direcciones:
        print(f"no hay renders de esfera para la variante {args.variant}. "
              f"Se generan con:\n"
              f"  blender --background --python "
              f"SIMULATION/render_studio_iterations.py -- --variant SOL \\\n"
              f"          --sun-orbit 0,22.5,...,337.5 "
              f"--sun-tilt -60,-30,0,30,60 --samples 8 --scale 25")
        return

    filas = []
    for (az, inc), d in sorted(direcciones.items()):
        r = medir(d, args.desde)
        if r is None:
            print(f"  sin imagen: {os.path.basename(d)}")
            continue
        filas.append(dict(azimut_deg=az, inclinacion_deg=inc,
                          carpeta=os.path.basename(d), **r))

    azs = sorted({f["azimut_deg"] for f in filas})
    incs = sorted({f["inclinacion_deg"] for f in filas})
    por = {(f["azimut_deg"], f["inclinacion_deg"]): f for f in filas}

    def matriz(titulo, campo, fmt="{:6.1f}"):
        print(f"\n  {titulo}")
        print("  azimut " + "".join(f"{i:>8.0f}" for i in incs))
        for az in azs:
            celdas = ""
            for inc in incs:
                f = por.get((az, inc))
                celdas += ("       ." if f is None
                           else fmt.format(f[campo]).rjust(8))
            print(f"  {az:6.1f} {celdas}")

    print(f"\nESFERA DEL SOL: {len(filas)} direcciones medidas, "
          f"{len(azs)} azimutes x {len(incs)} inclinaciones")
    print(f"contraste promediado desde {args.desde:.1f} m; cable ciego es la "
          f"fraccion del cable entero bajo {UMBRAL_CIEGO:.0f} niveles")
    matriz("CONTRASTE MEDIO, niveles de 8 bits", "contraste")
    matriz("CABLE CIEGO, % del cable", "ciego_pct")
    matriz("CONTRASTE MAS ALLA DE 18 m", "contraste_lejos")

    cs = np.array([f["contraste"] for f in filas])
    ci = np.array([f["ciego_pct"] for f in filas])
    mejor = filas[int(np.nanargmax(cs))]
    peor = filas[int(np.nanargmin(cs))]
    limpio = [f for f in filas if f["ciego_pct"] <= 1.0]
    print(f"\n  contraste: {np.nanmin(cs):.1f} a {np.nanmax(cs):.1f}, "
          f"media {np.nanmean(cs):.1f}")
    print(f"  mejor   azimut {mejor['azimut_deg']:.1f}, inclinacion "
          f"{mejor['inclinacion_deg']:+.1f}: contraste "
          f"{mejor['contraste']:.1f}, ciego {mejor['ciego_pct']:.1f}%")
    print(f"  peor    azimut {peor['azimut_deg']:.1f}, inclinacion "
          f"{peor['inclinacion_deg']:+.1f}: contraste "
          f"{peor['contraste']:.1f}, ciego {peor['ciego_pct']:.1f}%")
    print(f"  cable ciego: {np.nanmin(ci):.1f}% a {np.nanmax(ci):.1f}%, "
          f"media {np.nanmean(ci):.1f}%")
    print(f"  direcciones con el cable entero visible (ciego <= 1%): "
          f"{len(limpio)} de {len(filas)} "
          f"({len(limpio) / len(filas) * 100:.0f}%)")

    # Lo que la esfera contesta y el anillo no: cuanto manda la inclinacion
    # comparada con el azimut. Si la respuesta fuera "nada", el anillo ya
    # bastaba y estas horas de render sobraban.
    print("\n  POR INCLINACION, promediando los azimutes")
    print(f"  {'inclinacion':>12} {'contraste':>10} {'ciego':>8} "
          f"{'direcciones limpias':>20}")
    for inc in incs:
        g = [f for f in filas if f["inclinacion_deg"] == inc]
        c = np.array([f["contraste"] for f in g])
        z = np.array([f["ciego_pct"] for f in g])
        print(f"  {inc:+12.1f} {np.nanmean(c):10.1f} {np.nanmean(z):7.1f}% "
              f"{sum(1 for f in g if f['ciego_pct'] <= 1.0):12d} de {len(g)}")
    print("\n  POR AZIMUT, promediando las inclinaciones")
    print(f"  {'azimut':>12} {'contraste':>10} {'ciego':>8} "
          f"{'direcciones limpias':>20}")
    for az in azs:
        g = [f for f in filas if f["azimut_deg"] == az]
        c = np.array([f["contraste"] for f in g])
        z = np.array([f["ciego_pct"] for f in g])
        print(f"  {az:12.1f} {np.nanmean(c):10.1f} {np.nanmean(z):7.1f}% "
              f"{sum(1 for f in g if f['ciego_pct'] <= 1.0):12d} de {len(g)}")

    if args.csv:
        os.makedirs(os.path.dirname(os.path.abspath(args.csv)), exist_ok=True)
        with open(args.csv, "w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=list(filas[0].keys()))
            w.writeheader()
            for f in filas:
                w.writerow(f)
        print(f"\nescrito {args.csv}")


if __name__ == "__main__":
    main()
