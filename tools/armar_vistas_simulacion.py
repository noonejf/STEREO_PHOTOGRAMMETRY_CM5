#!/usr/bin/env python3
"""Las copias chicas de los renders que la aplicacion usa cuando no hay disco.

    python tools/armar_vistas_simulacion.py
    python tools/armar_vistas_simulacion.py --solo esfera

Escribe ``SIMULATION/experimentos/<experimento>/vistas/``, y **eso si se
versiona**, al reves que casi todo lo derivado de este repositorio. La razon
es concreta: ``data/captures/`` esta en el ``.gitignore``, asi que en un clon
limpio, o en la Raspberry, los renders no existen y la pagina de Simulacion
se quedaria con las cifras y sin una sola imagen. Las medidas sin la imagen
no se pueden auditar: la pregunta que se le hace a un contraste de 0.6 es
"a ver", y para eso hace falta ver.

Pesan 3.7 MB las 224 de la esfera, contra 70 MB de los renders crudos, porque
van a 1000 px de ancho y calidad 78. **Son solo para mirar.** Ninguna medida
sale de ellas: llevan la misma curva de gamma 0.42 que las figuras, aplicada
antes de encoger y no despues, y por tanto dejan de ser proporcionales a la
luz. La aplicacion lo sabe y no vuelve a realzarlas.

Cuando ``data/captures`` SI esta en la maquina, la aplicacion prefiere el
render crudo a resolucion completa y estas copias no se usan.
"""
from __future__ import annotations

import argparse
import csv
import os
import sys

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import cv2                        # noqa: E402
from medir_esfera import recoger  # noqa: E402

#: La misma curva que ``tools/fig_renders.py`` y ``tools/armar_esfera_web.py``.
GAMMA = 0.42
ANCHO = 1000
CALIDAD = 78

ESFERA = os.path.join(ROOT, "SIMULATION", "experimentos", "sol_esfera")
ESTUDIO = os.path.join(ROOT, "SIMULATION", "experimentos",
                       "estudio_luminarias_reales")


def copia(origen: str, destino: str) -> int:
    """Realza, encoge y graba. Devuelve los bytes escritos, 0 si no estaba."""
    img = cv2.imread(origen, cv2.IMREAD_GRAYSCALE)
    if img is None:
        return 0
    tabla = np.clip(((np.arange(256) / 255.0) ** GAMMA) * 255.0,
                    0, 255).astype(np.uint8)
    img = cv2.LUT(img, tabla)
    if img.shape[1] > ANCHO:
        alto = int(round(img.shape[0] * ANCHO / img.shape[1]))
        img = cv2.resize(img, (ANCHO, alto), interpolation=cv2.INTER_AREA)
    os.makedirs(os.path.dirname(destino), exist_ok=True)
    cv2.imwrite(destino, img, [int(cv2.IMWRITE_JPEG_QUALITY), CALIDAD])
    return os.path.getsize(destino)


def nombre_esfera(azimut: float, inclinacion: float,
                  lado: str = "left") -> str:
    """El mismo nombre que usa el visor web, para no inventar un segundo.

    La izquierda se llama como siempre, sin sufijo, porque ese nombre ya esta
    publicado en el visor HTML y en las copias versionadas de antes. La
    derecha se agrega con ``_right``, que es el convenio del estudio.
    """
    base = f"az{azimut:05.1f}_inc{inclinacion:+06.1f}"
    return f"{base}.jpg" if lado == "left" else f"{base}_{lado}.jpg"


def hacer_esfera(variante="SOL") -> int:
    """La esfera, con las dos camaras: las 112 direcciones tienen las dos.

    Las 16 del anillo, que son la fila de inclinacion cero y se renderizaron
    aparte, ya venian con el par. Si alguna faltara, ``copia`` devuelve cero
    y el panel esconde ese lado en vez de dibujar un hueco.
    """
    total = n = 0
    for (az, inc), carpeta in sorted(recoger(variante).items()):
        for lado in ("left", "right"):
            escritos = copia(os.path.join(carpeta, f"{lado}.jpg"),
                             os.path.join(ESFERA, "vistas",
                                          nombre_esfera(az, inc, lado)))
            total += escritos
            n += bool(escritos)
    print(f"esfera: {n} vistas, {total / 1e6:.1f} MB")
    return total


def hacer_estudio() -> int:
    """La familia del TV2, con las dos camaras: aqui si existen las dos."""
    ruta = os.path.join(ESTUDIO, "medidas_familia.csv")
    if not os.path.exists(ruta):
        print("estudio: falta medidas_familia.csv")
        return 0
    total = n = 0
    with open(ruta, encoding="utf-8") as fh:
        for fila in csv.DictReader(fh):
            base = os.path.join(ROOT, "data", "captures", fila["captura"])
            for lado in ("left.jpg", "right.jpg"):
                escritos = copia(
                    os.path.join(base, lado),
                    os.path.join(ESTUDIO, "vistas",
                                 f"{fila['variante']}_{lado}"))
                total += escritos
                n += bool(escritos)
    print(f"estudio: {n} vistas, {total / 1e6:.1f} MB")
    return total


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--solo", default="", help="esfera o estudio")
    args = ap.parse_args()
    total = 0
    if args.solo in ("", "esfera"):
        total += hacer_esfera()
    if args.solo in ("", "estudio"):
        total += hacer_estudio()
    print(f"total {total / 1e6:.1f} MB")


if __name__ == "__main__":
    main()
