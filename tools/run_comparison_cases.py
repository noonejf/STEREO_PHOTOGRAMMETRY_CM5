#!/usr/bin/env python3
"""Ensayo en seco de los criterios A3 sobre los casos renderizados.

Los criterios A3.1 a A3.7 estan registrados por adelantado en
``Documentation/LINKU_Experiment_TV2``, capitulo 2, tabla ``tab:crit-pipeline``,
y no se re-derivan aqui: esto los EVALUA, sobre pares sinteticos en los que la
verdad se conoce exactamente. La matriz de casos esta en
``SIMULATION/CASOS_COMPARACION.md``.

    python tools/run_comparison_cases.py
    python tools/run_comparison_cases.py --casos S,W

Por que vale la pena correrlo antes de la sesion:

* **Pone a prueba los criterios, no solo la pipeline.** Si uno resulta
  inmedible o esta mal definido, sale ahora y no en TV2.
* **Mide la brecha estudio contra orbita**, que es lo unico que responde si
  TV2 vale como validacion del caso de vuelo.
* **Aqui la verdad es exacta.** A3.5 compara contra una cinta metrica en la
  sesion; aqui contra el centro del cable que el generador conoce punto a
  punto.

Usa los modulos de la aplicacion sin modificarlos, que es lo que el capitulo
pide ("by running the application unmodified"). No abre la GUI: el tuner se
instancia con QApplication en modo offscreen para que la mascara salga del
mismo codigo que usa el operador.

Lo que este ensayo NO puede responder, y conviene no olvidarlo al leer la
tabla: Cycles no tiene ruido de sensor, no hay luz parasita, no hay deriva
termica y la geometria es exacta en vez de calibrada. Un criterio que falla
aqui va a fallar en TV2; uno que pasa aqui puede fallar igual alla.
"""
from __future__ import annotations

import argparse
import glob
import json
import math
import os
import sys

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "SIMULATION"))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import cv2  # noqa: E402

import build_tv2_studio as S  # noqa: E402
from processing.endpoint_detector import detect_wire_endpoints  # noqa: E402
from processing.wire_metrics import compute_wire_metrics  # noqa: E402


#: La matriz de CASOS_COMPARACION.md. ``recta`` dice si el criterio A3.6 se
#: puede evaluar: sobre un cable ondulado a proposito la rectitud devuelve un
#: numero bajo que no significa nada.
CASOS = [
    ("S",  "1 base estudio",      "estudio", "eje",     False),
    ("W",  "2 orbita",            "orbita",  "eje",     False),
    ("X",  "3 lamparas en cuadro","estudio", "eje",     False),
    ("M",  "4 costado estudio",   "estudio", "costado", False),
    ("C5", "5 costado orbita",    "orbita",  "costado", False),
    ("C6", "6 cable tenso",       "estudio", "eje",     True),
    ("C7", "7 tenso en orbita",   "orbita",  "eje",     True),
    ("C8", "8 onda fuerte",       "estudio", "eje",     False),
]

FX = 8.0 / 0.00155
BASELINE = 0.1
GAMMA = 0.42


def carpeta(variante):
    ds = [p for p in sorted(glob.glob(os.path.join(
            ROOT, "data", "captures", f"stereo_sim_studio{variante}_2026*")))
          if os.path.exists(os.path.join(p, "left.jpg"))]
    return ds[-1] if ds else None


def verdad(meta):
    """El centro del cable que el generador conoce, en 3D y proyectado."""
    c = meta["cord"]
    onda = c.get("wave_modes_m")
    pts = S.cord_points(c["x_m"], c["z_m"], c["y0_m"], c["y1_m"], 20001,
                        wave=onda)
    return pts


def proyecta(pts, vista, W, H, lado, meta):
    """Proyecta la verdad al plano imagen, con la convencion de cada vista.

    La posicion de la camara y la focal salen del ``metadata.json`` del
    render, nunca de constantes aqui. Tenerlas codificadas ya costo una
    tabla entera: el punto medio del cable estaba puesto a 14.25 y la camara
    de los casos de costado esta en 14.50, y esos 25 cm son 107 px sobre un
    cordon de 2 px de ancho, asi que la cobertura salia 0% con la mascara
    funcionando perfectamente.

    La otra trampa es el signo. En modo costado el derecho de la imagen es
    -Y, no +Y: proyectar con el signo contrario espeja las columnas sobre el
    centro y el unico punto que coincide es la columna central.
    """
    cam = meta.get(f"{lado}_camera", {})
    cx, cy, cz = cam.get("location_m", [0.0, 0.0, 0.0])
    fx = (meta.get("optics", {}).get("focal_mm", 8.0)) / 0.00155
    out = []
    for x, y, z in pts:
        if vista == "eje":
            d = y - cy
            u = W / 2.0 + fx * (x - cx) / d if d > 0.4 else None
        else:
            d = x - cx
            u = W / 2.0 + fx * (cy - y) / d if d > 0.4 else None
        if u is None:
            continue
        v = H / 2.0 + fx * (cz - z) / d
        if 0 <= u < W and 0 <= v < H:
            out.append((u, v, d))
    return out


