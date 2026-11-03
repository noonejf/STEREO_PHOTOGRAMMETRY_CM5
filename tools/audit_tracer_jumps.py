"""Audit both tracers for invented cable: jumps between consecutive points.

A traced path is consumed downstream as if every pixel of it were cable.
Stage 6 triangulates it and stage 7 turns it into arc length in metres, so
a straight segment drawn across background is not a cosmetic flaw, it is a
measurement that is wrong and does not look wrong.

The agreement metric alone does not catch this, and did not: it scores the
listed vertices, and a tracer that returns two points a hundred pixels
apart has both of them on the cable. This walks the chain, fills in the
pixels between consecutive vertices, and reports how many of them lie off
the mask and how long the largest jump is.

    python3 tools/audit_tracer_jumps.py --count 60
"""
from __future__ import annotations

import argparse
import contextlib
import io
import sys
from pathlib import Path

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


def densify(path):
    out = []
    for a, b in zip(path[:-1], path[1:]):
        n = max(abs(int(b[0]) - int(a[0])), abs(int(b[1]) - int(a[1])), 1)
        for t in range(n):
            out.append((int(round(a[0] + (b[0] - a[0]) * t / n)),
                        int(round(a[1] + (b[1] - a[1]) * t / n))))
    out.append((int(path[-1][0]), int(path[-1][1])))
    return out


def audit(path, mask):
    if not path or len(path) < 2:
        return {"off_frac": 1.0, "max_jump": 0.0}
    h, w = mask.shape[:2]
    d = densify(path)
    off = sum(1 for x, y in d
              if not (0 <= y < h and 0 <= x < w and mask[y, x] > 127))
    jumps = [float(np.hypot(b[0] - a[0], b[1] - a[1]))
             for a, b in zip(path[:-1], path[1:])]
    return {"off_frac": off / max(len(d), 1), "max_jump": max(jumps)}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--count", type=int, default=60)
    ap.add_argument("--seed-base", type=int, default=50_000)
    ap.add_argument("--size", type=int, nargs=2, default=(960, 720))
    args = ap.parse_args(argv)

    rows = {"smart": [], "graph": []}
    worst = {"smart": (0.0, None), "graph": (0.0, None)}
    for i in range(args.count):
        seed = args.seed_base + i
        mask, xy, meta, _ = generate.make_path_scene(seed, tuple(args.size))
        h, w = mask.shape[:2]
        r = float(meta.get("base_radius_px", 6.0))
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            a, b = EndpointDetector(mask, side="left").detect_endpoints(
                "skeleton", save_debug=False)
            trk = SmartWireTracker(mask, a, b)
            trk.track_wire(max_iterations=3000)
        gp, _ = grt.trace(mask, a, b, wire_radius=r)

        for name, path in (("smart", trk.path), ("graph", gp or [])):
            au = audit(path, mask)
            au["f1"] = path_agreement(path, xy, (w, h), r)["f1"]
            au["seed"] = seed
            au["shape"] = meta["shape"]
            au["radius"] = r
            rows[name].append(au)
            if au["max_jump"] > worst[name][0]:
                worst[name] = (au["max_jump"], seed)
        if (i + 1) % 15 == 0:
            print(f"  {i + 1}/{args.count}", flush=True)

    print(f"\n  {'tracer':<8}{'F1':>7}{'px inventados':>15}"
          f"{'escenas con salto':>20}{'salto peor':>12}")
    for name in ("smart", "graph"):
        rs = rows[name]
        f1 = 100 * float(np.mean([r_["f1"] for r_ in rs]))
        off = 100 * float(np.mean([r_["off_frac"] for r_ in rs]))
        big = sum(1 for r_ in rs
                  if r_["max_jump"] > max(8.0, 3.0 * r_["radius"]))
        print(f"  {name:<8}{f1:>7.1f}{off:>14.2f}%"
              f"{big:>13}/{len(rs)}{worst[name][0]:>12.1f}")

    print(f"\n  por forma, F1 medio")
    shapes = sorted({r_["shape"] for r_ in rows["smart"]})
    print(f"  {'forma':<10}{'n':>4}{'smart':>9}{'grafo':>9}{'dif':>8}")
    for sh in shapes:
        idx = [i for i, r_ in enumerate(rows["smart"]) if r_["shape"] == sh]
        a_ = 100 * np.mean([rows["smart"][i]["f1"] for i in idx])
        b_ = 100 * np.mean([rows["graph"][i]["f1"] for i in idx])
        print(f"  {sh:<10}{len(idx):>4}{a_:>9.1f}{b_:>9.1f}{b_ - a_:>+8.1f}")

    wins = sum(1 for a_, b_ in zip(rows["smart"], rows["graph"])
               if b_["f1"] > a_["f1"] + 0.02)
    loss = sum(1 for a_, b_ in zip(rows["smart"], rows["graph"])
               if a_["f1"] > b_["f1"] + 0.02)
    print(f"\n  grafo gana {wins}, pierde {loss}, empata "
          f"{len(rows['smart']) - wins - loss}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
