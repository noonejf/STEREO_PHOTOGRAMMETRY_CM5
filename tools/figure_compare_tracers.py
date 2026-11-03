"""Side-by-side figure: the same mask traced by each tracer, against the truth.

    python3 tools/figure_compare_tracers.py out.png --seeds 50017 50023 50001

The drawing order is the point of this file. An earlier version put the
true centreline in a grey close to the mask's own grey, which made it
invisible, and the figure then looked like an argument about which
coloured line was prettier. Here the truth is drawn **thick and underneath**
and the traced path **thin and on top**, so what is read directly off the
image is the one thing that matters: which parts of the true cable the
tracer missed. Anything blue left showing is cable the tracer did not
cover; any colour off the blue is cable it invented.

The endpoints are drawn twice, hollow for the true ends and filled for the
ones the detector found, because a tracer handed the wrong seed is being
blamed for someone else's mistake.
"""
from __future__ import annotations

import argparse
import contextlib
import io
import sys
from pathlib import Path

import cv2
import numpy as np

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import synthetic  # noqa: F401,E402
from synthetic import generate  # noqa: E402
from synthetic.evaluate import path_agreement  # noqa: E402
from processing.endpoint_detector import EndpointDetector  # noqa: E402
from processing.smart_wire_tracker import SmartWireTracker  # noqa: E402
from processing import graph_tracer as grt  # noqa: E402

PANEL_W, PANEL_H = 560, 560
TRUTH = (210, 130, 40)        # azul, el camino verdadero
SMART = (60, 140, 255)
GRAPH = (90, 240, 90)


def panel(mask, gt, path, det, true_ends, colour, title, scores, radius):
    h, w = mask.shape[:2]
    img = np.zeros((h, w, 3), np.uint8)
    img[mask > 127] = (46, 46, 46)
    pts = np.round(np.asarray(gt, float)).astype(int)
    pts[:, 0] = np.clip(pts[:, 0], 0, w - 1)
    pts[:, 1] = np.clip(pts[:, 1], 0, h - 1)
    thick = max(5, int(round(2.0 * radius)))
    cv2.polylines(img, [pts.reshape(-1, 1, 2)], False, TRUTH, thick)
    if path:
        p = np.asarray(path, np.int32).reshape(-1, 1, 2)
        cv2.polylines(img, [p], False, colour, 2)
    for e in true_ends:
        cv2.circle(img, (int(e[0]), int(e[1])), 11, (255, 255, 255), 2)
    for e in det:
        cv2.circle(img, (int(e[0]), int(e[1])), 6, (0, 220, 255), -1)

    ys, xs = np.nonzero(mask > 127)
    pad = 26
    crop = img[max(0, ys.min() - pad):ys.max() + pad,
               max(0, xs.min() - pad):xs.max() + pad]
    ch, cw = crop.shape[:2]
    s = min(PANEL_W / cw, (PANEL_H - 60) / ch)
    crop = cv2.resize(crop, (int(cw * s), int(ch * s)),
                      interpolation=cv2.INTER_AREA)
    out = np.zeros((PANEL_H, PANEL_W, 3), np.uint8)
    oy = 60 + ((PANEL_H - 60) - crop.shape[0]) // 2
    ox = (PANEL_W - crop.shape[1]) // 2
    out[oy:oy + crop.shape[0], ox:ox + crop.shape[1]] = crop
    cv2.putText(out, title, (12, 24), cv2.FONT_HERSHEY_SIMPLEX, 0.62, colour, 2)
    cv2.putText(out, scores, (12, 46), cv2.FONT_HERSHEY_SIMPLEX, 0.48,
                (235, 235, 235), 1)
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("out")
    ap.add_argument("--seeds", type=int, nargs="+",
                    default=[50017, 50023, 50001])
    ap.add_argument("--size", type=int, nargs=2, default=(960, 720))
    args = ap.parse_args(argv)

    rows = []
    for seed in args.seeds:
        mask, xy, meta, _ = generate.make_path_scene(seed, tuple(args.size))
        h, w = mask.shape[:2]
        r = float(meta.get("base_radius_px", 6.0))
        true_ends = [np.asarray(xy[0], float), np.asarray(xy[-1], float)]
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            a, b = EndpointDetector(mask, side="left").detect_endpoints(
                "skeleton", save_debug=False)
            trk = SmartWireTracker(mask, a, b)
            trk.track_wire(max_iterations=3000)
        gp, _ = grt.trace(mask, a, b, wire_radius=r)

        A, B = np.asarray(a, float), np.asarray(b, float)
        e_err = min(np.linalg.norm(A - true_ends[0]) + np.linalg.norm(B - true_ends[1]),
                    np.linalg.norm(A - true_ends[1]) + np.linalg.norm(B - true_ends[0])) / 2

        s_a = path_agreement(trk.path, xy, (w, h), r)
        g_a = path_agreement(gp or [], xy, (w, h), r)
        fmt = (lambda d: f"cubre {100*d['recall']:.0f}%  de lo trazado "
                         f"{100*d['precision']:.0f}% es cable  F1 {100*d['f1']:.1f}")
        left = panel(mask, xy, trk.path, [a, b], true_ends, SMART,
                     "SmartWireTracker", fmt(s_a), r)
        right = panel(mask, xy, gp, [a, b], true_ends, GRAPH,
                      "graph_tracer", fmt(g_a), r)
        sep = np.full((PANEL_H, 3, 3), 40, np.uint8)
        band = np.hstack([left, sep, right])
        tag = np.zeros((30, band.shape[1], 3), np.uint8)
        cv2.putText(tag, f"{meta['shape']}  seed {seed}   "
                         f"error de los extremos detectados: {e_err:.0f} px",
                    (12, 21), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 1)
        rows.append(np.vstack([tag, band]))
        print(f"{meta['shape']:<9} seed {seed}  endpoints {e_err:5.1f} px  "
              f"smart F1 {100*s_a['f1']:5.1f}  grafo F1 {100*g_a['f1']:5.1f}",
              flush=True)

    legend = np.zeros((34, rows[0].shape[1], 3), np.uint8)
    cv2.putText(legend, "azul grueso = hilo verdadero     linea fina = lo trazado"
                        "     circulo blanco = extremo real     punto amarillo = "
                        "extremo detectado",
                (12, 22), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (200, 200, 200), 1)
    gap = np.full((8, rows[0].shape[1], 3), 20, np.uint8)
    fig = legend
    for r_ in rows:
        fig = np.vstack([fig, gap, r_])
    cv2.imwrite(args.out, fig)
    print("escrito", args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
