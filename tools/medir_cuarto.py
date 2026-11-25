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
import csv
import glob
import json
import os
import re
import sys

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, os.path.join(ROOT, "SIMULATION"))

# **Antes de importar cv2**, no despues. La rueda de opencv-python se publica
# con el codec de OpenEXR desactivado, y la variable se lee una sola vez al
# inicializar el modulo: puesta despues del import, la lectura del EXR falla
# con "OpenEXR codec is disabled" y el error no dice que llego tarde.
os.environ.setdefault("OPENCV_IO_ENABLE_OPENEXR", "1")

import cv2  # noqa: E402
from medir_barrido import medir  # noqa: E402
import calculadora_luz as CL  # noqa: E402

#: Las variantes del cuarto con las luminarias reales, en el orden en que se
#: leen: primero la recomendada, luego sus pares de control.
FAMILIA = ("TV2", "TV2MADERA", "TV2RECTO", "TV2PANEL", "TV2SEIS",
           "TV2TENSO", "TV2COSTADO", "TV2296",
           "TV2HAZ0", "TV2HAZCAM", "TV2HAZLEJOS")


def ultima(variant, archivo="left.jpg"):
    """La ultima captura COMPLETA de esa variante que tenga ``archivo``.

    Dos razones para exigir el archivo y no solo la carpeta. El metadata se
    escribe al final, asi que mientras una cola corre la carpeta mas reciente
    existe y esta vacia. Y la misma variante se renderiza dos veces, en JPEG
    para mirarla y en EXR lineal para medir lux, asi que "la ultima" depende
    de para que se pide: pedir la de los lux y recibir la del JPEG, o al
    contrario, es un fallo silencioso.
    """
    d = [x for x in sorted(glob.glob(os.path.join(
        ROOT, "data", "captures", f"stereo_sim_studio{variant}_2*")))
        if os.path.exists(os.path.join(x, "metadata.json"))
        and os.path.exists(os.path.join(x, archivo))]
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
        # **Dos conversiones, no una.** El EXR lleva radiancia radiometrica,
        # W/m2/sr, asi que de un lambertiano se saca la irradiancia con
        # ``E_W = pi L / rho`` y de ahi a lux hay que multiplicar por la
        # eficacia luminosa del espectro, los 97.58 lm/W que el proyecto
        # deriva de su propio par AM0. Sin ese factor la razon
        # medido/modelo sale 0.01, que es 1/97.58 y no un fallo de la
        # escena: fue exactamente lo que salio la primera vez.
        medido = np.pi * L / rho * CL.S.LER
        # Prediccion del mismo modelo que dimensiono la fila, evaluada en el
        # piso (altura 0) y en ese mismo y.
        datos, _p, _c, _tiro = CL.perfil_inclinado(
            fix["spec"], fix["z_m"], 0.0, y, y + 1e-3,
            inclinacion_deg=tilt, pasos=2, onda=False,
            luces_y0=fix["y0_m"], luces_y1=fix["y1_m"])
        fuera.append((y, medido, datos[0][2]))
    return fuera, None


def luminarias_en_cuadro(img):
    """Cuantas manchas quemadas hay, y cuantos pixeles ocupan.

    Una luminaria apuntando al lente es la unica cosa de esta escena que
    llega a 255: el piso de molton tiene albedo 0.04 y el cordon es
    subpixel. Asi que contar las manchas de 255 cuenta bocas de proyector
    dentro del campo, que es un dato de montaje y no de fotometria: dice a
    partir de que angulo hay que abanderar.

    **Ojo con leer el area como si fuera saturacion real.** El render pasa
    por AgX, que tiene hombro en las altas luces, mientras un sensor corta
    en seco; el area quemada de verdad sera mayor. Lo que esta cuenta mide
    bien es SI la boca esta en cuadro, no cuanto se desborda.
    """
    if img is None:
        return 0, 0
    m = (img == 255).astype("uint8")
    total = int(m.sum())
    if not total:
        return 0, 0
    n, _, _, _ = cv2.connectedComponentsWithStats(m, 8)
    return n - 1, total


