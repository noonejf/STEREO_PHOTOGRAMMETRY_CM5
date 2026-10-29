"""End-to-end A/B of the geodesic tracer against `SmartWireTracker`.

Same scenes, same endpoints, same verdict metric as every other benchmark
here: F1 of the traced path against the known centreline
(`synthetic/evaluate.py`), on fresh scenes the trainers never saw.

Each tracer is run twice, once from the shipped detector's endpoints and
once from the true ends. The pair separates two things that are easy to
confuse: how good the tracer is, and how much it is being hurt by its
seed. The branch scorer was measured for a year against the first question
when the second was the binding one.

``--beta-sweep`` reports what each cost steepness would have scored. Beta
is the only real parameter: the cost of a pixel is exp(-beta * p), so the
ratio between crossing background and following the cable is exp(beta),
and that ratio is exactly how long a break the tracer will bridge. Low
beta bridges aggressively and starts cutting corners; high beta behaves
like the binary mask the old tracer walks.

Writes nothing but its report.
"""
from __future__ import annotations

import argparse
import contextlib
import io
import sys
import time
from pathlib import Path

import numpy as np

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import synthetic  # noqa: F401,E402  (console encoding fix)
from synthetic import generate  # noqa: E402
from synthetic.evaluate import path_agreement  # noqa: E402
from processing import geodesic_tracer  # noqa: E402
from processing.endpoint_detector import EndpointDetector  # noqa: E402
from processing.smart_wire_tracker import SmartWireTracker  # noqa: E402

BETAS = [3.0, 4.0, 6.0, 8.0, 12.0]


def classical_ends(mask):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        det = EndpointDetector(mask, side="left")
        return det.detect_endpoints(method="skeleton", save_debug=False)


def run_smart(mask, a, b, gt, radius, max_iter):
    t0 = time.time()
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        trk = SmartWireTracker(mask, tuple(int(v) for v in a),
                               tuple(int(v) for v in b))
        trk.track_wire(max_iterations=max_iter)
    h, w = mask.shape[:2]
    ag = path_agreement(trk.path, gt, (w, h), radius)
    ag["seconds"] = time.time() - t0
    return ag


def run_geodesic(mask, a, b, gt, radius, beta):
    t0 = time.time()
    path, info = geodesic_tracer.trace(mask, tuple(int(v) for v in a),
                                       tuple(int(v) for v in b), beta=beta)
    h, w = mask.shape[:2]
    ag = path_agreement(path or [], gt, (w, h), radius)
    ag["seconds"] = time.time() - t0
    ag["off_cable"] = info.get("off_cable_frac", 0.0)
    return ag


def summarise(name, rows, base=None):
    f1 = 100 * float(np.mean([r["f1"] for r in rows]))
    rec = 100 * float(np.mean([r["recall"] for r in rows]))
    pre = 100 * float(np.mean([r["precision"] for r in rows]))
    sec = float(np.mean([r["seconds"] for r in rows]))
    med = 100 * float(np.median([r["f1"] for r in rows]))
    delta = "" if base is None else f"{f1 - base:+.1f}"
    print(f"  {name:<26}{f1:>8.1f}{med:>8.1f}{rec:>8.1f}{pre:>8.1f}"
          f"{sec:>8.2f}{delta:>8}")
    return f1


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--count", type=int, default=60)
    ap.add_argument("--size", type=int, nargs=2, default=(960, 720))
    ap.add_argument("--max-iter", type=int, default=3000)
    ap.add_argument("--seed-base", type=int, default=50_000)
    ap.add_argument("--beta", type=float, default=geodesic_tracer.DEFAULT_BETA)
    ap.add_argument("--beta-sweep", action="store_true")
    args = ap.parse_args(argv)

    print(f"{args.count} fresh scenes from seed {args.seed_base}, "
          f"{args.size[0]}x{args.size[1]}\n")

    betas = BETAS if args.beta_sweep else [args.beta]
    rows = {"smart (detected ends)": [], "smart (true ends)": []}
    for b in betas:
        rows[f"geodesic b={b:g} (detected)"] = []
        rows[f"geodesic b={b:g} (true)"] = []
    shapes = []

    t0 = time.time()
    for i in range(args.count):
        mask, xy, meta, _ = generate.make_path_scene(args.seed_base + i,
                                                     tuple(args.size))
        radius = float(meta.get("base_radius_px", 6.0))
        shapes.append(meta["shape"])
        det = classical_ends(mask)
        tru = (tuple(np.asarray(xy[0], int)), tuple(np.asarray(xy[-1], int)))

        rows["smart (detected ends)"].append(
            run_smart(mask, det[0], det[1], xy, radius, args.max_iter))
        rows["smart (true ends)"].append(
            run_smart(mask, tru[0], tru[1], xy, radius, args.max_iter))
        for b in betas:
            rows[f"geodesic b={b:g} (detected)"].append(
                run_geodesic(mask, det[0], det[1], xy, radius, b))
            rows[f"geodesic b={b:g} (true)"].append(
                run_geodesic(mask, tru[0], tru[1], xy, radius, b))

        if (i + 1) % 10 == 0:
            print(f"  {i + 1}/{args.count} ({time.time() - t0:.0f}s)")

    print(f"\n  {'tracer':<26}{'F1':>8}{'median':>8}{'recall':>8}"
          f"{'prec':>8}{'sec':>8}{'vs':>8}")
    base = summarise("smart (detected ends)", rows["smart (detected ends)"])
    for name in rows:
        if name != "smart (detected ends)":
            summarise(name, rows[name], base)

    order = [n for n in rows]
    uniq = sorted(set(shapes))
    print(f"\n  by shape, mean F1")
    print(f"  {'shape':<10}{'n':>4}" + "".join(f"{n[:14]:>15}" for n in order))
    for sh in uniq:
        idx = [i for i, s in enumerate(shapes) if s == sh]
        cells = "".join(
            f"{100 * np.mean([rows[n][i]['f1'] for i in idx]):>15.1f}"
            for n in order)
        print(f"  {sh:<10}{len(idx):>4}{cells}")

    key = f"geodesic b={args.beta:g} (detected)"
    if key in rows:
        off = 100 * float(np.mean([r["off_cable"] for r in rows[key]]))
        print(f"\n  at beta={args.beta:g}, {off:.1f}% of the traced pixels "
              f"ran over background: that is the break-bridging, and the "
              f"shortcutting, in one number")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
