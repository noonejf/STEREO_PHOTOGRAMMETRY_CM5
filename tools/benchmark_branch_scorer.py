#!/usr/bin/env python3
"""End-to-end A/B of the learned branch scorer against the hand-tuned formula.

This exists because the offline metric lied. `synthetic.train_path` reported
the first trained scorer at 0.692 top-1 against the formula's 0.456 over
25317 held-out decisions, a wide and real margin, and the same model then
failed to improve the tracker end to end: over four masks it won one, lost
one badly and tied two, at two to five times the runtime.

Per-step accuracy and final coverage are not the same quantity. The tracker
is a sequential search with backtracking, so one confident wrong turn early
can cost more than the several hesitant ones the backtracking was tuned
around. Only coverage decides whether the model is worth switching on.

    python3 tools/benchmark_branch_scorer.py --count 40

Reads the synthetic path dataset. Writes nothing but its report.
"""
from __future__ import annotations

import argparse
import contextlib
import io
import json
import os
import statistics as st
import sys
import time
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import synthetic  # noqa: F401,E402
from processing.branch_scorer import get_scorer, reset  # noqa: E402
from processing.smart_wire_tracker import SmartWireTracker  # noqa: E402

DATA = ROOT / "data" / "synthetic" / "path"


def run_one(mask, start, end, max_iter):
    t0 = time.time()
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        tracker = SmartWireTracker(mask, start, end)
        result = tracker.track_wire(max_iterations=max_iter)
    return {"coverage": float(result.get("coverage", 0.0)),
            "points": len(tracker.path),
            "seconds": time.time() - t0}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data", default=str(DATA))
    ap.add_argument("--count", type=int, default=25)
    ap.add_argument("--max-iter", type=int, default=3000)
    ap.add_argument("--verbose", action="store_true", help="one line per mask")
    args = ap.parse_args(argv)

    data = Path(args.data)
    masks = sorted((data / "masks").glob("*.png"))[:args.count]
    if not masks:
        print(f"No masks in {data / 'masks'}. "
              "Run: python -m synthetic.generate path --count 500")
        return 1

    os.environ["LINKU_BRANCH_SCORER"] = "1"
    reset()
    scorer = get_scorer()
    if scorer is None:
        print("No usable path model. Train one first:\n"
              "  python -m synthetic.generate path --count 2000\n"
              "  python -m synthetic.train_path")
        return 1
    print(scorer.summary)
    print(f"\nRunning {len(masks)} masks both ways\n")

    rows = []
    for i, mp in enumerate(masks, 1):
        pj = data / "paths" / (mp.stem + ".json")
        if not pj.exists():
            continue
        mask = cv2.imread(str(mp), cv2.IMREAD_GRAYSCALE)
        gt = np.array(json.load(open(pj, encoding="utf-8"))["path"])
        if mask is None or len(gt) < 2:
            continue
        start = tuple(int(v) for v in gt[0])
        end = tuple(int(v) for v in gt[-1])

        out = {}
        for flag, label in (("1", "learned"), ("0", "formula")):
            os.environ["LINKU_BRANCH_SCORER"] = flag
            reset()
            out[label] = run_one(mask, start, end, args.max_iter)
        out["id"] = mp.stem
        rows.append(out)
        if args.verbose:
            print(f"  {mp.stem}  learned {out['learned']['coverage']*100:5.1f}%  "
                  f"formula {out['formula']['coverage']*100:5.1f}%  "
                  f"({out['learned']['seconds']:.1f}s vs {out['formula']['seconds']:.1f}s)")
        elif i % 5 == 0:
            print(f"  {i}/{len(masks)}", flush=True)

    if not rows:
        print("Nothing ran.")
        return 1

    lc = [r["learned"]["coverage"] for r in rows]
    fc = [r["formula"]["coverage"] for r in rows]
    lt = [r["learned"]["seconds"] for r in rows]
    ft = [r["formula"]["seconds"] for r in rows]
    wins = sum(1 for a, b in zip(lc, fc) if a > b + 0.02)
    losses = sum(1 for a, b in zip(lc, fc) if b > a + 0.02)
    ties = len(rows) - wins - losses

    print(f"\n{len(rows)} masks")
    print(f"  {'':<14}{'learned':>10}{'formula':>10}")
    print(f"  {'mean coverage':<14}{st.mean(lc)*100:>9.1f}%{st.mean(fc)*100:>9.1f}%")
    print(f"  {'median':<14}{st.median(lc)*100:>9.1f}%{st.median(fc)*100:>9.1f}%")
    print(f"  {'mean seconds':<14}{st.mean(lt):>10.2f}{st.mean(ft):>10.2f}")
    print(f"\n  learned wins {wins}, loses {losses}, ties {ties} "
          f"(2 percentage points of coverage counts as a difference)")
    print(f"  slowdown: {st.mean(lt)/max(st.mean(ft), 1e-9):.1f}x")

    better = st.mean(lc) > st.mean(fc) + 0.02 and wins > losses
    print("\nVerdict: " + ("switch it on, LINKU_BRANCH_SCORER=1, it improves coverage"
                           if better else
                           "leave it off. The offline top-1 margin does not reach "
                           "coverage, which is the number that matters"))
    os.environ["LINKU_BRANCH_SCORER"] = "0"
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
