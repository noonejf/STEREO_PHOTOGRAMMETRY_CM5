"""Sweep the learned endpoint decoder's settings, scored end to end.

`benchmark_endpoint_model.py` answers one question: does the learned finder,
as configured, beat the shipped detector on the traced path. This answers
the follow-up: is there *any* setting that would.

The expensive part is the tracker, at several seconds a run, and most
settings pick the same pair of pixels as their neighbours. So the pairs are
collected first, deduplicated per scene, and the tracker runs once per
distinct pair. A sweep of six settings then costs barely more than one
benchmark.

Two sweeps, chosen with ``--what``.

``gate`` sweeps ``min_one_sided`` in the full decoder, where the model
scores every skeleton pixel. This one is **closed and negative**: no
setting reached the classical detector, and the top of the range, where
only skeleton tips are accepted, still lost by 2.1 points.

``rerank`` sweeps the weight on the geodesic span when the model chooses
among the candidates the classical detector proposed. At a large weight it
reproduces the classical pair exactly, so that end of the sweep is a
built-in control: if the sweep does not converge to the classical score
there, the harness is wrong before the model is.

Writes nothing but its report.
"""
from __future__ import annotations

import argparse
import contextlib
import io
import os
import sys
import time
from pathlib import Path

import numpy as np

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import synthetic  # noqa: F401,E402  (console encoding fix)
from synthetic import generate  # noqa: E402
from synthetic.endpoints import predict_pair, score_candidates  # noqa: E402
from synthetic.evaluate import path_agreement  # noqa: E402
from processing import endpoint_model  # noqa: E402
from processing.endpoint_detector import EndpointDetector  # noqa: E402
from processing.smart_wire_tracker import SmartWireTracker  # noqa: E402

GATE_SETTINGS = [
    ("gate .30", 0.30),
    ("gate .50", 0.50),
    ("gate .70", 0.70),
    ("gate .85", 0.85),
    ("tips only", 1.01),   # nothing but a skeleton tip can clear this
]

RERANK_WEIGHTS = [0.0, 0.25, 0.5, 1.0, 2.0, 5.0, 20.0]


def trace_f1(mask, pair, gt, radius, max_iter):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        tracker = SmartWireTracker(mask, tuple(int(v) for v in pair[0]),
                                   tuple(int(v) for v in pair[1]))
        tracker.track_wire(max_iterations=max_iter)
    h, w = mask.shape[:2]
    return path_agreement(tracker.path, gt, (w, h), radius)["f1"]


def classical(mask):
    """The shipped detector's pair and the shortlist it chose it from."""
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        det = EndpointDetector(mask, side="left")
        start, end = det.detect_endpoints(method="skeleton", save_debug=False)
    return (start, end), list(getattr(det, "candidates", []))


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--what", default="rerank", choices=["gate", "rerank"])
    ap.add_argument("--count", type=int, default=60)
    ap.add_argument("--size", type=int, nargs=2, default=(960, 720))
    ap.add_argument("--max-iter", type=int, default=3000)
    ap.add_argument("--seed-base", type=int, default=50_000)
    args = ap.parse_args(argv)

    os.environ[endpoint_model.ENV_FLAG] = "1"
    endpoint_model.reset()
    finder = endpoint_model.get_finder()
    if finder is None:
        print("No usable endpoint model.")
        return 1
    print(finder.summary)
    print(f"{args.count} fresh scenes from seed {args.seed_base}, "
          f"sweeping {args.what}\n")

    if args.what == "gate":
        labels = [s[0] for s in GATE_SETTINGS]
    else:
        labels = [f"w={w:g}" for w in RERANK_WEIGHTS]

    t0 = time.time()
    scenes = []
    n_cands = []
    for i in range(args.count):
        mask, xy, meta, _ = generate.make_path_scene(args.seed_base + i,
                                                     tuple(args.size))
        radius = float(meta.get("base_radius_px", 6.0))
        cl_pair, cands = classical(mask)
        n_cands.append(len(cands))

        pairs = {"classical": cl_pair,
                 "true ends": (tuple(np.asarray(xy[0], int)),
                               tuple(np.asarray(xy[-1], int)))}
        if args.what == "gate":
            for label, thr in GATE_SETTINGS:
                p1, p2, _ = predict_pair(finder.model, finder.feature_names,
                                         mask, min_one_sided=thr,
                                         classical_margin=0.0)
                pairs[label] = cl_pair if p1 is None else (p1, p2)
        else:
            for w, label in zip(RERANK_WEIGHTS, labels):
                if len(cands) > 2:
                    p1, p2, _ = score_candidates(finder.model,
                                                 finder.feature_names, mask,
                                                 cands, geodesic_weight=w)
                else:
                    p1 = None   # nothing to choose between
                pairs[label] = cl_pair if p1 is None else (p1, p2)

        scenes.append({"mask": mask, "gt": xy, "radius": radius,
                       "shape": meta["shape"], "pairs": pairs})
        if (i + 1) % 10 == 0:
            print(f"  decoded {i + 1}/{args.count} ({time.time() - t0:.0f}s)")

    print(f"\n  candidates per mask: median {int(np.median(n_cands))}, "
          f"max {max(n_cands)}, masks with more than two: "
          f"{sum(1 for c in n_cands if c > 2)}/{len(n_cands)}")

    # one tracker run per distinct pair per scene, not per setting
    print("  tracing...")
    results = {k: [] for k in scenes[0]["pairs"]}
    traced = 0
    for sc in scenes:
        cache = {}
        for label, pair in sc["pairs"].items():
            key = (tuple(int(v) for v in pair[0]),
                   tuple(int(v) for v in pair[1]))
            if key not in cache:
                cache[key] = trace_f1(sc["mask"], pair, sc["gt"],
                                      sc["radius"], args.max_iter)
                traced += 1
            results[label].append(cache[key])
    print(f"  {traced} tracker runs for "
          f"{len(scenes) * len(results)} scene/setting cells\n")

    base = float(np.mean(results["classical"]) * 100)
    order = ["classical"] + labels + ["true ends"]
    print(f"  {'setting':<14}{'F1 mean':>9}{'vs classical':>14}"
          f"{'wins':>6}{'losses':>8}{'same':>6}")
    for label in order:
        f1 = float(np.mean(results[label]) * 100)
        wins = sum(1 for a, b in zip(results[label], results["classical"])
                   if a > b + 0.02)
        loss = sum(1 for a, b in zip(results[label], results["classical"])
                   if b > a + 0.02)
        same = sum(1 for a, b in zip(results[label], results["classical"])
                   if abs(a - b) < 1e-9)
        delta = "" if label == "classical" else f"{f1 - base:+.1f}"
        print(f"  {label:<14}{f1:>9.1f}{delta:>14}{wins:>6}{loss:>8}{same:>6}")

    shapes = sorted({sc["shape"] for sc in scenes})
    print(f"\n  by shape, mean F1")
    print(f"  {'shape':<10}{'n':>4}" + "".join(f"{l[:11]:>12}" for l in order))
    for sh in shapes:
        idx = [i for i, sc in enumerate(scenes) if sc["shape"] == sh]
        cells = "".join(f"{100 * np.mean([results[l][i] for i in idx]):>12.1f}"
                        for l in order)
        print(f"  {sh:<10}{len(idx):>4}{cells}")

    os.environ[endpoint_model.ENV_FLAG] = "0"
    endpoint_model.reset()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
