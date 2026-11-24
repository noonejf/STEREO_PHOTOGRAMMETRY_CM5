#!/usr/bin/env python3
"""Las figuras de renders del informe TV2: lo que la camara ve en cada caso.

    python tools/fig_renders.py
    python tools/fig_renders.py --idioma en      # las del entregable

Deja tres PNG en ``SIMULATION/experimentos/``, con ``_en`` pegado al nombre
cuando salen en ingles:

    estudio_luminarias_reales/fig_renders_cuarto.png   seis variantes del cuarto
    estudio_luminarias_reales/fig_renders_haz.png      el test de tres vias
    sol_esfera/fig_renders_polos.png                   los dos polos del sol

**Las imagenes van realzadas con ``(v/255)**GAMMA`` y hay que decirlo donde
se vean.** El render esta bien expuesto y aun asi el cordon marca unas
decenas de niveles sobre 255 con el fondo casi en cero, que es contraste de
sobra para el sensor y nada para una pagina impresa. La curva es monotona,
asi que no inventa un pixel ni cambia el orden de dos, pero la copia deja de
ser proporcional a la luz: **ninguna medida sale de estas figuras**. Las
cifras de los titulos salen de ``tools/medir_barrido.medir`` sobre el JPEG
crudo, igual que las tablas.

Y se realza **antes** de encoger, nunca al reves: encoger primero 4056 px a
1000 reparte un cordon de 1.7 px entre tres vecinos y lo borra.
"""
from __future__ import annotations

import argparse
import os
import sys

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt   # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import cv2                        # noqa: E402
import idioma as I                # noqa: E402
from medir_cuarto import ultima   # noqa: E402
from medir_esfera import recoger  # noqa: E402

GAMMA = 0.42
#: el sol deja el cordon mucho mas oscuro que la fila de proyectores
GAMMA_SOL = 0.32
ANCHO = 1000

CUARTO = os.path.join(ROOT, "SIMULATION", "experimentos",
                      "estudio_luminarias_reales")
ESFERA = os.path.join(ROOT, "SIMULATION", "experimentos", "sol_esfera")


def leer(carpeta, ancho=ANCHO, gamma=GAMMA):
    if carpeta is None:
        return None
    img = cv2.imread(os.path.join(carpeta, "left.jpg"), cv2.IMREAD_GRAYSCALE)
    if img is None:
        return None
    v = np.clip((img.astype(np.float32) / 255.0) ** gamma * 255.0, 0, 255)
    h = int(round(v.shape[0] * ancho / v.shape[1]))
    return cv2.resize(v.astype(np.uint8), (ancho, h),
                      interpolation=cv2.INTER_AREA)


def salida(carpeta, nombre):
    return os.path.join(carpeta, nombre + I.sufijo() + ".png")


def rejilla(paneles, filas, cols, destino, pie):
    fig, axes = plt.subplots(filas, cols, figsize=(3.6 * cols, 3.25 * filas),
                             facecolor="white")
    axes = np.atleast_1d(axes).ravel()
    for ax, (img, titulo, sub) in zip(axes, paneles):
        ax.set_facecolor("black")
        if img is not None:
            ax.imshow(img, cmap="gray", vmin=0, vmax=255,
                      interpolation="antialiased")
        ax.set_xticks([])
        ax.set_yticks([])
        ax.set_title(I.t(titulo), fontsize=13, fontweight="bold", pad=4)
        ax.set_xlabel(I.t(sub), fontsize=10.5, labelpad=5)
    for ax in axes[len(paneles):]:
        ax.axis("off")
    fig.text(0.5, 0.012, pie, ha="center", fontsize=9.6, color="#444444")
    fig.tight_layout(rect=(0, 0.035, 1, 1), h_pad=3.2)
    fig.savefig(destino, dpi=160)
    plt.close(fig)
    print(destino, os.path.getsize(destino) // 1024, "kB")


def pie_estandar(gamma=GAMMA):
    return I.t("Camara izquierda, realzada con gamma {g} para poder verse "
               "impresa. Las cifras salen del render crudo, no de estas "
               "copias.").format(g=gamma)


def fig_cuarto():
    v = [("TV2RECTO", "Haz vertical, molton",
          "la recomendada, contraste 92.4"),
         ("TV2", "Haz inclinado 40°, molton",
          "contraste 77.3, luz en una cara que no se ve"),
         ("TV2MADERA", "Haz inclinado 40°, piso de madera",
          "fondo medio 50.2 contra 17.5"),
         ("TV2PANEL", "Doce paneles de 1x1 m",
          "contraste 59.5 con 9.62 kW"),
         ("TV2296", "IMX296 con el 6 mm",
          "contraste 38.4, cordon de 0.58 px a 3 m"),
         ("TV2COSTADO0", "Vista de costado, haz vertical",
          "fondo medio 9.8 niveles")]
    paneles = [(leer(ultima(k)), tit, sub) for k, tit, sub in v]
    rejilla(paneles, 2, 3, salida(CUARTO, "fig_renders_cuarto"),
            pie_estandar())


def fig_haz():
    v = [("TV2HAZ0", "Vertical", "contraste 110.6"),
         ("TV2HAZCAM", "Inclinado 40° hacia las camaras",
          "contraste 89.5"),
         ("TV2HAZLEJOS", "Inclinado 40° hacia el extremo lejano",
          "contraste 86.0")]
    paneles = [(leer(ultima(k)), tit, sub) for k, tit, sub in v]
    rejilla(paneles, 1, 3, salida(CUARTO, "fig_renders_haz"),
            I.t("Cable corrido a y = 5.0 m para que las tres quepan en la "
                "misma sala. ") + pie_estandar())


def fig_polos():
    d = recoger("SOL")
    v = [((0.0, -89.0), "Sol detras de las camaras",
          "inclinacion -89°. Contraste 26.0, cable ciego 11.7 %"),
         ((0.0, 0.0), "Sol perpendicular al cable",
          "inclinacion 0°. Contraste 36.1, cable ciego 16.4 %"),
         ((0.0, 89.0), "Sol al final del cable",
          "inclinacion +89°. Contraste 0.6, cable ciego 82.1 %")]
    paneles = [(leer(d.get(k), gamma=GAMMA_SOL), tit, sub)
               for k, tit, sub in v]
    rejilla(paneles, 1, 3, salida(ESFERA, "fig_renders_polos"),
            I.t("Azimut 0 en las tres. Camara izquierda, realzada con gamma "
                "{g}, mas fuerte que la del cuarto porque el sol deja el "
                "cable mas oscuro. Las cifras salen del render crudo."
                ).format(g=GAMMA_SOL))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--solo", default="")
    ap.add_argument("--idioma", default="es", choices=("es", "en"))
    args = ap.parse_args()
    I.usar(args.idioma)
    todo = dict(cuarto=fig_cuarto, haz=fig_haz, polos=fig_polos)
    for k, f in todo.items():
        if not args.solo or k in args.solo.split(","):
            f()
    I.avisar()


if __name__ == "__main__":
    main()
