#!/usr/bin/env python3
"""End-to-end A/B of the learned endpoint finder against the shipped detector.

The standalone evaluation in `synthetic.train_endpoints` measures pixel error
to the true ends. That is necessary and, as the branch scorer proved, not
sufficient: endpoint detection is stage 2 of the pipeline and the tracker
consumes its output at stage 3, so the number that decides is what happens to
the *traced path* when the endpoints move. A pair that is 30 px off along the
cable costs almost nothing; a pair where one end landed on the wrong strand
of a crossing costs the whole trace.

For each fresh synthetic scene (seeds the trainers never saw), both detectors
run through the real entry point `detect_wire_endpoints`, and the real
`SmartWireTracker` traces the mask from each pair. Reported per detector:

- endpoint error in pixels, best assignment against the true ends,
- end-to-end coverage from the tracker,
- coverage from the *true* endpoints, as the ceiling either could reach,
- wins / losses / ties on coverage, and runtime.

    python3 tools/benchmark_endpoint_model.py --count 40

Writes nothing but its report.
"""
from __future__ import annotations

import argparse
import contextlib
import io
import os
import statistics as st
import sys
import time
from collections import defaultdict
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import synthetic  # noqa: F401,E402  (reconfigures stdout for Windows)
from synthetic import generate  # noqa: E402
from synthetic.evaluate import path_agreement  # noqa: E402
from processing import endpoint_model  # noqa: E402
from processing.endpoint_detector import detect_wire_endpoints  # noqa: E402
from processing.smart_wire_tracker import SmartWireTracker  # noqa: E402

#: Seed offset for the benchmark scenes. The datasets are generated from
#: small consecutive seeds, so anything up here was never trained on.
SEED_BASE = 50_000


def endpoint_error(found, true_a, true_b) -> float:
    """Mean per-end distance under the better of the two assignments."""
    (s, e) = found
    s = np.asarray(s, float)
    e = np.asarray(e, float)
    d1 = np.linalg.norm(s - true_a) + np.linalg.norm(e - true_b)
    d2 = np.linalg.norm(s - true_b) + np.linalg.norm(e - true_a)
    return float(min(d1, d2)) / 2.0


def run_tracker(mask, start, end, max_iter, gt_xy, radius) -> dict:
    t0 = time.time()
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        tracker = SmartWireTracker(mask, tuple(map(int, start)), tuple(map(int, end)))
        result = tracker.track_wire(max_iterations=max_iter)
    h, w = mask.shape[:2]
    agree = path_agreement(tracker.path, gt_xy, (w, h), radius)
    # track_wire reports coverage as a 0..1 fraction; percent reads better
    return {"coverage": 100.0 * float(result.get("coverage", 0.0)),
            "f1": 100.0 * agree["f1"],
            "recall": 100.0 * agree["recall"],
            "precision": 100.0 * agree["precision"],
            "seconds": time.time() - t0}


