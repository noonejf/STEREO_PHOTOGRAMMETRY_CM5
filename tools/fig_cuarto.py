#!/usr/bin/env python3
"""Las figuras del cuarto TV2 con las cinco luminarias reales.

    python tools/fig_cuarto.py
    python tools/fig_cuarto.py --idioma en      # las del entregable

Tres paneles, cada uno contestando una pregunta de la sesion del viernes 11.

**Arriba, los lux a lo largo del cable.** Es el panel que explica por que la
fila es de cinco y no de doce, y por que el cable baja a 1.5 m: un cono de 45
grados tiene una huella, y lo que decide la uniformidad es si las huellas se
tocan. Se dibuja la posicion de cada luminaria, el objetivo de R5 y el piso
propio del IMX477, que son dos lineas distintas y conviene no confundirlas.

**Abajo a la izquierda, a donde apuntarlas.** El test de tres vias medido
sobre los renders: haz vertical contra haz inclinado hacia las camaras
contra haz inclinado lejos de ellas.

**Abajo a la derecha, la tela.** Molton negro contra madera desnuda, con el
fondo medio del cuadro y la fraccion de cuadro encendido, que es la medida de
cuanto fondo claro tiene que pelear la mascara.
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, os.path.join(ROOT, "SIMULATION"))

import cv2  # noqa: E402
import calculadora_luz as CL  # noqa: E402
import idioma as I  # noqa: E402
import build_tv2_studio as S  # noqa: E402
from medir_barrido import medir  # noqa: E402
from medir_cuarto import ultima  # noqa: E402

SPEC5 = "storm1200x:45:4,ls1200d_pro:45:1"
SPEC6 = "storm1200x:45:4,ls1200d_pro:45:2"


def panel_lux(ax, nota_y=-0.33):
    """Los lux a lo largo del cable. Va en la figura de tres paneles y, a
    solas, en la figura del informe: dentro del compuesto el texto sale a
    menos de cuatro puntos cuando LaTeX lo encoge al ancho de la caja, que
    es ilegible, y una figura no se arregla con una nota al pie."""
    casos = (
        (SPEC5, 6.0, 1.5, 2.0, 20.0, 0.0, "5 luminarias a 6.0 m, haz vertical",
         "#1f6fb4", 2.4, "-"),
        (SPEC5, 6.0, 1.5, 2.0, 20.0, 40.0,
         "5 a 6.0 m, haz inclinado 40 grados", "#6aa8dd", 1.7, "-"),
        (SPEC6, 6.25, 1.5, 2.0, 22.0, 0.0,
         "6 a 6.25 m, 20 m de cable", "#2e8b57", 1.7, "--"),
        (SPEC5, 2.0, 1.5, 2.0, 20.0, 0.0,
         "5 a solo 0.5 m sobre el cable", "#c0392b", 1.5, "-"),
    )
    peores = []
    for spec, hl, hh, y0, y1, inc, etq, color, lw, ls in casos:
        datos, puestas, _corr, _tiro = CL.perfil_inclinado(
            spec, hl, hh, y0, y1, inclinacion_deg=inc, pasos=500, onda=True)
        ys = [a for a, _, _ in datos]
        es = [max(b, 1.0) for _, b, _ in datos]
        ax.plot(ys, es, ls, lw=lw, color=color,
                label=I.t("{etq}   |   peor punto {v} lx").format(
                    etq=I.t(etq), v=f"{min(es):,.0f}"))
        peores.append(min(es))
        if inc == 0.0 and hl == 6.0 and spec == SPEC5:
            for _m, _r, ya, _yl in puestas:
                ax.plot([ya], [1.4e5], "v", color=color, ms=8, clip_on=False)
    ax.axhline(S.E_R5_SLOW_LX, color="0.2", ls="--", lw=1.3)
    ax.text(21.6, S.E_R5_SLOW_LX * 1.12, "R5: 3600 lx", fontsize=8.2,
            color="0.2", ha="right")
    ax.axhline(S.E_IMX477_FLOOR_LX, color="0.45", ls=":", lw=1.3)
    ax.text(21.6, S.E_IMX477_FLOOR_LX * 0.62,
            I.t("piso propio del IMX477: 2320 lx"), fontsize=8.2,
            color="0.45", ha="right")
    ax.set_yscale("log")
    ax.set_ylim(1.0, 2.2e5)
    ax.set_xlim(1.5, 22.5)
    ax.set_xlabel(I.t("posicion a lo largo del cable "
                      "(m desde la pared de las camaras)"))
    ax.set_ylabel(I.t("iluminancia en el cable,\ncara a la luz (lx)"))
    ax.set_title(I.t("Lo que decide la fila no es la potencia, es si las "
                     "huellas de los conos se tocan"), fontsize=11)
    ax.grid(alpha=0.2, which="major")
    ax.legend(fontsize=8.0, loc="lower center", ncol=2, framealpha=0.95,
              borderpad=0.5)
    ax.text(0.0, nota_y,
            I.t("Los triangulos son las cinco luminarias de la fila "
                "recomendada. Modelo de fuente puntual con perfil cos^n, "
                "sin rebotes de pared ni perdidas por suciedad:\nel render "
                "de Cycles entrega un 30 % mas, medido recuperando los lux "
                "del piso de molton. La cuarta curva no es una propuesta, "
                "es el control que muestra el hueco."),
            transform=ax.transAxes, fontsize=7.4, color="0.4", va="top")



def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dest", default=os.path.join(
        "SIMULATION", "experimentos", "estudio_luminarias_reales"))
    ap.add_argument("--idioma", default="es", choices=("es", "en"))
    args = ap.parse_args()
    I.usar(args.idioma)
    dest = os.path.join(ROOT, args.dest)
    os.makedirs(dest, exist_ok=True)

    fig = plt.figure(figsize=(12.6, 9.2))
    gs = fig.add_gridspec(2, 2, height_ratios=(1.15, 1.0), hspace=0.62,
                          wspace=0.26)

    panel_lux(fig.add_subplot(gs[0, :]))

    # --------------------------------- abajo izquierda: a donde apuntarlas
    ax = fig.add_subplot(gs[1, 0])
    import csv as _csv
    incs, cons = [], []
    ruta = os.path.join(dest, "medidas_inclinacion.csv")
    if os.path.exists(ruta):
        with open(ruta, newline="", encoding="utf-8") as fh:
            for r in _csv.DictReader(fh):
                incs.append(float(r["inclinacion_deg"]))
                cons.append(float(r["contraste"]))
    if incs:
        o = np.argsort(incs)
        incs = np.array(incs)[o]
        cons = np.array(cons)[o]
        ax.plot(incs, cons, "-o", color="#1f6fb4", lw=2.2, ms=6,
                label=I.t("barrido de inclinacion"))
        for x, y in zip(incs, cons):
            ax.annotate(f"{y:.0f}", (x, y), textcoords="offset points",
                        xytext=(7, 7), ha="left", fontsize=8, color="#1f6fb4")
    primero = True
    for v, x, mk in (("TV2HAZ0", 0.0, "o"), ("TV2HAZCAM", 40.0, "s"),
                     ("TV2HAZLEJOS", 40.0, "D")):
        d = ultima(v)
        if d is None:
            continue
        r = medir(d, 5.0)
        if r is None:
            continue
        ax.plot([x], [r["contraste"]], mk, color="#c0392b", ms=8,
                label=I.t("test de tres vias, cable corrido")
                if primero else None)
        primero = False
    ax.set_xlabel(I.t("inclinacion del haz (grados desde la vertical)"))
    ax.set_ylabel(I.t("contraste del cordon (niveles)"))
    ax.set_title(I.t("Inclinar cuesta contraste, y no es poco"),
                 fontsize=10.5)
    ax.set_xlim(-6, 70)
    ax.grid(alpha=0.22)
    ax.legend(fontsize=7.6, loc="lower left")
    ax.text(0.985, 0.995,
            I.t("De un cilindro visto casi de punta la camara ve\n"
                "el limbo, cuyas normales apuntan en x y en z.\n"
                "El haz vertical ilumina justamente una de ellas."),
            transform=ax.transAxes, ha="right", va="top", fontsize=7.4,
            color="0.35")

    # ------------------------------------------- abajo derecha: la tela
    ax = fig.add_subplot(gs[1, 1])
    pares = (("TV2", I.t("molton negro\nsobre la madera"), "#2b2b30"),
             ("TV2MADERA", I.t("madera desnuda"), "#b5833f"))
    x = np.arange(len(pares))
    fondos, encendido, etqs2, cols2 = [], [], [], []
    for v, etq, col in pares:
        d = ultima(v)
        if d is None:
            continue
        img = cv2.imread(os.path.join(d, "left.jpg"), cv2.IMREAD_GRAYSCALE)
        if img is None:
            continue
        fondos.append(float(img.mean()))
        encendido.append(float((img > 10).mean() * 100))
        etqs2.append(etq)
        cols2.append(col)
    if fondos:
        x = np.arange(len(fondos))
        ax.bar(x - 0.19, fondos, width=0.36, color=cols2,
               label=I.t("fondo medio del cuadro (niveles)"))
        ax.bar(x + 0.19, encendido, width=0.36, color=cols2, alpha=0.45,
               hatch="//", label=I.t("cuadro sobre 10 niveles (%)"))
        for i, (a, b) in enumerate(zip(fondos, encendido)):
            ax.text(i - 0.19, a + 1.2, f"{a:.1f}", ha="center", fontsize=8.6)
            ax.text(i + 0.19, b + 1.2, f"{b:.1f}%", ha="center", fontsize=8.6)
        ax.set_xticks(x)
        ax.set_xticklabels(etqs2, fontsize=8.4)
        ax.set_ylim(0, max(max(fondos), max(encendido)) * 1.3)
    ax.legend(fontsize=7.6, loc="upper center")
    ax.set_title(I.t("La tela no es una mejora, es una condicion del "
                     "montaje"), fontsize=10.5)
    ax.text(0.5, -0.26,
            I.t("Albedos ASUMIDOS, 0.04 el molton y 0.30 la madera "
                "barnizada: hay que medirlos con el fotometro el dia de la "
                "sesion. Y la madera barnizada no es lambertiana: manda un "
                "reflejo \nespecular que este modelo no reproduce, asi que "
                "0.30 difuso es la version optimista del problema."),
            transform=ax.transAxes, ha="center", va="top", fontsize=7.4,
            color="0.4")
    ax.grid(alpha=0.2, axis="y")

    pares = []
    for v, etq in (("TV2COSTADO0", I.t("vertical")),
                   ("TV2COSTADO", I.t("inclinado 40 grados"))):
        d = ultima(v)
        if d is None:
            continue
        r = medir(d, 5.0)
        img = cv2.imread(os.path.join(d, "left.jpg"), cv2.IMREAD_GRAYSCALE)
        if r is None or img is None:
            continue
        pares.append(I.t("{etq}, cordon {c} y fondo medio {f} con {p} % "
                         "del cuadro encendido").format(
                             etq=etq, c=f"{r['contraste_todo']:.1f}",
                             f=f"{img.mean():.1f}",
                             p=f"{(img > 10).mean() * 100:.0f}"))
    if pares:
        fig.text(0.5, 0.005,
                 I.t("En la vista de COSTADO el cordon empata y lo que "
                     "cambia es el fondo: {pares}. El haz vertical gana en "
                     "las dos vistas.").format(pares="; ".join(pares)),
                 ha="center", fontsize=8.0, color="#1f6fb4")
    fig.suptitle(I.t("El TV2 con las luminarias que el estudio tiene: "
                     "4 STORM 1200x y 1 LS 1200d Pro"), fontsize=13)
    # la misma curva, sola y en un lienzo mas chico: es la que entra al
    # informe, donde \textwidth son 15 cm
    f2, a2 = plt.subplots(figsize=(8.4, 4.6))
    panel_lux(a2, nota_y=-0.17)
    p2 = os.path.join(dest, f"fig_cuarto_lux{I.sufijo()}.png")
    f2.savefig(p2, dpi=170, bbox_inches="tight")
    plt.close(f2)
    print(p2)

    p = os.path.join(dest, f"fig_cuarto_luminarias{I.sufijo()}.png")
    fig.savefig(p, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(p)
    I.avisar()


if __name__ == "__main__":
    main()