def mascara(tuner, img):
    """La mascara del tuner, con el mismo estiramiento que usaria el operador."""
    tuner.original_img = img
    tuner._gamma = GAMMA
    tuner._prepare_preview()
    tuner.refresh_mask()
    m = tuner.mask_result
    if m is None:
        return None
    if m.shape[:2] != img.shape[:2]:
        m = cv2.resize(m, (img.shape[1], img.shape[0]),
                       interpolation=cv2.INTER_NEAREST)
    return (m > 0).astype(np.uint8)


def una_componente(mb):
    n, _, stats, _ = cv2.connectedComponentsWithStats(mb, 8)
    areas = sorted((stats[i, cv2.CC_STAT_AREA] for i in range(1, n)),
                   reverse=True)
    if not areas:
        return False, 0
    # Un componente suelto de unos pocos pixeles es ruido de umbral, no una
    # segunda hebra: se cuentan los que pesan al menos el 1% del mayor.
    grandes = [a for a in areas if a >= 0.01 * areas[0]]
    return len(grandes) == 1, len(grandes)


def traza(mb, ini, fin):
    from processing import graph_tracer
    try:
        r = graph_tracer.track_wire(mb * 255, ini, fin)
        if r.get("success"):
            return r.get("path", []), "grafo"
    except Exception as e:
        print(f"      grafo fallo: {e}")
    try:
        from processing.smart_wire_tracker import SmartWireTracker
        t = SmartWireTracker(mb * 255, ini, fin)
        r = t.track_wire()
        if r.get("success"):
            return r.get("path", []), "DFS"
    except Exception as e:
        print(f"      DFS fallo: {e}")
    return [], "ninguno"


def arco_verdadero(pts, lo, hi):
    seg = [p for p in pts if lo <= p[1] <= hi]
    if len(seg) < 2:
        return float("nan")
    return sum(math.dist(seg[i], seg[i + 1]) for i in range(len(seg) - 1))