def escribir(ruta, filas):
    with open(ruta, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(filas[0].keys()))
        w.writeheader()
        for f in filas:
            w.writerow(f)
    print(f"  {ruta}  ({len(filas)} filas)")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--variants", default=",".join(FAMILIA))
    ap.add_argument("--desde", type=float, default=5.0)
    ap.add_argument("--lux", action="store_true",
                    help="recupera los lux del piso del render lineal y los "
                         "compara contra el modelo fotometrico")
    ap.add_argument("--csv-dir", dest="csv_dir", default=None,
                    help="escribe las tres tablas: la familia, el barrido de "
                         "inclinacion de las luminarias y los lux del piso")
    args = ap.parse_args()
    filas_familia = []

    print(f"\n{'variante':12} {'lum':>4} {'kW':>6} {'todo el':>8} "
          f"{'fondo':>8} {'ciego':>7} {'fondo':>7} {'detras':>7} "
          f"{'cuadro>10':>10} {'pred peor':>10}")
    print(f"{'':12} {'':4} {'':6} {'cable':>8} {'oscuro':>8} {'':7} "
          f"{'medio':>7} {'del hilo':>7} {'':10} {'lx':>10}")
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
        filas_familia.append(dict(
            variante=v, luminarias=n, kw=kw, tipo=(
                "proyectores reales de ficha" if fix else
                "paneles de 1x1 m supuestos"),
            contraste_fondo_oscuro=None if r is None else
            round(r["contraste"], 2),
            contraste_todo_el_cable=None if r is None else
            round(r["contraste_todo"], 2),
            fondo_detras_del_hilo=None if r is None else
            round(r["fondo_detras_mediano"], 2),
            ciego_pct=None if r is None else round(r["ciego_pct"], 2),
            fondo_medio=None if img is None else round(float(img.mean()), 3),
            cuadro_sobre_10_pct=None if img is None else
            round(float((img > 10).mean() * 100), 3),
            piso=(meta.get("floor") or {}).get("covering"),
            albedo_piso=(meta.get("floor") or {}).get("albedo"),
            inclinacion_deg=(fix or lamps or {}).get("tilt_deg"),
            direccion_haz=(fix or lamps or {}).get("tilt_dir"),
            vista=meta.get("view"), sensor=(meta.get("sensor") or {}).get("name"),
            focal_mm=meta["optics"]["focal_mm"],
            cable_m=meta["cord"]["length_m"], cable_z_m=meta["cord"]["z_m"],
            pred_peor_lx=peor,
            pred_uniformidad=pred.get("uniformidad_peor_sobre_mejor"),
            captura=os.path.basename(d)))
        print(f"{v:12} {n:4d} {kw:6.2f} "
              f"{(r['contraste_todo'] if r else float('nan')):8.1f} "
              f"{(r['contraste'] if r else float('nan')):8.1f} "
              f"{(r['ciego_pct'] if r else float('nan')):6.1f}% "
              f"{(img.mean() if img is not None else float('nan')):7.2f} "
              f"{(r['fondo_detras_mediano'] if r else float('nan')):7.1f} "
              f"{((img > 10).mean() * 100 if img is not None else float('nan')):9.1f}% "
              f"{(f'{peor:,.0f}' if peor else '---'):>10}")

    if args.csv_dir:
        dcsv = os.path.join(ROOT, args.csv_dir)
        os.makedirs(dcsv, exist_ok=True)
        escribir(os.path.join(dcsv, "medidas_familia.csv"), filas_familia)

        # El barrido de inclinacion de las luminarias vive en carpetas
        # ``..._tiltNNN.N_...``, el mismo formato que el roll y el sol, asi
        # que se leen con la misma expresion.
        #
        # **Una fila por angulo, y la captura mas reciente.** Un angulo se
        # renderiza mas de una vez: el barrido original salio con una sola
        # camara y se repitio con las dos. Recorrer el glob sin agrupar
        # metia las dos carpetas y daba dos filas del mismo angulo, que la
        # tabla del capitulo 5 habria publicado como si fueran dos medidas.
        # El nombre lleva la fecha al final, asi que ordenar alfabeticamente
        # y quedarse con la ultima es quedarse con la mas nueva.
        por_angulo = {}
        for d in sorted(glob.glob(os.path.join(
                ROOT, "data", "captures", "stereo_sim_studioTV2_tilt*"))):
            m = re.search(r"_tilt(\d+\.\d)_", os.path.basename(d) + "_")
            if not m or not os.path.exists(os.path.join(d, "metadata.json")):
                continue
            por_angulo[float(m.group(1))] = d

        filas_inc = []
        for grados, d in sorted(por_angulo.items()):
            r = medir(d, args.desde)
            img = cv2.imread(os.path.join(d, "left.jpg"), cv2.IMREAD_GRAYSCALE)
            if r is None:
                continue
            n_lum, px_lum = luminarias_en_cuadro(img)
            filas_inc.append(dict(
                inclinacion_deg=grados,
                contraste=round(r["contraste"], 2),
                ciego_pct=round(r["ciego_pct"], 2),
                sobre_lampara_pct=round(r["sobre_lampara_pct"], 2),
                fondo_medio=None if img is None else round(float(img.mean()), 3),
                camaras=2 if os.path.exists(
                    os.path.join(d, "right.jpg")) else 1,
                luminarias_en_cuadro=n_lum,
                px_quemados=px_lum,
                captura=os.path.basename(d)))
        if filas_inc:
            escribir(os.path.join(dcsv, "medidas_inclinacion.csv"), filas_inc)

        filas_lux = []
        for v in args.variants.split(","):
            d = ultima(v.strip(), "left.exr")
            if d is None:
                continue
            pares, _err = lux_del_piso(d)
            if not pares:
                continue
            for y, me, pr in pares:
                filas_lux.append(dict(
                    variante=v.strip(), y_m=round(y, 3),
                    lux_medidos=round(me, 1), lux_modelo=round(pr, 1),
                    razon=round(me / pr, 4) if pr > 1.0 else None))
        if filas_lux:
            escribir(os.path.join(dcsv, "medidas_lux_piso.csv"), filas_lux)
        print(f"\ntablas escritas en {dcsv}")

    if not args.lux:
        return
    print("\n  LUX EN EL PISO: medidos del render lineal contra el modelo")
    print("  El piso es lambertiano de albedo conocido, asi que E = pi L / rho.")
    for v in args.variants.split(","):
        v = v.strip()
        d = ultima(v, "left.exr")
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