def detect(mask, learned: bool):
    """Run the real pipeline entry with the model on or off."""
    os.environ[endpoint_model.ENV_FLAG] = "1" if learned else "0"
    endpoint_model.reset()
    t0 = time.time()
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        pair = detect_wire_endpoints(mask)
    return pair, time.time() - t0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--count", type=int, default=40)
    ap.add_argument("--size", type=int, nargs=2, default=(960, 720))
    ap.add_argument("--max-iter", type=int, default=3000)
    ap.add_argument("--seed-base", type=int, default=SEED_BASE)
    ap.add_argument("--verbose", action="store_true", help="one line per scene")
    args = ap.parse_args(argv)

    os.environ[endpoint_model.ENV_FLAG] = "1"
    endpoint_model.reset()
    finder = endpoint_model.get_finder()
    if finder is None:
        print("No usable endpoint model. Train one first:\n"
              "  python -m synthetic.generate path --count 1500\n"
              "  python -m synthetic.train_endpoints")
        return 1
    print(finder.summary)
    print(f"{args.count} fresh scenes from seed {args.seed_base}, "
          f"size {args.size[0]}x{args.size[1]}\n")

    rows = []
    for i in range(args.count):
        mask, xy, meta, _ = generate.make_path_scene(args.seed_base + i, tuple(args.size))
        true_a, true_b = np.asarray(xy[0], float), np.asarray(xy[-1], float)

        radius = float(meta.get("base_radius_px", 6.0))
        row = {"shape": meta["shape"]}
        for name, learned in (("classical", False), ("learned", True)):
            pair, t_det = detect(mask, learned)
            trk = run_tracker(mask, pair[0], pair[1], args.max_iter, xy, radius)
            trk["err"] = endpoint_error(pair, true_a, true_b)
            trk["seconds"] += t_det
            row[name] = trk
        # ceiling: what the tracker does when handed the true ends
        trk = run_tracker(mask, true_a, true_b, args.max_iter, xy, radius)
        row["ceiling"] = trk["f1"]
        row["ceiling_cov"] = trk["coverage"]
        rows.append(row)
        if args.verbose:
            c, l = row["classical"], row["learned"]
            print(f"  {i:3d} {row['shape']:9s} err {c['err']:6.1f} vs {l['err']:6.1f} px"
                  f" | F1 {c['f1']:5.1f} vs {l['f1']:5.1f}"
                  f" (ceiling {row['ceiling']:5.1f})")

    os.environ[endpoint_model.ENV_FLAG] = "0"
    endpoint_model.reset()

    def col(name, key):
        return [r[name][key] for r in rows]

    print("\nEndpoint error, px (lower is better)")
    for name in ("classical", "learned"):
        v = col(name, "err")
        print(f"  {name:10s} median {st.median(v):7.1f}   p75 {np.percentile(v, 75):7.1f}"
              f"   within 25px {100 * np.mean(np.array(v) <= 25):3.0f}%")

    print("\nAgreement with the TRUE path, % (the number that decides)")
    print("  The tracker's own coverage counts mask pixels visited, which "
          "rewards wandering;\n  agreement scores the trace against the known "
          "centreline instead.")
    for name in ("classical", "learned"):
        print(f"  {name:10s} F1 mean {st.mean(col(name, 'f1')):5.1f}"
              f"   median {st.median(col(name, 'f1')):5.1f}"
              f"   recall {st.mean(col(name, 'recall')):5.1f}"
              f"   precision {st.mean(col(name, 'precision')):5.1f}")
    ceil = [r["ceiling"] for r in rows]
    print(f"  {'true ends':10s} F1 mean {st.mean(ceil):5.1f}"
          f"   median {st.median(ceil):5.1f}   <- ceiling")

    print("\nTracker's own mask coverage, %, for reference")
    for name in ("classical", "learned"):
        v = col(name, "coverage")
        print(f"  {name:10s} mean {st.mean(v):5.1f}   median {st.median(v):5.1f}")

    wins = sum(1 for r in rows if r["learned"]["f1"] > r["classical"]["f1"] + 2)
    losses = sum(1 for r in rows if r["classical"]["f1"] > r["learned"]["f1"] + 2)
    ties = len(rows) - wins - losses
    print(f"\n  true-path F1, counting 2 points as a difference: "
          f"{wins} wins / {losses} losses / {ties} ties")

    t_c, t_l = st.mean(col("classical", "seconds")), st.mean(col("learned", "seconds"))
    print(f"  runtime per scene: classical {t_c:.1f}s, learned {t_l:.1f}s "
          f"({t_l / max(t_c, 1e-9):.1f}x)")

    print("\nBy shape, mean true-path F1 (classical / learned / ceiling):")
    by = defaultdict(list)
    for r in rows:
        by[r["shape"]].append(r)
    for k in sorted(by):
        g = by[k]
        print(f"  {k:9s} n={len(g):3d}   "
              f"{st.mean(x['classical']['f1'] for x in g):5.1f} / "
              f"{st.mean(x['learned']['f1'] for x in g):5.1f} / "
              f"{st.mean(x['ceiling'] for x in g):5.1f}")

    better_err = st.median(col("learned", "err")) <= st.median(col("classical", "err"))
    better_f1 = (st.mean(col("learned", "f1")) >= st.mean(col("classical", "f1"))
                 and wins >= losses)
    if better_err and better_f1:
        print("\nVerdict: the learned finder is at least as good end to end")
    else:
        print("\nVerdict: the learned finder does NOT pay for itself end to end")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