def evalua(variante, nombre, entorno, vista, es_recta, tuner):
    d = carpeta(variante)
    if d is None:
        return dict(caso=nombre, estado="sin render")
    meta = json.load(open(os.path.join(d, "metadata.json"), encoding="utf-8"))
    pts = verdad(meta)
    res = dict(caso=nombre, variante=variante, entorno=entorno, vista=vista,
               carpeta=os.path.basename(d))

    paths = {}
    for lado in ("left", "right"):
        img = cv2.imread(os.path.join(d, f"{lado}.jpg"))
        H, W = img.shape[:2]
        mb = mascara(tuner, img)
        if mb is None or mb.sum() == 0:
            res[f"{lado}_error"] = "sin mascara"
            continue
        uno, n_comp = una_componente(mb)
        res[f"{lado}_A31"] = uno
        res[f"{lado}_componentes"] = n_comp

        # cobertura y precision contra el centro verdadero
        proj = proyecta(pts, vista, W, H, lado, meta)
        dil = cv2.dilate(mb, np.ones((7, 7), np.uint8))
        cub = sum(1 for u, v, _ in proj if dil[int(v), int(u)]) / max(len(proj), 1)
        lienzo = np.zeros((H, W), np.uint8)
        for u, v, _ in proj:
            lienzo[int(v), int(u)] = 1
        cerca = cv2.dilate(lienzo, np.ones((15, 15), np.uint8))
        pre = float((mb * cerca).sum()) / max(int(mb.sum()), 1)
        res[f"{lado}_cobertura"] = cub
        res[f"{lado}_precision"] = pre

        try:
            e1, e2 = detect_wire_endpoints(mb * 255)
            res[f"{lado}_A32"] = e1 is not None and e2 is not None
        except Exception as ex:
            res[f"{lado}_A32"] = False
            res[f"{lado}_endpoints_error"] = str(ex)[:60]
            continue

        path, quien = traza(mb, e1, e2)
        res[f"{lado}_A33"] = len(path) > 1
        res[f"{lado}_trazador"] = quien
        paths[lado] = path

    if len(paths) == 2 and all(len(p) > 1 for p in paths.values()):
        from processing.stereo_processor import StereoProcessor
        sp = StereoProcessor.__new__(StereoProcessor)
        img = cv2.imread(os.path.join(d, "left.jpg"))
        try:
            mr = sp.compute_disparity_from_wire_paths(
                paths["left"], paths["right"], img.shape[:2])
        except Exception as ex:
            res["matching_error"] = str(ex)[:80]
            mr = {"success": False}
        if mr.get("success"):
            calib = dict(focal_length=FX, baseline=BASELINE,
                         cx=img.shape[1] / 2.0, cy=img.shape[0] / 2.0)
            wm = compute_wire_metrics(mr["matches"], mr["disparities"], calib)
            if wm is not None:
                s = wm.summary()
                res["A34_retenido"] = s["retained_fraction"]
                res["arco_m"] = s["total_length_m"]
                res["arco_crudo_m"] = s["total_length_raw_m"]
                res["rectitud"] = s["straightness"]
                # la verdad sobre el tramo que el path realmente cubrio
                proj = proyecta(pts, vista, img.shape[1], img.shape[0], "left", meta)
                if proj:
                    ds = [p[2] for p in proj]
                    c = meta["cord"]
                    if vista == "eje":
                        lo, hi = 2.0 + min(ds), 2.0 + max(ds)
                    else:
                        lo, hi = c["y0_m"], c["y1_m"]
                    av = arco_verdadero(pts, lo, hi)
                    res["arco_verdadero_m"] = av
                    if av == av and av > 0:
                        res["A35_error_pct"] = 100.0 * (s["total_length_m"] - av) / av
    res["A36_aplica"] = es_recta
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--casos", default="",
                    help="lista separada por comas, por defecto todos")
    args = ap.parse_args()
    quiere = [c.strip() for c in args.casos.split(",") if c.strip()]

    from PyQt5.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    from edge_detection_tuner import EdgeDetectionTuner
    tuner = EdgeDetectionTuner()

    filas = []
    for var, nombre, entorno, vista, recta in CASOS:
        if quiere and var not in quiere:
            continue
        print(f"\n=== {nombre}  ({var}, {entorno}, {vista})", flush=True)
        filas.append(evalua(var, nombre, entorno, vista, recta, tuner))

    print("\n\n" + "=" * 100)
    print("CRITERIOS A3 SOBRE LOS CASOS RENDERIZADOS")
    print("=" * 100)
    cab = (f"{'caso':<22}{'A3.1':>6}{'A3.2':>6}{'A3.3':>6}{'A3.4':>8}"
           f"{'A3.5':>10}{'A3.6':>8}{'cobert':>8}{'precis':>8}")
    print(cab)
    print("-" * len(cab))
    for r in filas:
        if r.get("estado"):
            print(f"{r['caso']:<22}{r['estado']}")
            continue
        def si(k):
            a, b = r.get(f"left_{k}"), r.get(f"right_{k}")
            if a is None or b is None:
                return "  ?"
            return " si" if (a and b) else " NO"
        ret = r.get("A34_retenido")
        err = r.get("A35_error_pct")
        rec = r.get("rectitud")
        cob = (r.get("left_cobertura", 0) + r.get("right_cobertura", 0)) / 2
        pre = (r.get("left_precision", 0) + r.get("right_precision", 0)) / 2
        print(f"{r['caso']:<22}{si('A31'):>6}{si('A32'):>6}{si('A33'):>6}"
              f"{(f'{ret*100:.0f}%' if ret is not None else '-'):>8}"
              f"{(f'{err:+.1f}%' if err is not None else '-'):>10}"
              f"{(f'{rec:.3f}' if (rec is not None and r['A36_aplica']) else '---'):>8}"
              f"{cob*100:7.0f}%{pre*100:7.0f}%")
    print("\numbrales: A3.1 y A3.2 >=80% de los pares, A3.3 >=50%, "
          "A3.4 >=90% por par, A3.5 +-10%, A3.6 >=0.97")
    print("A3.6 solo aplica a los casos de cable tenso; '---' es no aplica.")

    salida = os.path.join(ROOT, "data", "results", "casos_comparacion.json")
    os.makedirs(os.path.dirname(salida), exist_ok=True)
    with open(salida, "w", encoding="utf-8") as fh:
        json.dump(filas, fh, indent=2, ensure_ascii=False, default=float)
    print(f"\ndetalle en {salida}")


if __name__ == "__main__":
    main()
