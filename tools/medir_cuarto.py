"""Mide el cuarto TV2 con las luminarias reales, y comprueba la fotometria.

Dos cosas distintas, y la segunda es la que da confianza en la primera.

**1. La tabla de la familia.** Contraste del cordon, cable ciego, fondo medio
y fraccion de cuadro encendido para cada variante, con el mismo criterio que
`tools/medir_barrido.py` porque importa su `medir` en vez de copiarlo.

**2. Lux recuperados del piso.** El piso de molton es un plano lambertiano de
albedo conocido, asi que de un render lineal se puede volver atras: la
radiancia de un lambertiano es ``L = rho * E / pi``, luego ``E = pi * L /
rho``. Comparar eso contra lo que predice `tools/calculadora_luz.py` cierra
la cadena entera de una vez, de la candela de la ficha a los watts de Blender
al pixel, y es la unica forma de saber si la escena entrega los lux que el
plan dice.

**Se mide el piso y no el cordon, a proposito.** El cordon es un cilindro de
1 mm, o sea subpixel mas alla de unos metros, y el filtro de reconstruccion
de Cycles reparte su flujo segun la orientacion: su pixel de pico no mide la
luz que recibe. Ademas la radiancia integrada a lo ancho de un cilindro
depende del angulo entre la luz y la camara por un factor que hay que
modelar. Un plano no tiene ninguno de los dos problemas.

    python tools/medir_cuarto.py
    python tools/medir_cuarto.py --lux
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import sys

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, os.path.join(ROOT, "SIMULATION"))

import cv2  # noqa: E402
from medir_barrido import medir  # noqa: E402
import calculadora_luz as CL  # noqa: E402

#: Las variantes del cuarto con las luminarias reales, en el orden en que se
#: leen: primero la recomendada, luego sus pares de control.
FAMILIA = ("TV2", "TV2MADERA", "TV2RECTO", "TV2PANEL", "TV2SEIS",
           "TV2TENSO", "TV2COSTADO", "TV2296",
           "TV2HAZ0", "TV2HAZCAM", "TV2HAZLEJOS")


def ultima(variant):
    """La ultima captura COMPLETA de esa variante.

    Se exige el metadata porque la carpeta se crea antes de renderizar: si
    una cola esta corriendo, la mas reciente es la que se esta escribiendo y
    todavia no tiene nada que leer.
    """
    d = [x for x in sorted(glob.glob(os.path.join(
        ROOT, "data", "captures", f"stereo_sim_studio{variant}_2*")))
        if os.path.exists(os.path.join(x, "metadata.json"))]
    return d[-1] if d else None


def lux_del_piso(carpeta, muestras=24):
    """Lux en el piso, medidos del render lineal y predichos por el modelo.

    Devuelve una lista de ``(y_m, lux_medidos, lux_predichos)``. Se recorre
    la columna central de la imagen hacia abajo, que por estar la camara en
    x = 0 mirando a lo largo del cuarto cae sobre la linea ``x = 0`` del
    piso, y se retroproyecta cada pixel al plano ``z = 0``.
    """
    meta = json.load(open(os.path.join(carpeta, "metadata.json"),
                          encoding="utf-8"))
    ruta = os.path.join(carpeta, "left.exr")
    if not os.path.exists(ruta):
        return None, "no hay left.exr, hace falta renderizar con --linear"
    img = cv2.imread(ruta, cv2.IMREAD_UNCHANGED)
    if img is None:
        return None, "cv2 no pudo leer el exr"
    if img.ndim == 3:
        # Luminancia de Rec.709 sobre el EXR, que viene en BGR lineal.
        img = (0.0722 * img[:, :, 0] + 0.7152 * img[:, :, 1]
               + 0.2126 * img[:, :, 2])
    img = img.astype(np.float64)

    piso = meta.get("floor") or {}
    rho = piso.get("albedo")
    fix = meta.get("fixtures")
    if rho is None or not fix:
        return None, "la variante no tiene piso con albedo o no usa fichas"

    H, W = img.shape
    cam = meta["left_camera"]["location_m"]
    px_um = (meta.get("sensor") or {}).get("pixel_um", 1.55)
    fx = meta["optics"]["focal_mm"] / (px_um * 1e-3)
    cx, cy = W / 2.0, H / 2.0

    # Las filas utiles van de un poco por debajo del centro al borde: mas
    # arriba el rayo no corta el piso dentro del cuarto, y el borde inferior
    # es el punto mas cercano que entra en cuadro.
    filas = np.linspace(cy + 420, H - 12, muestras).astype(int)
    tilt = fix["tilt_deg"] if fix["tilt_dir"] == "-y" else -fix["tilt_deg"]

    fuera = []
    for v in filas:
        t = cam[2] * fx / (v - cy)          # distancia hasta el plano z = 0
        y = cam[1] + t
        if not (0.5 < y < 29.5):
            continue
        # Un parche de 9 x 9 alrededor del pixel, mediana: el piso es plano y
        # la mediana se come el ruido de 24 muestras sin tocar el nivel.
        u0, v0 = int(cx), int(v)
        parche = img[max(0, v0 - 4):v0 + 5, max(0, u0 - 4):u0 + 5]
        L = float(np.median(parche))
        medido = np.pi * L / rho
        # Prediccion del mismo modelo que dimensiono la fila, evaluada en el
        # piso (altura 0) y en ese mismo y.
        datos, _p, _c, _tiro = CL.perfil_inclinado(
            fix["spec"], fix["z_m"], 0.0, y, y + 1e-3,
            inclinacion_deg=tilt, pasos=2, onda=False,
            luces_y0=fix["y0_m"], luces_y1=fix["y1_m"])
        fuera.append((y, medido, datos[0][2]))
    return fuera, None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--variants", default=",".join(FAMILIA))
    ap.add_argument("--desde", type=float, default=5.0)
    ap.add_argument("--lux", action="store_true",
                    help="recupera los lux del piso del render lineal y los "
                         "compara contra el modelo fotometrico")
    args = ap.parse_args()

    print(f"\n{'variante':12} {'luminarias':>11} {'kW':>6} {'contraste':>10} "
          f"{'ciego':>7} {'fondo':>7} {'cuadro>10':>10} {'pred peor lx':>13}")
    for v in args.variants.split(","):
        v = v.strip()
        d = ultima(v)
        if d is None:
            print(f"{v:12} sin render")
            continue
        meta = json.load(open(os.path.join(d, "metadata.json"),
                              encoding="utf-8"))
        img = cv2.imread(os.path.join(d, "left.jpg"), cv2.IMREAD_GRAYSCALE)
        r = medir(d, args.desde)
        fix = meta.get("fixtures")
        lamps = meta.get("lamps")
        n = (fix or lamps or {}).get("count", 0)
        kw = (fix or lamps or {}).get("kw_electrical_total", float("nan"))
        pred = (fix or {}).get("predicted") or {}
        peor = pred.get("peor_lx_cara_a_la_luz")
        print(f"{v:12} {n:11d} {kw:6.2f} "
              f"{(r['contraste'] if r else float('nan')):10.1f} "
              f"{(r['ciego_pct'] if r else float('nan')):6.1f}% "
              f"{(img.mean() if img is not None else float('nan')):7.2f} "
              f"{((img > 10).mean() * 100 if img is not None else float('nan')):9.1f}% "
              f"{(f'{peor:,.0f}' if peor else '---'):>13}")

    if not args.lux:
        return
    print("\n  LUX EN EL PISO: medidos del render lineal contra el modelo")
    print("  El piso es lambertiano de albedo conocido, asi que E = pi L / rho.")
    for v in args.variants.split(","):
        v = v.strip()
        d = ultima(v)
        if d is None:
            continue
        datos, err = lux_del_piso(d)
        if datos is None:
            continue
        ys = np.array([a for a, _, _ in datos])
        me = np.array([b for _, b, _ in datos])
        pr = np.array([c for _, _, c in datos])
        ok = pr > 1.0
        razon = me[ok] / pr[ok]
        print(f"\n  {v}: {ok.sum()} puntos de piso entre "
              f"{ys[ok].min():.1f} y {ys[ok].max():.1f} m")
        print(f"  {'y (m)':>8} {'medido lx':>12} {'modelo lx':>12} {'razon':>8}")
        for y, a, b in zip(ys[ok], me[ok], pr[ok]):
            print(f"  {y:8.2f} {a:12,.0f} {b:12,.0f} {a / b:8.2f}")
        print(f"  razon medida/modelo: mediana {np.median(razon):.2f}, "
              f"de {razon.min():.2f} a {razon.max():.2f}")


if __name__ == "__main__":
    main()
