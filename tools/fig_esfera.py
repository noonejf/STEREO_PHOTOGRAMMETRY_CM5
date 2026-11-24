#!/usr/bin/env python3
"""Las figuras de la esfera del sol: el mapa y los perfiles.

    python tools/fig_esfera.py --csv SIMULATION/experimentos/sol_esfera/medidas.csv
    python tools/fig_esfera.py --idioma en      # las del entregable

Dos figuras, y la primera es la que contesta la pregunta que el anillo no
podia contestar.

``fig_esfera_mapa.png``: dos mapas de azimut por inclinacion, contraste y
cable ciego. En un mapa asi se ve de un golpe si la inclinacion manda o no:
si las filas fueran todas iguales, el barrido de azimut ya bastaba.

``fig_esfera_perfiles.png``: el contraste contra el azimut, una curva por
inclinacion, con la curva de inclinacion cero marcada porque es el barrido
que ya estaba medido y publicado.

Los dos ejes van en el convenio de ``build_sun`` y no en otro: azimut
creciendo de 0 a 360 girando alrededor del eje del cable, inclinacion con
signo, positiva cuando el sol esta del lado del extremo lejano.
"""
from __future__ import annotations

import argparse
import csv
import os
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import idioma as I  # noqa: E402


def leer(ruta):
    filas = []
    with open(ruta, newline="", encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            filas.append(dict(
                az=float(r["azimut_deg"]), inc=float(r["inclinacion_deg"]),
                contraste=float(r["contraste"]),
                ciego=float(r["ciego_pct"]),
                lejos=float(r["contraste_lejos"] or "nan")))
    return filas


def rejilla(filas, campo, azs, incs):
    m = np.full((len(incs), len(azs)), np.nan)
    por = {(f["az"], f["inc"]): f for f in filas}
    for i, inc in enumerate(incs):
        for j, az in enumerate(azs):
            f = por.get((az, inc))
            if f is not None:
                m[i, j] = f[campo]
    return m


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", default=os.path.join(
        "SIMULATION", "experimentos", "sol_esfera", "medidas.csv"))
    ap.add_argument("--dest", default=os.path.join(
        "SIMULATION", "experimentos", "sol_esfera"))
    ap.add_argument("--idioma", default="es", choices=("es", "en"))
    args = ap.parse_args()
    I.usar(args.idioma)

    filas = leer(os.path.join(ROOT, args.csv))
    # Los polos se dejan fuera de los mapas: a +-89 grados el azimut no
    # significa nada, un solo punto no es una fila de la rejilla, y pintarlo
    # como si lo fuera diria que a esa inclinacion solo se probo un azimut.
    rej = [f for f in filas if abs(f["inc"]) < 85]
    polos = [f for f in filas if abs(f["inc"]) >= 85]
    azs = sorted({f["az"] for f in rej})
    incs = sorted({f["inc"] for f in rej})
    dest = os.path.join(ROOT, args.dest)
    os.makedirs(dest, exist_ok=True)

    # ---------------------------------------------------------------- mapa
    fig, axes = plt.subplots(2, 1, figsize=(11.0, 7.6))
    for ax, campo, titulo, cmap, unidad in (
            (axes[0], "contraste", I.t("Contraste del cordon"),
             "viridis", I.t("niveles de 8 bits")),
            (axes[1], "ciego", I.t("Cable que la mascara no puede segmentar"),
             "magma_r", I.t("% del cable"))):
        m = rejilla(rej, campo, azs, incs)
        im = ax.imshow(m, aspect="auto", origin="lower", cmap=cmap,
                       extent=(azs[0] - 11.25, azs[-1] + 11.25,
                               incs[0] - 15, incs[-1] + 15),
                       interpolation="nearest")
        ax.set_yticks(incs)
        ax.set_xticks(azs[::2])
        ax.set_ylabel(I.t("inclinacion del sol (grados)"))
        ax.set_title(titulo, fontsize=11)
        cb = fig.colorbar(im, ax=ax, pad=0.015)
        cb.set_label(unidad, fontsize=8)
        for i, inc in enumerate(incs):
            for j, az in enumerate(azs):
                if np.isnan(m[i, j]):
                    continue
                ax.text(az, inc, f"{m[i, j]:.0f}", ha="center", va="center",
                        fontsize=7.0,
                        color="white" if (campo == "contraste") ==
                        (m[i, j] < np.nanmean(m)) else "black")
    axes[1].set_xlabel(
        I.t("azimut del sol alrededor del eje del cable (grados)"))
    pie = I.t("Convenio de build_sun: a 0 y 0 el sol viene de arriba, "
              "perpendicular al cable. Inclinacion positiva, el sol esta "
              "del lado del extremo lejano.")
    if polos:
        pie += "\n" + I.t(
            "Los polos quedan fuera del mapa porque alli el azimut no "
            "significa nada: ") + ", ".join(
                I.t("inclinacion {inc} da contraste {c} y {z} % ciego").format(
                    inc=f"{p['inc']:+.0f}", c=f"{p['contraste']:.0f}",
                    z=f"{p['ciego']:.0f}")
                for p in sorted(polos, key=lambda q: q["inc"])) + "."
    fig.text(0.012, 0.012, pie, fontsize=7.2, color="0.3")
    fig.suptitle(I.t("La esfera del sol: 16 azimutes por 5 inclinaciones, "
                     "IMX477 con el 8 mm"), fontsize=12)
    fig.tight_layout(rect=(0, 0.055, 1, 0.965))
    p1 = os.path.join(dest, f"fig_esfera_mapa{I.sufijo()}.png")
    fig.savefig(p1, dpi=150)
    plt.close(fig)

    # ------------------------------------------------------------ perfiles
    fig, axes = plt.subplots(1, 2, figsize=(12.0, 4.6))
    colores = plt.cm.coolwarm(np.linspace(0, 1, len(incs)))
    for ax, campo, etiqueta in (
            (axes[0], "contraste", I.t("contraste del cordon (niveles)")),
            (axes[1], "ciego", I.t("cable ciego (%)"))):
        for c, inc in zip(colores, incs):
            g = sorted([f for f in rej if f["inc"] == inc],
                       key=lambda f: f["az"])
            ancho = 2.6 if inc == 0.0 else 1.3
            ax.plot([f["az"] for f in g], [f[campo] for f in g], "-o",
                    ms=3.4, lw=ancho, color=c,
                    label=I.t("{inc} grados").format(inc=f"{inc:+.0f}") +
                          (I.t(" (el anillo ya medido)") if inc == 0.0
                           else ""))
        ax.set_xlabel(I.t("azimut (grados)"))
        ax.set_ylabel(etiqueta)
        ax.set_xticks(azs[::2])
        ax.grid(alpha=0.25)
    axes[0].legend(fontsize=7.6, title=I.t("inclinacion del sol"),
                   title_fontsize=7.6, loc="lower left", framealpha=0.92)
    fig.suptitle(I.t("El azimut dibuja la forma, la inclinacion la "
                     "desplaza"), fontsize=12)
    fig.tight_layout(rect=(0, 0, 1, 0.94))
    p2 = os.path.join(dest, f"fig_esfera_perfiles{I.sufijo()}.png")
    fig.savefig(p2, dpi=150)
    plt.close(fig)

    print(p1)
    print(p2)
    I.avisar()


if __name__ == "__main__":
    main()
